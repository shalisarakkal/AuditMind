"""Organization-scoped remediation writes; scoring and source evidence are untouched."""
from datetime import date, datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import func, select
from app.models.archive import ArchiveBatch
from app.models.enums import ArchiveState, UserRole
from app.models.finding import Finding
from app.models.finding_history import FindingHistory
from app.models.membership import OrgMembership
from app.models.user import User
from app.schemas.finding_workflow import HistoryRead, SavedWorkflowNote, WorkflowRead
from app.services.events import actor_label, record_event
from app.services.knowledge_service import KnowledgeError, require_active_org
from app.services.org_lock import lock_org, lock_org_jobs
from app.services.workflow_deadlines import DEADLINE_TIMEZONE, deadline_expiry, deadline_now


def get_finding(db, org_id, finding_id):
    finding = db.scalar(select(Finding).where(Finding.id == finding_id, Finding.org_id == org_id))
    if finding is None:
        raise HTTPException(404, "Finding not found")
    return finding


def assignee_label(db, org_id, user_id):
    if user_id is None:
        return None
    return db.scalar(select(func.coalesce(func.nullif(func.trim(User.name), ""), User.email)).join(OrgMembership, OrgMembership.user_id == User.id).where(
        OrgMembership.org_id == org_id, User.id == user_id, User.is_active.is_(True)))


def read_workflow(db, finding):
    label = assignee_label(db, finding.org_id, finding.assignee_id)
    history = select(FindingHistory).where(FindingHistory.org_id == finding.org_id,
        FindingHistory.finding_id == finding.id).order_by(FindingHistory.version.desc()).limit(1)
    latest = db.scalar(history)
    verified = db.scalar(history.where(FindingHistory.verification.is_not(None), FindingHistory.verification != ""))
    state = _state(finding)
    def note(entry, field):
        return SavedWorkflowNote(text=getattr(entry, field), actor_label=entry.actor_label,
            created_at=entry.created_at) if entry else None
    return WorkflowRead(finding_id=finding.id, status=finding.workflow_status,
        version=finding.workflow_version, assignee_id=finding.assignee_id,
        assignee_available=label is not None, assignee_label=label,
        due_date=finding.due_date, risk_review_date=finding.risk_review_date,
        updated_at=finding.workflow_updated_at, latest_rationale=note(latest, "rationale"),
        latest_verification=note(verified, "verification"), **{
            key: state[key] for key in ("due_timezone", "due_expires_at", "risk_review_timezone", "risk_review_expires_at")})


def read_history(db, entry):
    result = HistoryRead.model_validate(entry)
    for side in ("before", "after"):
        state = getattr(entry, side)
        identifier = state.get("assignee_id")
        label = None
        if identifier:
            label = state.get("assignee_label") or assignee_label(db, entry.org_id, UUID(identifier)) or "Former/unavailable assignee"
        setattr(result, f"{side}_assignee_label", label)
    return result


def _state(finding):
    state = dict(status=finding.workflow_status,
        assignee_id=str(finding.assignee_id) if finding.assignee_id else None,
        due_date=finding.due_date.isoformat() if finding.due_date else None,
        risk_review_date=finding.risk_review_date.isoformat() if finding.risk_review_date else None)
    for prefix in ("due", "risk_review"):
        day = getattr(finding, f"{prefix}_date")
        zone = getattr(finding, f"{prefix}_timezone", None) or (DEADLINE_TIMEZONE if day else None)
        expires = getattr(finding, f"{prefix}_expires_at", None) or (deadline_expiry(day, zone) if day else None)
        state[f"{prefix}_timezone"] = zone
        state[f"{prefix}_expires_at"] = expires.astimezone(timezone.utc).isoformat() if expires else None
    return state


