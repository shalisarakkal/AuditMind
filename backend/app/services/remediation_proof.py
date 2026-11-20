"""Open-finding proof review. No workflow closure or scoring authority is granted."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import DBAPIError
from app.models.archive import ArchiveBatch
from app.models.enums import ArchiveState, UserRole
from app.models.finding_observation import FindingObservation
from app.models.finding_consolidation import FindingConsolidation
from app.models.membership import OrgMembership
from app.models.remediation_proof import RemediationProof
from app.models.user import User
from app.services.events import actor_label, record_event
from app.services.knowledge_service import KnowledgeError, require_active_org
from app.services.org_lock import lock_org, lock_org_jobs
from app.services.publication_consumers import context as publication_context
from app.services.status_scoring import _finding, _reference

MAX_AGE = timedelta(days=90)


def _ready(db):
    if not db.scalar(text("""SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_trigger t ON t.tgrelid=c.oid JOIN pg_proc p ON p.oid=t.tgfoid
        WHERE n.nspname=current_schema() AND p.pronamespace=n.oid AND p.proname='am_remediation_proof_guard_v1'
        AND c.relname='remediation_proofs' AND t.tgname='am_remediation_proof_guard' AND t.tgenabled='O' AND t.tgtype=31)""")):
        raise HTTPException(503, "Remediation proof review requires coordinated schema activation")


def _latest(db, org_id, finding_id):
    return db.scalar(select(RemediationProof).where(RemediationProof.org_id == org_id,
        RemediationProof.finding_id == finding_id).order_by(RemediationProof.version.desc()).limit(1))


def has_history(db, org_id, finding_id):
    # Consolidation can run on the preceding schema before proof activation.
    installed = db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname='remediation_proofs')"))
    return bool(installed and _latest(db, org_id, finding_id))


def _context(db, finding):
    return dict(workflow_version=finding.workflow_version,
        observation_count=db.scalar(select(func.count()).select_from(FindingObservation).where(
            FindingObservation.org_id == finding.org_id, FindingObservation.finding_id == finding.id)),
        publication=publication_context(db, finding.org_id, finding.id),
        consolidation_generation=int(db.scalar(select(func.coalesce(func.sum(FindingConsolidation.version), 0)).where(
            FindingConsolidation.org_id == finding.org_id, or_(FindingConsolidation.finding_a_id == finding.id,
                FindingConsolidation.finding_b_id == finding.id)))))


def _current(db, finding, latest):
    if latest is None:
        return False
    context = _context(db, finding)
    captured = {key: latest.context.get(key) for key in context}
    if finding.workflow_status != "open" or finding.consolidation_id or captured != context:
        return False
    if not datetime.now(timezone.utc) - MAX_AGE <= latest.observed_at <= datetime.now(timezone.utc):
        return False
    try:
        _, _, digest = _reference(db, finding.org_id, latest.source_reference)
    except HTTPException as exc:
        if exc.status_code == 422:
            return False
        raise
    return digest == latest.source_sha256


def read(db, org_id, finding_id, member, *, before=None, limit=20):
    _ready(db)
    finding = _finding(db, org_id, finding_id)
    latest = _latest(db, org_id, finding_id)
    current = _current(db, finding, latest)
    query = select(RemediationProof).where(RemediationProof.org_id == org_id, RemediationProof.finding_id == finding_id)
    if before is not None:
        query = query.where(RemediationProof.version < before)
    records = db.scalars(query.order_by(RemediationProof.version.desc()).limit(limit + 1)).all()
    reason = None
    if finding.consolidation_id:
        reason = "Remediation proof review is unavailable for consolidated pairs."
    elif finding.workflow_status != "open":
        reason = "Remediation proof is submitted while the workflow is Open."
    state = latest.state if latest else "not_submitted"
    if latest and not current:
        state = "stale"
    return dict(version=latest.version if latest else 0, workflow_version=finding.workflow_version,
        workflow_status=finding.workflow_status, state=state, blocked_reason=reason,
        can_submit=reason is None and member.role in (UserRole.admin, UserRole.auditor),
        can_review=reason is None and member.role == UserRole.admin and current and latest.state == "pending",
        self_review_required=bool(latest and latest.submitter_id == member.user_id),
        next_before=records[limit - 1].version if len(records) > limit else None,
        records=[{key: getattr(row, key) for key in ("id", "version", "workflow_version", "state", "source_reference",
            "source_sha256", "observed_at", "submitter_label", "actor_label", "note", "created_at")} for row in records[:limit]])


def _write(db, org_id, finding_id, member, payload, *, review):
    _ready(db)
    lock_org_jobs(db, org_id)
    def busy():
        raise HTTPException(409, "Inventory is changing; retry proof review after the current batch")
    lock_org(db, org_id, on_wait=busy)
    try:
        require_active_org(db, org_id, lock=True)
    except KnowledgeError as exc:
        raise HTTPException(409, "Organization is read-only or unavailable") from exc
    current = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id,
        OrgMembership.user_id == member.user_id).with_for_update(nowait=True).execution_options(populate_existing=True))
    roles = (UserRole.admin,) if review else (UserRole.admin, UserRole.auditor)
    if current is None or current.role not in roles:
        raise HTTPException(403, "Insufficient remediation proof permissions")
    actor = db.scalar(select(User).where(User.id == current.user_id).with_for_update(read=True, nowait=True)
        .execution_options(populate_existing=True))
    if actor is None or not actor.is_active or actor.must_change_password:
        raise HTTPException(403, "An active organization account is required")
    finding = _finding(db, org_id, finding_id, lock=True)
    if finding.consolidation_id:
        raise HTTPException(409, "Remediation proof review is unavailable for consolidated pairs")
    if finding.workflow_status != "open":
        raise HTTPException(409, "Remediation proof requires an Open workflow")
    affected = [v for v in (finding.id, finding.asset_id, finding.scan_id) if v]
    if db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id, ArchiveBatch.item_id.in_(affected),
            ArchiveBatch.state.in_((ArchiveState.archiving, ArchiveState.restoring, ArchiveState.purging))).limit(1)):
        raise HTTPException(409, "An affected item is being archived, restored or purged")
    latest = _latest(db, org_id, finding_id)
    version = latest.version if latest else 0
    if payload.expected_version != version or payload.expected_workflow_version != finding.workflow_version:
        raise HTTPException(409, "Workflow or proof changed; reload before retrying")
    instant = datetime.now(timezone.utc)
    context = _context(db, finding)
    if review:
        if latest is None or latest.state != "pending":
            raise HTTPException(409, "Submit evidence before a new review")
        if not _current(db, finding, latest):
            raise HTTPException(409, "Workflow, source or evidence changed; submit current proof again")
        if not payload.evidence_reviewed:
            raise HTTPException(422, "Confirm that you reviewed the referenced evidence")
        if latest.submitter_id == current.user_id and not payload.self_review_acknowledged:
            raise HTTPException(422, "Explicitly acknowledge review of your own submitted proof")
        reference, observed = latest.source_reference, latest.observed_at
        _, _, digest = _reference(db, org_id, reference, lock=True)
        if digest != latest.source_sha256:
            raise HTTPException(409, "Evidence source changed; submit it again")
        submitter_id, submitter_label = latest.submitter_id, latest.submitter_label
        state = payload.decision
        context = {**context, "evidence_reviewed": True,
            "self_review_acknowledged": payload.self_review_acknowledged}
    else:
        if not instant - MAX_AGE <= payload.observed_at <= instant:
            raise HTTPException(422, "Proof observation must be within the last 90 days and not in the future")
        reference, observed = payload.source_reference, payload.observed_at
        _, _, digest = _reference(db, org_id, reference, lock=True)
        submitter_id, submitter_label = actor.id, actor_label(actor)[:255]
        state = "pending"
    row = RemediationProof(org_id=org_id, finding_id=finding_id, version=version + 1,
        workflow_version=finding.workflow_version, state=state, source_reference=reference,
        source_sha256=digest, observed_at=observed, submitter_id=submitter_id, submitter_label=submitter_label,
        actor_id=actor.id, actor_label=actor_label(actor)[:255], note=payload.note, created_at=instant, context=context)
    db.add(row)
    record_event(db, "remediation_proof_changed", org_id=org_id, actor=actor, item=str(finding_id),
        details=dict(finding_id=str(finding_id), version=version + 1, state=state))
    db.commit()
    return read(db, org_id, finding_id, current)


def write(db, org_id, finding_id, member, payload, *, review=False):
    try:
        return _write(db, org_id, finding_id, member, payload, review=review)
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) in ("55P03", "23505", "23503", "40001", "40P01"):
            db.rollback()
            raise HTTPException(409, "Proof or reviewer context is busy or changed; reload before retrying") from exc
        raise
