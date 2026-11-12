"""Versioned declarations and bounded reviews; no absence is treated as remediation."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import load_only

from app.models.archive import ArchiveJob, ArchiveBatch
from app.models.enums import ScanStatus, ArchiveState, UserRole
from app.models.finding import Finding
from app.models.finding_absence_review import (
    FindingAbsenceReviewBatch, FindingAbsenceReviewDecision, FindingAbsenceReviewItem,
)
from app.models.finding_observation import FindingObservation
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.models.scan_snapshot import ScanSnapshotDeclaration
from app.models.user import User
from app.schemas.scan_snapshot import (
    AbsenceReviewDecisionWrite, AbsenceReviewQueueItem, AbsenceReviewQueuePage,
    NotObservedCandidate, SnapshotComparison, SnapshotRead, SnapshotView,
)
from app.services.events import actor_label, record_event
from app.services.org_lock import lock_org, lock_org_jobs
from app.services.knowledge_service import KnowledgeError, require_active_org

_MAX_REVIEW_OBSERVATIONS_PER_SCAN = 5000


def _scan(db, org_id, scan_id, lock=False):
    query = select(Scan).where(Scan.org_id == org_id, Scan.id == scan_id, Scan.archived_at.is_(None))
    if lock:
        query = query.with_for_update(key_share=True)
    scan = db.scalar(query.execution_options(populate_existing=True))
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return scan


def _latest(db, org_id, scan_id):
    return db.scalar(select(ScanSnapshotDeclaration).where(ScanSnapshotDeclaration.org_id == org_id,
        ScanSnapshotDeclaration.scan_id == scan_id).order_by(ScanSnapshotDeclaration.version.desc()).limit(1))


def _context(scan):
    return dict(id=str(scan.id), filename=scan.filename, scan_type=scan.scan_type,
        profile=scan.profile, source=scan.source, status=scan.status.value,
        started_at=scan.started_at.astimezone(timezone.utc).isoformat() if scan.started_at else None,
        completed_at=scan.completed_at.astimezone(timezone.utc).isoformat() if scan.completed_at else None,
        content_hash=scan.content_hash, ingestion_config_fingerprint=scan.ingestion_config_fingerprint)


def _blockers(db, scan):
    blockers, complete = [], []
    if scan.status != ScanStatus.completed or scan.completed_at is None:
        blockers.append("scan_not_successfully_completed")
    if not scan.ingestion_config_fingerprint:
        blockers.append("captured_import_configuration_unavailable")
    summary = scan.summary
    if scan.source != "upload" or not isinstance(summary, dict) or not all(
            type(summary.get(key)) is int and summary[key] >= 0 for key in ("failed", "skipped", "warnings_total")):
        blockers.append("verified_import_report_unavailable")
    elif summary.get("error") or summary.get("errors") or any(summary[key] for key in ("failed", "skipped", "warnings_total")):
        complete.append("import_has_errors_skips_or_warnings")
    if db.scalar(select(ArchiveJob.id).where(ArchiveJob.org_id == scan.org_id,
            ArchiveJob.status.in_((ScanStatus.pending, ScanStatus.running))).limit(1)) or db.scalar(
            select(ArchiveBatch.id).where(ArchiveBatch.org_id == scan.org_id,
                ArchiveBatch.state.in_((ArchiveState.archiving, ArchiveState.restoring, ArchiveState.purging))).limit(1)):
        blockers.append("organization_archive_operation_in_progress")
    return blockers, complete


def read_snapshot(db, org_id, scan_id):
    scan = _scan(db, org_id, scan_id)
    blockers, complete = _blockers(db, scan)
    latest = _latest(db, org_id, scan_id)
    return SnapshotView(scan=_context(scan), declaration=SnapshotRead.model_validate(latest) if latest else None,
        declaration_blockers=blockers, complete_blockers=complete)


def write_snapshot(db, org_id, scan_id, membership, payload, revoke=False):
    # Serialize with job admission and with declarations on this scan. No
    # inventory scan or import-wide org lock: only one small scan row is locked.
    lock_org_jobs(db, org_id)
    try:
        require_active_org(db, org_id, lock=True)
    except KnowledgeError as exc:
        raise HTTPException(409, "Organization is read-only or unavailable") from exc
    current = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id,
        OrgMembership.user_id == membership.user_id).with_for_update().execution_options(populate_existing=True))
    if current is None or current.role not in (UserRole.admin, UserRole.auditor):
        raise HTTPException(403, "Insufficient permissions")
    scan = _scan(db, org_id, scan_id, lock=True)
    latest = _latest(db, org_id, scan_id)
    version = latest.version if latest else 0
    if payload.expected_version != version:
        raise HTTPException(409, dict(code="snapshot_version_conflict", message="Snapshot declaration changed. Reload before saving."))
    if revoke:
        if latest is None or latest.state != "declared":
            raise HTTPException(409, "There is no active declaration to revoke")
        fields, context = latest.declaration, latest.scan_context
    else:
        if payload.source_snapshot_at is not None and scan.completed_at is not None and payload.source_snapshot_at > scan.completed_at:
            raise HTTPException(422, "Source snapshot time must not be later than import completion")
        blockers, complete = _blockers(db, scan)
        if blockers or (payload.snapshot_kind == "complete" and complete):
            raise HTTPException(409, dict(code="snapshot_declaration_blocked", message="This scan cannot receive that declaration", reasons=blockers + complete))
        fields = payload.model_dump(mode="json", exclude={"expected_version", "rationale"})
        context = _context(scan)
    actor = db.get(User, membership.user_id)
    declaration = ScanSnapshotDeclaration(org_id=org_id, scan_id=scan_id, version=version + 1,
        state="revoked" if revoke else "declared", declaration=fields, scan_context=context,
        rationale=payload.rationale, actor_id=membership.user_id, actor_label=actor_label(actor))
    db.add(declaration)
    db.flush()
    record_event(db, "scan_snapshot_revoked" if revoke else "scan_snapshot_declared", org_id=org_id,
        actor=actor, item=scan.filename or str(scan.id),
        details=dict(scan_id=str(scan.id), declaration_id=str(declaration.id), version=declaration.version,
            snapshot_kind=fields["snapshot_kind"], rationale=payload.rationale))
    db.commit()
    return read_snapshot(db, org_id, scan_id)


def compare_snapshots(db, org_id, payload, *, persist_queue=False, membership=None, expected_review_token=None):
    # A comparison is never an authorization token; persist only an explicit,
    # eligible candidate snapshot after rechecking organization and scan state.
    if persist_queue:
        if membership is None or membership.role not in (UserRole.admin, UserRole.auditor):
            raise HTTPException(403, "Insufficient permissions")
        def refuse_busy_inventory():
            raise HTTPException(409, "Inventory publication is in progress; compare again after it finishes")
        lock_org(db, org_id, on_wait=refuse_busy_inventory)
        try:
            require_active_org(db, org_id, lock=True)
        except KnowledgeError as exc:
            raise HTTPException(409, "Organization is read-only or unavailable") from exc
        current_membership = db.scalar(select(OrgMembership).where(
            OrgMembership.org_id == org_id, OrgMembership.user_id == membership.user_id)
            .with_for_update().execution_options(populate_existing=True))
        if current_membership is None or current_membership.role not in (UserRole.admin, UserRole.auditor):
            raise HTTPException(403, "Insufficient permissions")
        membership = current_membership
        for scan_id in sorted((payload.baseline_scan_id, payload.current_scan_id), key=str):
            _scan(db, org_id, scan_id, lock=True)
    if payload.baseline_scan_id == payload.current_scan_id:
        raise HTTPException(422, "Choose two different scans")
    baseline = read_snapshot(db, org_id, payload.baseline_scan_id)
    current = read_snapshot(db, org_id, payload.current_scan_id)
    reasons = []
    for side, view, expected in (("baseline", baseline, payload.baseline_version),
            ("current", current, payload.current_version)):
        declaration = view.declaration
        if declaration is None or declaration.version != expected:
            raise HTTPException(409, "Snapshot declaration changed or is missing. Reload both scans.")
        reasons += [f"{side}:{reason}" for reason in view.declaration_blockers + view.complete_blockers]
        if declaration.state != "declared":
            reasons.append(f"{side}:declaration_revoked")
        if declaration.declaration.snapshot_kind != "complete" or not declaration.declaration.coverage_confirmed:
            reasons.append(f"{side}:source_snapshot_not_complete")
        if declaration.declaration.unreachable_targets:
            reasons.append(f"{side}:unreachable_targets")
        if view.scan != declaration.scan_context:
            reasons.append(f"{side}:scan_context_changed")
    left, right = baseline.declaration.declaration, current.declaration.declaration
    for field in ("tool_name", "tool_instance_id", "tool_configuration_id"):
        if getattr(left, field) != getattr(right, field):
            reasons.append(f"{field}_changed")
    for field in ("scan_type", "profile", "source", "ingestion_config_fingerprint"):
        if baseline.scan[field] != current.scan[field]:
            reasons.append(f"{field}_changed")
    differences = dict(baseline_only_targets=sorted(set(left.targets) - set(right.targets)),
        current_only_targets=sorted(set(right.targets) - set(left.targets)),
        baseline_exclusions=left.exclusions, current_exclusions=right.exclusions,
        baseline_unreachable_targets=left.unreachable_targets, current_unreachable_targets=right.unreachable_targets)
    if left.targets != right.targets:
        reasons.append("target_scope_changed")
    if left.exclusions != right.exclusions:
        reasons.append("scope_exclusions_changed")
    for side, declaration in (("baseline", left), ("current", right)):
        if declaration.source_snapshot_at is None:
            reasons.append(f"{side}:source_snapshot_time_unavailable")
    if left.source_snapshot_at is not None and right.source_snapshot_at is not None and right.source_snapshot_at <= left.source_snapshot_at:
        reasons.append("current_source_snapshot_is_not_newer")
    absence_blockers = list(reasons)
    review_candidates = []
    candidate_count = 0
    baseline_reviewable = current_reviewable = 0
    baseline_unreviewable = current_unreviewable = 0
    ambiguous_identity_count = 0
    identity_fingerprint = None
    all_review_candidates = []
    if not reasons:
        baseline_observations = _scan_observations(db, org_id, payload.baseline_scan_id)
        current_observations = _scan_observations(db, org_id, payload.current_scan_id)
        if (len(baseline_observations) > _MAX_REVIEW_OBSERVATIONS_PER_SCAN
                or len(current_observations) > _MAX_REVIEW_OBSERVATIONS_PER_SCAN):
            if len(baseline_observations) > _MAX_REVIEW_OBSERVATIONS_PER_SCAN:
                absence_blockers.append("baseline:scan_observation_limit_exceeded")
            if len(current_observations) > _MAX_REVIEW_OBSERVATIONS_PER_SCAN:
                absence_blockers.append("current:scan_observation_limit_exceeded")
        else:
            from app.services.identity_bindings import identity_reviews
            baseline_reviews = identity_reviews(db, org_id, baseline_observations)
            current_reviews = identity_reviews(db, org_id, current_observations)
            identity_fingerprint = _identity_review_fingerprint(
                baseline_observations, baseline_reviews, current_observations, current_reviews)
            baseline_keys: dict[str, set] = {}
            finding_keys: dict[object, set[str]] = {}
            latest_observation: dict[object, FindingObservation] = {}
            baseline_counts: dict[object, int] = {}
            for observation in baseline_observations:
                candidate_key = baseline_reviews[observation.id][0]["candidate_key"]
                if candidate_key is None:
                    continue
                baseline_reviewable += 1
                baseline_keys.setdefault(candidate_key, set()).add(observation.finding_id)
                finding_keys.setdefault(observation.finding_id, set()).add(candidate_key)
                latest_observation.setdefault(observation.finding_id, observation)
                baseline_counts[observation.finding_id] = baseline_counts.get(observation.finding_id, 0) + 1
            current_keys = set()
            for observation in current_observations:
                candidate_key = current_reviews[observation.id][0]["candidate_key"]
                if candidate_key is None:
                    continue
                current_reviewable += 1
                current_keys.add(candidate_key)
            baseline_unreviewable = len(baseline_observations) - baseline_reviewable
            current_unreviewable = len(current_observations) - current_reviewable
            if current_unreviewable:
                absence_blockers.append("current:unreviewable_observations_present")
            ambiguous_findings = set()
            for findings_for_key in baseline_keys.values():
                if len(findings_for_key) > 1:
                    ambiguous_identity_count += 1
                    ambiguous_findings.update(findings_for_key)
            possible_findings = {
                finding_id for finding_id, keys in finding_keys.items()
                if not keys.intersection(current_keys) and finding_id not in ambiguous_findings
            } if not current_unreviewable else set()
            findings = db.execute(select(
                Finding.id, Finding.asset_id, func.left(Finding.description, 2000).label("description"), Finding.category,
                Finding.domain, Finding.severity, Finding.workflow_status, Finding.workflow_version,
            ).where(
                Finding.org_id == org_id, Finding.id.in_(possible_findings),
                Finding.active()).order_by(Finding.id)).all() if possible_findings else []
            candidate_count = len(findings)
            for finding in findings:
                observation = latest_observation[finding.id]
                all_review_candidates.append(dict(
                    finding_id=finding.id,
                    baseline_observation_id=observation.id,
                    reviewable_baseline_observation_count=baseline_counts[finding.id],
                    asset_id=finding.asset_id,
                    description=finding.description,
                    category=finding.category,
                    domain=finding.domain.value,
                    severity=finding.severity.value,
                    workflow_status=finding.workflow_status,
                    workflow_version=finding.workflow_version,
                    baseline_recorded_at=observation.recorded_at,
                ))
            review_candidates = all_review_candidates[
                payload.candidate_offset:payload.candidate_offset + payload.candidate_limit]
    absence_eligible = not absence_blockers
    reviewed_at = datetime.now(timezone.utc)
    review_queue_batch_id = None
    review_queue_item_count = 0
    snapshot_candidates = [NotObservedCandidate(**candidate).model_dump(mode="json")
        for candidate in all_review_candidates]
    review_context = dict(baseline=baseline.model_dump(mode="json"), current=current.model_dump(mode="json"),
        identity_review_fingerprint=identity_fingerprint, candidates=snapshot_candidates)
    review_token = hashlib.sha256(json.dumps(review_context, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest() if absence_eligible else None
    if persist_queue and (not review_token or expected_review_token != review_token):
        raise HTTPException(409, "Scan review context changed; compare again before saving candidates")
    if persist_queue and absence_eligible and all_review_candidates:
        actor = db.get(User, membership.user_id)
        batch_identity = dict(
            contract="absence-review-queue-v1",
            org_id=str(org_id),
            baseline_scan_id=str(payload.baseline_scan_id),
            current_scan_id=str(payload.current_scan_id),
            baseline_version=payload.baseline_version,
            current_version=payload.current_version,
            identity_review_fingerprint=identity_fingerprint,
            review_token=review_token,
            candidates=snapshot_candidates,
        )
        batch_key = hashlib.sha256(json.dumps(
            batch_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        batch = db.scalar(select(FindingAbsenceReviewBatch).where(
            FindingAbsenceReviewBatch.org_id == org_id,
            FindingAbsenceReviewBatch.batch_key == batch_key).with_for_update())
        is_new = batch is None
        if batch is None:
            comparison_context = dict(
                reviewed_at=reviewed_at.isoformat(),
                baseline=baseline.model_dump(mode="json"),
                current=current.model_dump(mode="json"),
                declared_metadata_matches=True,
                scope_differences=differences,
                identity_review_fingerprint=identity_fingerprint,
            )
            batch = FindingAbsenceReviewBatch(
                org_id=org_id, batch_key=batch_key, baseline_scan_id=payload.baseline_scan_id,
                current_scan_id=payload.current_scan_id, baseline_version=payload.baseline_version,
                current_version=payload.current_version, context=comparison_context,
                actor_id=membership.user_id, actor_label=actor_label(actor), created_at=reviewed_at,
            )
            db.add(batch)
            db.flush()
            db.add_all([
                FindingAbsenceReviewItem(
                    org_id=org_id, batch_id=batch.id, finding_id=candidate["finding_id"],
                    baseline_observation_id=candidate["baseline_observation_id"],
                    candidate=candidate, created_at=reviewed_at,
                )
                for candidate in snapshot_candidates
            ])
            db.flush()
            record_event(db, "finding_absence_review_saved", org_id=org_id, actor=actor,
                item=f"{baseline.scan.get('filename') or baseline.scan['id']} vs {current.scan.get('filename') or current.scan['id']}",
                details=dict(batch_id=str(batch.id), baseline_scan_id=str(payload.baseline_scan_id),
                    current_scan_id=str(payload.current_scan_id), baseline_version=payload.baseline_version,
                    current_version=payload.current_version, candidate_count=len(snapshot_candidates)))
        review_queue_batch_id = batch.id
        review_queue_item_count = db.scalar(select(func.count(FindingAbsenceReviewItem.id)).where(
            FindingAbsenceReviewItem.org_id == org_id,
            FindingAbsenceReviewItem.batch_id == batch.id)) or 0
        if is_new:
            db.commit()
    return SnapshotComparison(reviewed_at=reviewed_at, baseline=baseline, current=current,
        declared_metadata_matches=not reasons, absence_eligible=absence_eligible,
        blocking_reasons=reasons, absence_blockers=absence_blockers, scope_differences=differences,
        review_candidates=review_candidates, candidate_count=candidate_count,
        candidate_offset=payload.candidate_offset, candidate_limit=payload.candidate_limit,
        baseline_reviewable_observations=baseline_reviewable,
        current_reviewable_observations=current_reviewable,
        baseline_unreviewable_observations=baseline_unreviewable,
        current_unreviewable_observations=current_unreviewable,
        ambiguous_baseline_identity_count=ambiguous_identity_count,
        review_token=review_token, review_queue_batch_id=review_queue_batch_id,
        review_queue_item_count=review_queue_item_count)


def _identity_review_fingerprint(baseline_observations, baseline_reviews, current_observations, current_reviews):
    reviewed = []
    for observations, reviews in ((baseline_observations, baseline_reviews), (current_observations, current_reviews)):
        for observation in observations:
            assessment, binding = reviews[observation.id]
            key = assessment.get("candidate_key")
            reviewed.append(dict(
                observation_id=str(observation.id),
                binding_version=binding["version"] if binding else 0,
                binding_state=binding["state"] if binding else "unreviewed",
                binding_current=binding["current"] if binding else False,
                candidate_key_hash=hashlib.sha256(key.encode()).hexdigest() if key else None,
            ))
    return hashlib.sha256(json.dumps(
        sorted(reviewed, key=lambda value: value["observation_id"]),
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_absence_review_queue(db, org_id, *, state, limit, offset):
    latest_state = select(FindingAbsenceReviewDecision.state).where(
        FindingAbsenceReviewDecision.item_id == FindingAbsenceReviewItem.id,
        FindingAbsenceReviewDecision.org_id == org_id,
    ).order_by(FindingAbsenceReviewDecision.version.desc()).limit(1
    ).correlate(FindingAbsenceReviewItem).scalar_subquery()
    conditions = [FindingAbsenceReviewItem.org_id == org_id]
    if state == "pending":
        conditions.append(or_(latest_state.is_(None), latest_state == "reopened"))
    elif state == "kept_active":
        conditions.append(latest_state == "kept_active")
    total = db.scalar(select(func.count(FindingAbsenceReviewItem.id)).where(*conditions)) or 0
    rows = db.scalars(select(FindingAbsenceReviewItem).where(*conditions).order_by(
        FindingAbsenceReviewItem.created_at.desc(), FindingAbsenceReviewItem.id.desc()
    ).limit(limit).offset(offset)).all()
    # Load each captured declaration context once, not once per candidate in a
    # joined page. Return only compact batch summaries, not repeated scope JSON.
    batches = {batch.id: batch for batch in db.scalars(select(FindingAbsenceReviewBatch).where(
        FindingAbsenceReviewBatch.org_id == org_id,
        FindingAbsenceReviewBatch.id.in_({item.batch_id for item in rows}))).all()} if rows else {}
    latest_decisions = {}
    item_ids = [item.id for item in rows]
    if item_ids:
        ranked_decisions = select(
            FindingAbsenceReviewDecision.id.label("id"),
            func.row_number().over(
                partition_by=FindingAbsenceReviewDecision.item_id,
                order_by=FindingAbsenceReviewDecision.version.desc(),
            ).label("position"),
        ).where(
            FindingAbsenceReviewDecision.org_id == org_id,
            FindingAbsenceReviewDecision.item_id.in_(item_ids),
        ).subquery()
        decisions = db.scalars(select(FindingAbsenceReviewDecision).join(
            ranked_decisions, ranked_decisions.c.id == FindingAbsenceReviewDecision.id,
        ).where(ranked_decisions.c.position == 1)).all()
        latest_decisions = {decision.item_id: decision for decision in decisions}
    return AbsenceReviewQueuePage(
        items=[_absence_review_item(item, batches[item.batch_id], latest_decisions.get(item.id)) for item in rows],
        total=total, limit=limit, offset=offset,
    )


def _absence_review_item(item, batch, decision):
    summary = {"reviewed_at": batch.context["reviewed_at"],
        "identity_review_fingerprint": batch.context["identity_review_fingerprint"]}
    for side in ("baseline", "current"):
        captured = batch.context[side]
        summary[side] = dict(scan={key: captured["scan"].get(key) for key in ("id", "filename")},
            declaration_version=captured["declaration"]["version"])
    return AbsenceReviewQueueItem(
        id=item.id, batch_id=batch.id, candidate=item.candidate, comparison=summary,
        state="kept_active" if decision and decision.state == "kept_active" else "pending",
        decision_version=decision.version if decision else 0,
        rationale=decision.rationale if decision else None,
        actor_label=decision.actor_label if decision else None,
        decided_at=decision.created_at if decision else None,
        created_at=item.created_at,
    )


def decide_absence_review(db, org_id, item_id, membership, payload: AbsenceReviewDecisionWrite):
    # Reviewing a retained queue item never publishes inventory. Do not wait on
    # the import lock or hold job admission behind a long-running import.
    try:
        require_active_org(db, org_id, lock=True)
    except KnowledgeError as exc:
        raise HTTPException(409, "Organization is read-only or unavailable") from exc
    current_membership = db.scalar(select(OrgMembership).where(
        OrgMembership.org_id == org_id, OrgMembership.user_id == membership.user_id)
        .with_for_update().execution_options(populate_existing=True))
    if current_membership is None or current_membership.role not in (UserRole.admin, UserRole.auditor):
        raise HTTPException(403, "Insufficient permissions")
    item = db.scalar(select(FindingAbsenceReviewItem).where(
        FindingAbsenceReviewItem.org_id == org_id,
        FindingAbsenceReviewItem.id == item_id,
    ).with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, "Absence review item not found")
    if payload.action == "keep_active":
        finding = db.scalar(select(Finding).options(load_only(Finding.id, Finding.workflow_version,
            Finding.archived_at, Finding.suppression_id)).where(Finding.org_id == org_id, Finding.id == item.finding_id)
            .with_for_update(key_share=True).execution_options(populate_existing=True))
        if finding is None or finding.archived_at is not None or finding.suppression_id is not None:
            raise HTTPException(409, "This finding is no longer active; refresh the scan comparison before reviewing it")
        if finding.workflow_version != item.candidate["workflow_version"]:
            raise HTTPException(409, "Finding workflow changed since this snapshot; compare the scans again before reviewing it")
    previous = db.scalar(select(FindingAbsenceReviewDecision).where(
        FindingAbsenceReviewDecision.org_id == org_id,
        FindingAbsenceReviewDecision.item_id == item_id,
    ).order_by(FindingAbsenceReviewDecision.version.desc()).limit(1))
    version = previous.version if previous else 0
    if payload.expected_version != version:
        raise HTTPException(409, dict(code="absence_review_version_conflict",
            message="This review changed. Reload the queue before retrying."))
    if payload.action == "keep_active" and previous and previous.state == "kept_active":
        raise HTTPException(409, "This candidate is already marked to remain active")
    if payload.action == "reopen" and (previous is None or previous.state != "kept_active"):
        raise HTTPException(409, "Only a kept-active review can be returned to the queue")
    actor = db.get(User, current_membership.user_id)
    state = "kept_active" if payload.action == "keep_active" else "reopened"
    decision = FindingAbsenceReviewDecision(
        org_id=org_id, item_id=item_id, version=version + 1, state=state,
        rationale=payload.rationale, actor_id=current_membership.user_id,
        actor_label=actor_label(actor),
    )
    db.add(decision)
    db.flush()
    record_event(db, "finding_absence_review_decided" if state == "kept_active" else "finding_absence_review_reopened",
        org_id=org_id, actor=actor, item=str(item.finding_id),
        details=dict(item_id=str(item.id), batch_id=str(item.batch_id), finding_id=str(item.finding_id), version=decision.version,
            state=state, rationale=payload.rationale))
    db.commit()
    return _absence_review_item(item, db.get(FindingAbsenceReviewBatch, item.batch_id), decision)


def _scan_observations(db, org_id, scan_id):
    return db.scalars(select(FindingObservation).options(load_only(
        FindingObservation.id, FindingObservation.org_id, FindingObservation.finding_id,
        FindingObservation.scan_id, FindingObservation.source, FindingObservation.scan_type,
        FindingObservation.profile, FindingObservation.asset_identity,
        FindingObservation.source_identity, FindingObservation.recorded_at,
    )).where(FindingObservation.org_id == org_id, FindingObservation.scan_id == scan_id)
        .order_by(FindingObservation.recorded_at.desc(), FindingObservation.id.desc())
        .limit(_MAX_REVIEW_OBSERVATIONS_PER_SCAN + 1)).all()
