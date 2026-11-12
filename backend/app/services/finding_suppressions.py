"""Reviewed suppression publication, safe source retention and reappearance review."""
import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased, defer, load_only
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import ObservationIdentityBinding
from app.models.finding_suppression import (FindingSuppression, FindingSuppressionDecision,
    OrganizationSuppressionRevision, FindingSuppressionReappearance)
from app.models.evidence_evaluation import OrganizationEvidenceRevision
from app.models.archive import ArchiveBatch
from app.models.asset import Asset
from app.models.scan import Scan
from app.models.membership import OrgMembership
from app.models.enums import UserRole
from app.models.user import User
from app.models.dashboard_snapshot import DashboardSnapshot
from app.services.identity_bindings import identity_reviews
from app.services.finding_identity import IDENTITY_VERSION, NESSUS_MAPPING, assess_identity
from app.services.events import actor_label, record_event
from app.services.knowledge_service import KnowledgeError, require_active_org
from app.services.org_lock import lock_org, lock_org_jobs
from app.services.suppression_repository import append_transition, page, history  # noqa: F401

_MAX_OBSERVATIONS = 1000


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def revision(db, org_id):
    return db.scalar(select(OrganizationSuppressionRevision.revision).where(OrganizationSuppressionRevision.org_id == org_id)) or 0


def _retained_finding(db, org_id, identifier, *, lock=False):
    query = select(Finding, func.substr(Finding.description, 1, 500),
        func.encode(func.sha256(func.convert_to(func.coalesce(Finding.description, ""), "UTF8")), "hex"))
    query = query.options(defer(Finding.raw_data), defer(Finding.details), defer(Finding.description)).where(
        Finding.org_id == org_id, Finding.id == identifier)
    if lock: query = query.with_for_update()
    row = db.execute(query.execution_options(populate_existing=True)).one_or_none()
    if row is None: return None
    finding, label, fingerprint = row
    finding._suppression_label = label or finding.category or "Finding"
    finding._suppression_description_hash = fingerprint
    return finding


def _lifecycle(db, org_id, finding):
    if finding is None: return dict(state="purged", finding_id=None)
    asset = db.get(Asset, finding.asset_id, populate_existing=True) if finding.asset_id else None
    scan = db.get(Scan, finding.scan_id, populate_existing=True) if finding.scan_id else None
    affected = {v for v in (finding.id, finding.asset_id, finding.scan_id) if v}
    if db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id, ArchiveBatch.item_id.in_(affected),
            ArchiveBatch.state.in_(("archiving", "restoring", "purging"))).limit(1)):
        raise HTTPException(409, "An affected item has an archive operation in progress")
    def stamp(value): return value.isoformat() if value else None
    return dict(state="archived" if finding.archived_at or (asset and asset.archived_at) or (scan and scan.archived_at) else "retained",
        finding_id=str(finding.id), workflow_version=finding.workflow_version, workflow_status=finding.workflow_status,
        verification_version=finding.risk_verification_version,
        suppression_id=str(finding.suppression_id) if finding.suppression_id else None,
        archive_batch_id=str(finding.archive_batch_id) if finding.archive_batch_id else None,
        finding_archived_at=stamp(finding.archived_at), asset_archived_at=stamp(asset.archived_at) if asset else None,
        scan_archived_at=stamp(scan.archived_at) if scan else None,
        asset_id=str(finding.asset_id) if finding.asset_id else None, scan_id=str(finding.scan_id) if finding.scan_id else None,
        description_hash=finding._suppression_description_hash, severity=finding.severity.value, domain=finding.domain.value)


