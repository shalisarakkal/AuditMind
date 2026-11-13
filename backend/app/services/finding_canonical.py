"""Reversible canonical designation; original records/histories remain independent.

No importer, score, archive or payload changes. A designation is usable only
after fresh pair validation; it is never authorization for automatic merging.
"""
import hashlib
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import aliased, defer
from app.models.archive import ArchiveBatch
from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision as Decision
from app.models.finding_observation import FindingObservation
from app.models.finding_verification import FindingVerification
from app.models.user import User
from app.services.events import actor_label, record_event
from app.services.finding_workflow import read_workflow
from app.services.identity_comparison import compare_observation
from app.services.org_lock import lock_org


def latest(db, org_id, pair_key):
    return db.scalar(select(Decision).where(Decision.org_id == org_id, Decision.pair_key == pair_key)
        .order_by(Decision.version.desc()).limit(1))


def receipt(row, *, current=None):
    return dict(id=str(row.id), pair_key=row.pair_key, version=row.version, state=row.state, current=current,
        canonical_finding_id=str(row.canonical_finding_id), finding_a_id=str(row.finding_a_id),
        finding_b_id=str(row.finding_b_id), context=row.context, rationale=row.rationale,
        actor_label=row.actor_label, created_at=row.created_at.isoformat())


def _summary(db, org_id, finding, *, excerpt=None, description_hash=None):
    verification = db.scalar(select(FindingVerification).where(FindingVerification.org_id == org_id,
        FindingVerification.finding_id == finding.id).order_by(FindingVerification.version.desc()).limit(1))
    observed = db.execute(select(FindingObservation.id, FindingObservation.recorded_at,
        FindingObservation.filename, FindingObservation.source_row).where(
        FindingObservation.org_id == org_id, FindingObservation.finding_id == finding.id)
        .order_by(FindingObservation.recorded_at.desc(), FindingObservation.id.desc()).limit(1)).one_or_none()
    return dict(id=str(finding.id), category=finding.category,
        description=(finding.description or "")[:2000] if description_hash is None else excerpt,
        description_sha256=hashlib.sha256((finding.description or "").encode()).hexdigest() if description_hash is None else description_hash,
        severity=finding.severity.value, domain=finding.domain.value, source=finding.source,
        asset_id=str(finding.asset_id) if finding.asset_id else None,
        scan_id=str(finding.scan_id) if finding.scan_id else None,
        workflow=read_workflow(db, finding).model_dump(mode="json"),
        verification_version=finding.risk_verification_version,
        verification_state=finding.risk_verification_state,
        verification=dict(version=verification.version, state=verification.state, note=verification.note,
            actor_label=verification.actor_label, created_at=verification.created_at.isoformat(),
            expires_at=verification.expires_at.isoformat() if verification.expires_at else None,
            source_reference=verification.source_reference) if verification else None,
        latest_observation=dict(id=str(observed.id), filename=observed.filename, source_row=observed.source_row,
            recorded_at=observed.recorded_at.isoformat()) if observed else None)