def update_workflows(db, org_id, membership, targets, patch):
    # Same ordering as archive job creation. Also serialize with archive/import chunks.
    lock_org_jobs(db, org_id)
    try:
        require_active_org(db, org_id, lock=True)
    except KnowledgeError as exc:
        raise HTTPException(409, "Organization is read-only or unavailable") from exc
    lock_org(db, org_id)
    # Re-read role under lock; never trust a role cached before a concurrent removal.
    current = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id,
        OrgMembership.user_id == membership.user_id).with_for_update().execution_options(populate_existing=True))
    if current is None or current.role not in (UserRole.admin, UserRole.auditor):
        raise HTTPException(403, "Insufficient permissions")
    ids = sorted((t.finding_id for t in targets), key=str)
    rows = db.scalars(select(Finding).where(Finding.org_id == org_id, Finding.id.in_(ids))
        .order_by(Finding.id).with_for_update().execution_options(populate_existing=True)).all()
    if len(rows) != len(ids) or any(f.archived_at for f in rows):
        raise HTTPException(404, "Finding not found or unavailable")
    affected = {identifier for f in rows for identifier in (f.id, f.asset_id, f.scan_id) if identifier}
    if db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id,
            ArchiveBatch.item_id.in_(affected), ArchiveBatch.state == ArchiveState.archiving).limit(1)):
        raise HTTPException(409, "An affected item is being archived")
    versions = {t.finding_id: t.expected_version for t in targets}
    changes = patch.model_dump(exclude_unset=True, exclude={"rationale", "verification", "expected_version", "deadline_timezone"})
    if "assignee_id" in changes and changes["assignee_id"] is not None:
        # Membership and user locks prevent removal/deactivation racing validation.
        eligible = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id,
            OrgMembership.user_id == changes["assignee_id"]).with_for_update())
        user = db.scalar(select(User).where(User.id == changes["assignee_id"])
            .with_for_update().execution_options(populate_existing=True))
        if eligible is None or user is None or not user.is_active:
            raise HTTPException(422, "Assignee must be an active member of this organization")
    prepared = []
    for finding in rows:
        if finding.workflow_version != versions[finding.id]:
            raise HTTPException(409, dict(code="workflow_conflict", message="Finding changed; reload before retrying"))
        before = _state(finding)
        after = {**before, **{key: value.isoformat() if isinstance(value, date)
            else str(value) if key == "assignee_id" and value is not None else value
            for key, value in changes.items()}}
        for prefix in ("due", "risk_review"):
            key = f"{prefix}_date"
            if key in changes:
                zone = patch.deadline_timezone if changes[key] else None
                try:
                    expires = deadline_expiry(changes[key], zone) if changes[key] else None
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
                # Compare instants: an inclusive local day must contain or follow
                # creation, even when the author's timezone differs from UTC.
                if expires is not None and expires <= finding.created_at:
                    label = "Due date" if prefix == "due" else "Risk review date"
                    raise HTTPException(422, f"{label} cannot be earlier than the finding creation date")
                after[f"{prefix}_timezone"] = zone
                after[f"{prefix}_expires_at"] = expires.isoformat() if expires else None
        changed = before != after
        if (changed or "status" in changes) and "accepted_risk" in (before["status"], after["status"]):
            if current.role != UserRole.admin:
                raise HTTPException(403, "Risk acceptance changes require an organization admin")
        accepting = after["status"] == "accepted_risk" and (changed or "status" in changes)
        if accepting and (not after["risk_review_expires_at"] or datetime.fromisoformat(after["risk_review_expires_at"]) <= deadline_now()):
            raise HTTPException(422, "Accepted risk requires a review date whose end-of-day deadline has not passed")
        if after["status"] != "accepted_risk" and after["risk_review_date"] is not None:
            if "risk_review_date" in changes and changes["risk_review_date"] is not None:
                raise HTTPException(422, "Risk review date only applies to accepted risk")
            after["risk_review_date"] = None
            after["risk_review_timezone"] = None
            after["risk_review_expires_at"] = None
        if before["status"] != after["status"] and after["status"] in ("mitigated", "resolved", "false_positive") and not patch.verification:
            raise HTTPException(422, "This transition requires a verification note")
        prepared.append((finding, before, after))
    for finding, before, after in prepared:
        # Rationale alone is an explicit appended note; version makes retries detectably stale.
        if before == after and changes:
            continue
        finding.workflow_status = after["status"]
        finding.assignee_id = UUID(after["assignee_id"]) if after["assignee_id"] else None
        finding.due_date = date.fromisoformat(after["due_date"]) if after["due_date"] else None
        finding.risk_review_date = date.fromisoformat(after["risk_review_date"]) if after["risk_review_date"] else None
        for prefix in ("due", "risk_review"):
            setattr(finding, f"{prefix}_timezone", after[f"{prefix}_timezone"])
            value = after[f"{prefix}_expires_at"]
            setattr(finding, f"{prefix}_expires_at", datetime.fromisoformat(value) if value else None)
        finding.workflow_version += 1
        finding.workflow_updated_at = datetime.now(timezone.utc)
        db.add(FindingHistory(org_id=org_id, finding_id=finding.id, actor_id=current.user_id,
            actor_label=actor_label(current.user)[:255], version=finding.workflow_version,
            before={**before, "assignee_label": assignee_label(db, org_id, UUID(before["assignee_id"])) if before["assignee_id"] else None},
            after={**after, "assignee_label": assignee_label(db, org_id, UUID(after["assignee_id"])) if after["assignee_id"] else None},
            rationale=patch.rationale, verification=patch.verification))
        record_event(db, "finding_workflow_changed", org_id=org_id, actor=current.user,
            item=str(finding.id), details=dict(finding_id=str(finding.id), version=finding.workflow_version,
                previous_status=before["status"], status=after["status"]))
    db.commit()
    return [read_workflow(db, finding) for finding in rows]