def _trusted_identity(db, org_id, finding):
    observations = db.scalars(select(FindingObservation).options(defer(FindingObservation.payload)).where(
        FindingObservation.org_id == org_id, FindingObservation.finding_id == finding.id)
        .order_by(FindingObservation.recorded_at, FindingObservation.id).limit(_MAX_OBSERVATIONS + 1)).all()
    if not observations or len(observations) > _MAX_OBSERVATIONS:
        raise HTTPException(409, "Suppression requires 1-1000 retained, independently reviewed native Nessus observations")
    reviews = identity_reviews(db, org_id, observations)
    keys = {value[0].get("candidate_key") for value in reviews.values()}
    if None in keys or len(keys) != 1 or any(not v[1] or not v[1]["current"] for v in reviews.values()):
        raise HTTPException(409, "Review every retained observation's native Nessus tool and canonical asset identity before suppression")
    assessment, binding = reviews[observations[0].id]
    if assessment["version"] != IDENTITY_VERSION or assessment["mapping"] != NESSUS_MAPPING:
        raise HTTPException(409, "Only the reviewed native Nessus identity mapping is supported")
    newer = aliased(ObservationIdentityBinding)
    conflict = db.scalar(select(FindingObservation.id).join(ObservationIdentityBinding,
        ObservationIdentityBinding.observation_id == FindingObservation.id).join(Finding,
        Finding.id == FindingObservation.finding_id).where(ObservationIdentityBinding.org_id == org_id,
        FindingObservation.org_id == org_id, Finding.org_id == org_id, Finding.active(), Finding.id != finding.id,
        ObservationIdentityBinding.tool_id == uuid.UUID(binding["tool_id"]),
        ObservationIdentityBinding.canonical_asset_id == uuid.UUID(binding["canonical_asset_id"]),
        ObservationIdentityBinding.state == "bound", ObservationIdentityBinding.context["source_material"] == assessment["source_material"],
        ~select(newer.id).where(newer.observation_id == ObservationIdentityBinding.observation_id,
            newer.org_id == org_id, newer.version > ObservationIdentityBinding.version).exists()).limit(1))
    if conflict: raise HTTPException(409, "Another active finding has a matching reviewed identity; resolve the canonical conflict before suppression")
    from app.models.finding_canonical import FindingCanonicalDecision
    later = aliased(FindingCanonicalDecision)
    chosen_elsewhere = db.scalar(select(FindingCanonicalDecision.id).where(FindingCanonicalDecision.org_id == org_id,
        FindingCanonicalDecision.state == "selected", FindingCanonicalDecision.canonical_finding_id != finding.id,
        FindingCanonicalDecision.context["candidate_key"].astext == assessment["candidate_key"],
        ~select(later.id).where(later.org_id == org_id, later.pair_key == FindingCanonicalDecision.pair_key,
            later.version > FindingCanonicalDecision.version).exists()).limit(1))
    if chosen_elsewhere: raise HTTPException(409, "A current canonical designation selects another finding; review and revoke that conflict before suppression")
    identity = dict(version=assessment["version"], mapping=assessment["mapping"], candidate_key=assessment["candidate_key"],
        tool_id=binding["tool_id"], tool_name=binding["tool_name"], canonical_asset_id=binding["canonical_asset_id"],
        source_asset_id=observations[0].asset_identity.get("asset_id"), source_material=assessment["source_material"])
    stamp = _digest([dict(id=str(o.id), binding_version=reviews[o.id][1]["version"],
        recorded_at=o.recorded_at, import_id=str(o.import_id)) for o in observations])
    return identity, stamp


def preview(db, org_id, target, *, lock=False):
    registry = None
    if target.action == "clear":
        query = select(FindingSuppression).where(FindingSuppression.org_id == org_id, FindingSuppression.id == target.suppression_id)
        if lock: query = query.with_for_update()
        registry = db.scalar(query.execution_options(populate_existing=True))
        if registry is None: raise HTTPException(404, "Suppression record not found")
        if registry.state != "suppressed": raise HTTPException(409, "This suppression is already cleared")
        finding = _retained_finding(db, org_id, registry.finding_id, lock=lock)
        other_retained = db.scalar(select(Finding.id).where(Finding.org_id == org_id,
            Finding.suppression_id == registry.id, Finding.id != registry.finding_id,
            Finding.archived_at.is_(None)).limit(1))
        if other_retained:
            raise HTTPException(409, "Another retained payload shares this suppression identity; archive the additional source or resolve the canonical conflict before clearing")
        life = _lifecycle(db, org_id, finding)
        identity, observation_stamp = registry.identity, None
        if finding:
            if finding.suppression_id != registry.id: raise HTTPException(409, "Finding disposition changed; reload before clearing")
            duplicate = db.scalar(select(Finding.id).where(Finding.org_id == org_id, Finding.id != finding.id, Finding.active(),
                Finding.asset_id.is_not_distinct_from(finding.asset_id), Finding.source == finding.source,
                Finding.category.is_not_distinct_from(finding.category),
                True if finding.category is not None else Finding.description.is_not_distinct_from(finding.description)).limit(1))
            if duplicate: raise HTTPException(409, "Another active finding may duplicate the retained payload; resolve the canonical/source conflict before clearing")
    else:
        finding = _retained_finding(db, org_id, target.finding_id, lock=lock)
        if finding is None: raise HTTPException(404, "Finding not found")
        life = _lifecycle(db, org_id, finding)
        if life["state"] != "retained" or finding.suppression_id:
            raise HTTPException(409, "Choose a retained active finding that is not already suppressed")
        identity, observation_stamp = _trusted_identity(db, org_id, finding)
        query = select(FindingSuppression).where(FindingSuppression.org_id == org_id,
            FindingSuppression.identity_version == identity["version"], FindingSuppression.candidate_key == identity["candidate_key"])
        if lock: query = query.with_for_update()
        registry = db.scalar(query.execution_options(populate_existing=True))
        if registry and registry.finding_id != finding.id:
            former = _retained_finding(db, org_id, registry.finding_id, lock=lock)
            if former and _lifecycle(db, org_id, former)["state"] == "retained":
                raise HTTPException(409, "The prior suppressed finding is still retained; resolve its canonical/source lifecycle before applying this identity to another record")
    context = dict(contract="reviewed-suppression-v1", org_id=str(org_id), action=target.action,
        target_finding_id=str(finding.id) if finding else str(registry.finding_id), lifecycle=life, identity=identity,
        observations=observation_stamp, suppression_id=str(registry.id) if registry else None,
        version=registry.version if registry else 0, reappearances=registry.reappearance_count if registry else 0,
        label=finding._suppression_label[:500] if finding else registry.label)
    return dict(action=target.action, finding_id=context["target_finding_id"], suppression_id=context["suppression_id"],
        expected_version=context["version"], review_token=_digest(context), label=context["label"], lifecycle=life["state"],
        finding_status=life.get("workflow_status"), identity=identity, context=context)