def preview(db, org_id, target, source_id, *, lock=False, bounded=False):
    comparison = compare_observation(db, org_id, target, source_id, **({"bounded": True} if bounded else {}))
    if comparison["result"] != "canonical_conflict" or not comparison["already_reviewed"]:
        raise HTTPException(409, "Two separate findings with independently current matching identity reviews are required")
    identifiers = sorted((comparison["source_finding_id"], comparison["target_finding_id"]))
    pair_key = ":".join(identifiers)
    query = select(Finding).where(Finding.org_id == org_id, Finding.id.in_([uuid.UUID(value) for value in identifiers])).order_by(Finding.id)
    if lock:
        query = query.with_for_update(key_share=True)
    excerpts = {}
    if bounded:
        query = query.add_columns(func.substr(func.coalesce(Finding.description, ""), 1, 2000),
            func.encode(func.sha256(func.convert_to(func.coalesce(Finding.description, ""), "UTF8")), "hex"))
        rows = db.execute(query.options(defer(Finding.raw_data), defer(Finding.details), defer(Finding.description))
            .execution_options(populate_existing=True)).all()
        findings = [row[0] for row in rows]
        excerpts = {row[0].id: dict(excerpt=row[1], description_hash=row[2]) for row in rows}
    else:
        findings = db.scalars(query.options(defer(Finding.raw_data), defer(Finding.details))
            .execution_options(populate_existing=True)).all()
    if len(findings) != 2 or any(row.archived_at is not None or row.suppression_id is not None for row in findings):
        raise HTTPException(409, "Both findings must be active")
    affected = {value for row in findings for value in (row.id, row.asset_id, row.scan_id) if value}
    affected.add(uuid.UUID(comparison["canonical_asset_id"]))
    if db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id,
            ArchiveBatch.item_id.in_(affected), ArchiveBatch.state.in_(("archiving", "restoring", "purging"))).limit(1)):
        raise HTTPException(409, "An affected item has an archive operation in progress")
    # Only an explicit pair is reviewed. Never create chains or overlap another
    # recorded selection; stale overlapping decisions must be explicitly revoked.
    ids = [uuid.UUID(value) for value in identifiers]
    identity = Decision.context.op("->>")(literal_column("'candidate_key'"))
    # Supersession spans ALL contexts, not just matching historical keys. A
    # correlated lookup uses the unique org/pair/version index and returns at
    # most one actual conflict, with no permanent cap on retained old receipts.
    newer = aliased(Decision)
    superseded = select(newer.id).where(newer.org_id == org_id, newer.pair_key == Decision.pair_key,
        newer.version > Decision.version).correlate(Decision).exists()
    conflict = db.execute(select(Decision.id, Decision.canonical_finding_id).where(
        Decision.org_id == org_id, Decision.pair_key != pair_key, Decision.state == "selected",
        or_(Decision.finding_a_id.in_(ids), Decision.finding_b_id.in_(ids),
            identity == comparison["candidate_key"], identity.is_(None)), ~superseded)
        .order_by(Decision.pair_key, Decision.version.desc()).limit(1)).one_or_none()
    if conflict is not None:
        raise HTTPException(409, dict(code="canonical_conflict",
            message="A finding or native identity already participates in another canonical selection; review and revoke it first",
            decision_id=str(conflict.id), canonical_finding_id=str(conflict.canonical_finding_id)))
    previous = latest(db, org_id, pair_key)
    context = dict(contract="canonical-selection-v1", identity_token=comparison["review_token"],
        candidate_key=comparison["candidate_key"], findings=[_summary(db, org_id, row, **excerpts.get(row.id, {})) for row in findings])
    version = previous.version if previous else 0
    token = hashlib.sha256(json.dumps(dict(context=context, pair_key=pair_key, version=version),
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return dict(pair_key=pair_key, context=context, expected_version=version, review_token=token,
        saved=receipt(previous, current=previous.state == "selected" and previous.context == context) if previous else None)


def save(db, org_id, target, actor_id, payload):
    if not payload.confirm_histories:
        raise HTTPException(422, "Confirm review of both findings and their independent histories")
    # Imports use this lock while publishing findings and observations. Hold it
    # through the final context check and receipt commit so a later observation
    # cannot appear between preview validation and publication.
    lock_org(db, org_id)
    from app.services.consolidation_lifecycle import ensure_free
    ensure_free(db,org_id,'observation',target.id)
    ensure_free(db,org_id,'observation',payload.source_observation_id)
    prepared = preview(db, org_id, target, payload.source_observation_id, lock=True)
    if prepared["review_token"] != payload.review_token or prepared["expected_version"] != payload.expected_version:
        raise HTTPException(409, "Canonical review context changed; reload and review again")
    ids = [row["id"] for row in prepared["context"]["findings"]]
    if str(payload.canonical_finding_id) not in ids:
        raise HTTPException(422, "Choose one of the two reviewed findings")
    saved = prepared["saved"]
    if saved and saved["current"] and saved["canonical_finding_id"] == str(payload.canonical_finding_id):
        raise HTTPException(409, "This canonical selection is already current")
    actor = db.get(User, actor_id)
    row = Decision(org_id=org_id, pair_key=prepared["pair_key"], finding_a_id=uuid.UUID(ids[0]), finding_b_id=uuid.UUID(ids[1]),
        canonical_finding_id=payload.canonical_finding_id, source_observation_id=payload.source_observation_id,
        target_observation_id=target.id, version=payload.expected_version + 1, state="selected",
        context=prepared["context"], rationale=payload.rationale, actor_id=actor_id, actor_label=actor_label(actor))
    # Recheck after preparation; never silently capture a host/workflow different
    # from the displayed preview. Persist the reviewed snapshot, not a new one.
    checked = preview(db, org_id, target, payload.source_observation_id)
    if checked["review_token"] != payload.review_token:
        raise HTTPException(409, "Canonical context changed during save; review again")
    db.add(row)
    db.flush()
    record_event(db, "finding_canonical_selected", org_id=org_id, actor=actor,
        item=str(payload.canonical_finding_id), details=dict(pair_key=row.pair_key, version=row.version,
            finding_id=str(row.canonical_finding_id), decision_id=str(row.id),
            canonical_finding_id=str(row.canonical_finding_id), rationale=payload.rationale))
    db.commit()
    return receipt(row)


def revoke(db, org_id, decision_id, actor_id, payload):
    lock_org(db,org_id)
    from app.services.consolidation_lifecycle import ensure_free
    ensure_free(db,org_id,'canonical_decision',decision_id)
    row = db.scalar(select(Decision).where(Decision.org_id == org_id, Decision.id == decision_id))
    if row is None:
        raise HTTPException(404, "Canonical decision not found")
    current = latest(db, org_id, row.pair_key)
    if current.id != row.id or current.version != payload.expected_version or current.state != "selected":
        raise HTTPException(409, "Canonical decision changed; reload before retrying")
    actor = db.get(User, actor_id)
    decision = Decision(org_id=org_id, pair_key=row.pair_key, finding_a_id=row.finding_a_id,
        finding_b_id=row.finding_b_id, canonical_finding_id=row.canonical_finding_id,
        source_observation_id=row.source_observation_id, target_observation_id=row.target_observation_id,
        version=row.version + 1, state="revoked", context=row.context, rationale=payload.rationale,
        actor_id=actor_id, actor_label=actor_label(actor))
    db.add(decision)
    db.flush()
    record_event(db, "finding_canonical_revoked", org_id=org_id, actor=actor, item=str(row.canonical_finding_id),
        details=dict(pair_key=row.pair_key, version=decision.version, finding_id=str(row.canonical_finding_id),
            decision_id=str(decision.id), rationale=payload.rationale))
    db.commit()
    return receipt(decision, current=False)
