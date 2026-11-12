"""Transactional retained ledger repository; publication admission belongs to the caller."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import load_only
from app.models.finding_suppression import FindingSuppression, FindingSuppressionDecision
from app.schemas.finding_suppression import SuppressionPage, SuppressionHistoryPage

_REQUEST_LOCK_NAMESPACE = 17


def page(db, org_id, *, state, limit, offset):
    query = select(FindingSuppression).options(load_only(FindingSuppression.id,
        FindingSuppression.identity_version, FindingSuppression.candidate_key, FindingSuppression.finding_id,
        FindingSuppression.version, FindingSuppression.state, FindingSuppression.label,
        FindingSuppression.reappearance_count, FindingSuppression.created_at, FindingSuppression.updated_at)
    ).where(FindingSuppression.org_id == org_id)
    if state != "all": query = query.where(FindingSuppression.state == state)
    rows = db.scalars(query.order_by(FindingSuppression.created_at.desc(), FindingSuppression.id.desc())
        .offset(offset).limit(limit + 1)).all()
    return SuppressionPage(items=rows[:limit], has_more=len(rows) > limit, limit=limit, offset=offset)


def history(db, org_id, suppression_id, *, limit, before_version):
    if db.scalar(select(FindingSuppression.id).where(FindingSuppression.org_id == org_id,
            FindingSuppression.id == suppression_id)) is None:
        raise HTTPException(404, "Suppression record not found")
    query = select(FindingSuppressionDecision).options(load_only(FindingSuppressionDecision.id,
        FindingSuppressionDecision.version, FindingSuppressionDecision.state, FindingSuppressionDecision.rationale,
        FindingSuppressionDecision.actor_label, FindingSuppressionDecision.created_at)).where(
        FindingSuppressionDecision.org_id == org_id, FindingSuppressionDecision.suppression_id == suppression_id)
    if before_version is not None: query = query.where(FindingSuppressionDecision.version < before_version)
    rows = db.scalars(query.order_by(FindingSuppressionDecision.version.desc()).limit(limit + 1)).all()
    return SuppressionHistoryPage(items=rows[:limit], has_more=len(rows) > limit, limit=limit, before_version=before_version)


def append_transition(db, *, org_id, suppression_id, request_id, expected_version, state,
                      rationale, actor_id, actor_label, context, allow_reapply=False):
    if state not in ("suppressed", "cleared") or expected_version < 0:
        raise ValueError("Invalid suppression transition")
    rationale = rationale.strip()
    if not 1 <= len(rationale) <= 2000 or not actor_label.strip():
        raise ValueError("Rationale and actor attribution are required")
    material = dict(suppression_id=str(suppression_id), expected_version=expected_version,
        state=state, rationale=rationale, actor_id=str(actor_id), context=context)
    request_hash = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    key = int.from_bytes(hashlib.sha256(f"{org_id}:{request_id}".encode()).digest()[:4], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(_REQUEST_LOCK_NAMESPACE, key)))
    previous = db.scalar(select(FindingSuppressionDecision).where(FindingSuppressionDecision.org_id == org_id,
        FindingSuppressionDecision.request_id == request_id))
    if previous:
        if previous.request_hash != request_hash: raise HTTPException(409, "Request identifier was already used for a different decision")
        return previous
    with db.begin_nested():
        row = db.scalar(select(FindingSuppression).where(FindingSuppression.org_id == org_id,
            FindingSuppression.id == suppression_id).with_for_update().execution_options(populate_existing=True))
        if row is None: raise HTTPException(404, "Suppression record not found")
        if expected_version == 0:
            existing = db.scalar(select(FindingSuppressionDecision.id).where(FindingSuppressionDecision.org_id == org_id,
                FindingSuppressionDecision.suppression_id == suppression_id).limit(1))
            if row.version != 1 or row.state != "suppressed" or state != "suppressed" or existing:
                raise HTTPException(409, "Suppression changed; reload before retrying")
        elif row.version != expected_version or (row.state == state and not (allow_reapply and state == "suppressed")):
            raise HTTPException(409, "Suppression changed; reload before retrying")
        else:
            db.execute(update(FindingSuppression).where(FindingSuppression.org_id == org_id,
                FindingSuppression.id == suppression_id, FindingSuppression.version == expected_version)
                .values(version=expected_version + 1, state=state, updated_at=datetime.now(timezone.utc)))
        decision = FindingSuppressionDecision(org_id=org_id, suppression_id=suppression_id,
            request_id=request_id, request_hash=request_hash, version=expected_version + 1, state=state,
            rationale=rationale, actor_id=actor_id, actor_label=actor_label, context=context)
        db.add(decision); db.flush()
    return decision