def _admit(db, org_id, member, action):
    lock_org_jobs(db, org_id)
    def busy(): raise HTTPException(409, "Inventory publication is busy; retry this decision after the current write batch")
    lock_org(db, org_id, on_wait=busy)
    try: require_active_org(db, org_id, lock=True)
    except KnowledgeError as exc: raise HTTPException(409, "Organization is read-only or unavailable") from exc
    current = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id, OrgMembership.user_id == member.user_id)
        .with_for_update(read=True).execution_options(populate_existing=True))
    roles = (UserRole.admin,) if action == "clear" else (UserRole.admin, UserRole.auditor)
    if current is None or current.role not in roles: raise HTTPException(403, "Insufficient permissions")
    actor = db.scalar(select(User).where(User.id == current.user_id).with_for_update(read=True).execution_options(populate_existing=True))
    if actor is None or not actor.is_active: raise HTTPException(403, "Account is unavailable")
    return current


def _invalidate(db, org_id):
    for model in (OrganizationSuppressionRevision, OrganizationEvidenceRevision):
        db.execute(insert(model).values(org_id=org_id, revision=1).on_conflict_do_update(
            index_elements=[model.org_id], set_={"revision": model.revision + 1}))
    from app.services.dashboard_snapshots import configuration
    if configuration(db).enabled:
        instant = datetime.now(timezone.utc)
        db.execute(insert(DashboardSnapshot).values(id=uuid.uuid4(), org_id=org_id, status="pending", requested_at=instant,
            retry_count=0).on_conflict_do_update(index_elements=[DashboardSnapshot.org_id], set_={"payload":None,
                "status":case((DashboardSnapshot.status == "running", "running"), else_="pending"),
                "requested_at":instant, "error_message":None}))
    else: db.execute(update(DashboardSnapshot).where(DashboardSnapshot.org_id == org_id).values(payload=None))


def decide(db, org_id, member, payload):
    current = _admit(db, org_id, member, payload.action)
    if not payload.confirm: raise HTTPException(422, "Confirm the reviewed finding and visibility consequences")
    digest = _digest(dict(org_id=str(org_id), actor_id=str(current.user_id), request=payload.model_dump(mode="json")))
    previous = db.scalar(select(FindingSuppressionDecision).where(FindingSuppressionDecision.org_id == org_id,
        FindingSuppressionDecision.request_id == payload.request_id))
    if previous:
        if previous.context.get("request_digest") != digest: raise HTTPException(409, "Request identifier was already used for a different operation")
        return dict(decision_id=str(previous.id), suppression_id=str(previous.suppression_id), version=previous.version, state=previous.state, replayed=True)
    with db.begin_nested():
        prepared = preview(db, org_id, payload, lock=True)
        if prepared["review_token"] != payload.review_token or prepared["expected_version"] != payload.expected_version:
            raise HTTPException(409, "Finding, identity or suppression context changed; reload the preview before retrying")
        finding = _retained_finding(db, org_id, uuid.UUID(prepared["finding_id"]), lock=True)
        registry = db.get(FindingSuppression, uuid.UUID(prepared["suppression_id"])) if prepared["suppression_id"] else None
        if registry is None:
            identity = prepared["identity"]
            registry = FindingSuppression(org_id=org_id, identity_version=identity["version"], candidate_key=identity["candidate_key"],
                identity=identity, source_fingerprint=_source_fingerprint(identity["source_asset_id"], identity["source_material"]),
                finding_id=finding.id, label=prepared["label"], version=1, state="suppressed")
            db.add(registry); db.flush()
        state = "suppressed" if payload.action == "suppress" else "cleared"
        decision = append_transition(db, org_id=org_id, suppression_id=registry.id, request_id=payload.request_id,
            expected_version=payload.expected_version, state=state, rationale=payload.rationale, actor_id=current.user_id,
            actor_label=actor_label(db.get(User, current.user_id)),
            context={**prepared["context"], "request_digest":digest},
            allow_reapply=payload.action == "suppress" and payload.expected_version > 0)
        if payload.action == "suppress":
            registry.finding_id, registry.label = finding.id, prepared["label"]
            # An explicitly reviewed source alias may retain the same canonical
            # key. Track its current source for future possible-reappearance
            # receipts; prior source material remains in decision history.
            registry.identity = prepared["identity"]
            registry.source_fingerprint = _source_fingerprint(prepared["identity"]["source_asset_id"],
                prepared["identity"]["source_material"])
            finding.suppression_id = finding.suppression_history_id = registry.id
        else:
            db.execute(update(Finding).where(Finding.org_id == org_id, Finding.suppression_id == registry.id).values(suppression_id=None))
        db.flush(); _invalidate(db, org_id)
        record_event(db, "finding_suppressed" if payload.action == "suppress" else "finding_suppression_cleared",
            org_id=org_id, actor=db.get(User, current.user_id), item=prepared["label"], details=dict(finding_id=prepared["finding_id"],
                suppression_id=str(registry.id), version=decision.version, rationale=payload.rationale, payload_state=prepared["lifecycle"]))
    db.commit()
    return dict(decision_id=str(decision.id), suppression_id=str(registry.id), version=decision.version, state=state, replayed=False)


def _source_fingerprint(asset_id, material):
    return _digest(dict(source_asset_id=str(asset_id), mapping=NESSUS_MAPPING, material=material))


def record_reappearances(db, org_id, observations):
    """One indexed lookup per native batch; never binds or hides a new upload."""
    candidates = {}
    for row in observations:
        if row["scan_type"] != "nessus" or row["source"] != "nessus" or row.get("profile") is not None: continue
        assessment = assess_identity(org_id=org_id, scan_type=row["scan_type"], source=row["source"], profile=row.get("profile"), raw=row["source_identity"])
        if assessment.mapping != NESSUS_MAPPING or set(assessment.blocking_reasons) - {"source_instance_not_configured", "stable_asset_mapping_not_verified"}: continue
        asset_id = row["asset_identity"].get("asset_id")
        if asset_id: candidates[row["id"]] = (_source_fingerprint(asset_id, assessment.source_material), row)
    if not candidates: return
    registries = db.scalars(select(FindingSuppression).options(
        load_only(FindingSuppression.id, FindingSuppression.source_fingerprint)).where(FindingSuppression.org_id == org_id,
        FindingSuppression.state == "suppressed", FindingSuppression.source_fingerprint.in_({v[0] for v in candidates.values()}))).all()
    lookup = {}
    for registry in registries: lookup.setdefault(registry.source_fingerprint, []).append(registry)
    receipts = [dict(id=uuid.uuid4(), org_id=org_id, suppression_id=registry.id, observation_id=row["id"], finding_id=row["finding_id"],
        scan_id=row.get("scan_id"), filename=row.get("filename"), created_at=row["recorded_at"])
        for fingerprint, row in candidates.values() for registry in lookup.get(fingerprint, [])]
    if not receipts: return
    totals = Counter()
    for start in range(0, len(receipts), 500):
        changed = db.scalars(insert(FindingSuppressionReappearance).values(receipts[start:start+500]).on_conflict_do_nothing(
            constraint="uq_suppression_reappearance").returning(FindingSuppressionReappearance.suppression_id)).all()
        totals.update(changed)
    for identifier, count in totals.items():
        db.execute(update(FindingSuppression).where(FindingSuppression.org_id == org_id, FindingSuppression.id == identifier)
            .values(reappearance_count=FindingSuppression.reappearance_count + count))


def reappearances(db, org_id, identifier, *, limit, offset):
    if not db.scalar(select(FindingSuppression.id).where(FindingSuppression.org_id == org_id, FindingSuppression.id == identifier)):
        raise HTTPException(404, "Suppression record not found")
    rows = db.scalars(select(FindingSuppressionReappearance).where(FindingSuppressionReappearance.org_id == org_id,
        FindingSuppressionReappearance.suppression_id == identifier).order_by(FindingSuppressionReappearance.created_at.desc(),
        FindingSuppressionReappearance.id.desc()).limit(limit + 1).offset(offset)).all()
    return dict(items=[dict(id=str(r.id), finding_id=str(r.finding_id), observation_id=str(r.observation_id),
        scan_id=str(r.scan_id) if r.scan_id else None, filename=r.filename, created_at=r.created_at, state="needs_identity_review")
        for r in rows[:limit]], has_more=len(rows) > limit, limit=limit, offset=offset)
