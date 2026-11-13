"""Stage A metadata transactions, reserved for the future integrated publisher.

No route calls this module. The production entry point fails closed until all
visibility/proof/lifecycle consumers can participate in the same transaction.
Private staging never commits and must not be exposed as a metadata-only writer.
"""
import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased, defer

from app.models.archive import ArchiveBatch, ArchiveJob
from app.models.enums import UserRole
from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_consolidation import (FindingConsolidation, FindingConsolidationDecision,
    FindingConsolidationMember, FindingConsolidationDependency)
from app.models.finding_identity_binding import ObservationIdentityBinding
from app.models.finding_observation import FindingObservation
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services import finding_consolidations
from app.services.consolidation_dependencies import MAX_OBSERVATIONS, manifest
from app.services.events import actor_label
from app.services.finding_identity import IDENTITY_VERSION, NESSUS_MAPPING
from app.services.identity_bindings import identity_reviews
from app.services.org_lock import _key

CONTRACT = "consolidation-metadata-admission-v1"


@contextmanager
def _bounded_lock_wait(db):
    # NOWAIT covers selected rows; unique/FK index conflicts can still wait.
    # Cap those waits too, without weakening or leaking the caller's setting.
    previous = int(db.scalar(text("SELECT setting FROM pg_settings WHERE name='lock_timeout'")))
    limit = min(previous, 750) if previous else 750
    db.scalar(select(func.set_config("lock_timeout", f"{limit}ms", True)))
    try:
        yield
    except BaseException:
        # The enclosing savepoint rolls back both changes and SET LOCAL.
        raise
    else:
        db.scalar(select(func.set_config("lock_timeout", f"{previous}ms", True)))


class MetadataRequest(BaseModel):
    """Internal contract, deliberately absent from HTTP/OpenAPI request schemas."""
    model_config = ConfigDict(extra="forbid")
    canonical_decision_id: uuid.UUID
    request_id: uuid.UUID
    expected_version: int = Field(ge=0, le=2_147_483_646)
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    confirm: bool


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def publish(*args, **kwargs):
    """Retired legacy entry point; client flags never confer publication authority."""
    raise HTTPException(409, "This legacy entry point is unavailable; use the authorized default-off pair publication routes")


def _third_identity_conflict(db, org_id, ids, identity, material):
    binding = ObservationIdentityBinding
    newer = aliased(binding)
    superseded = select(newer.id).where(newer.observation_id == binding.observation_id,
        newer.org_id == org_id, newer.version > binding.version).correlate(binding).exists()
    # Match only server-reviewed normalized material, then revalidate current
    # source context. Historical/revoked/stale decisions confer no authority.
    rows = db.scalars(select(FindingObservation).options(defer(FindingObservation.payload))
        .join(binding, binding.observation_id == FindingObservation.id).where(
            FindingObservation.org_id == org_id, binding.org_id == org_id,
            FindingObservation.finding_id.not_in(ids), binding.state == "bound", ~superseded,
            binding.tool_id == uuid.UUID(identity["tool_id"]),
            binding.canonical_asset_id == uuid.UUID(identity["canonical_asset_id"]),
            binding.context["identity_version"].astext == IDENTITY_VERSION,
            binding.context["source_mapping"].astext == NESSUS_MAPPING,
            binding.context["source_material"] == material)
        .order_by(FindingObservation.id).limit(MAX_OBSERVATIONS + 1)).all()
    if len(rows) > MAX_OBSERVATIONS:
        raise HTTPException(409, "Too many external identity candidates for bounded review")
    for assessment, reviewed in identity_reviews(db, org_id, rows).values():
        if reviewed and reviewed["current"] and assessment["candidate_key"] == identity["candidate_key"]:
            raise HTTPException(409, "Another independently reviewed finding shares this identity; review that conflict first")


def _prepare(db, org_id, actor_id, identifier):
    pair = finding_consolidations._preview(db, org_id, actor_id, identifier)
    if not pair["prerequisites_met"]:
        raise HTTPException(409, dict(message="Pair prerequisites changed or are incomplete", blockers=pair["blockers"]))
    decision = db.get(FindingCanonicalDecision, identifier)
    ids = (decision.finding_a_id, decision.finding_b_id)
    findings = {row.id: row for row in db.scalars(select(Finding).options(defer(Finding.description),
        defer(Finding.raw_data), defer(Finding.details)).where(Finding.org_id == org_id, Finding.id.in_(ids)))}
    observations = db.scalars(select(FindingObservation).options(defer(FindingObservation.payload)).where(
        FindingObservation.org_id == org_id, FindingObservation.finding_id.in_(ids))
        .order_by(FindingObservation.id).limit(MAX_OBSERVATIONS + 1)).all()
    sources = manifest(db, org_id, decision, findings, observations, pair["identity"])
    if sources is None:
        raise HTTPException(409, "Source ownership is unavailable or exceeds the review limit")
    # Resolve native material through a current identity review, not upload claims.
    assessment = identity_reviews(db, org_id, observations[:1])[observations[0].id][0]
    material = assessment["source_material"]
    _third_identity_conflict(db, org_id, ids, pair["identity"], material)
    affected = [uuid.UUID(row["resource_id"]) for row in sources["resources"]
        if row["resource_kind"] in ("finding", "scan", "asset")]
    pending_batches = select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id,
        ArchiveBatch.item_id.in_(affected), ArchiveBatch.state.in_(("archiving", "restoring", "purging"))).exists()
    pending_jobs = select(ArchiveJob.id).join(ArchiveBatch, ArchiveBatch.id == ArchiveJob.batch_id).where(
        ArchiveJob.org_id == org_id, ArchiveBatch.org_id == org_id, ArchiveBatch.item_id.in_(affected),
        ArchiveJob.status.in_(("pending", "running"))).exists()
    importing = select(Scan.id).where(Scan.org_id == org_id, Scan.status.in_(("pending", "running"))).exists()
    if db.scalar(select(or_(pending_batches, pending_jobs, importing))):
        raise HTTPException(409, "An import or affected source lifecycle operation is pending or running")
    recorded = pair["recorded_group"]
    from app.services.consolidation_policy import configuration
    policy=configuration(db,org_id)
    context = dict(contract=CONTRACT, feature_version=policy['version'], feature_enabled=policy['enabled'], org_id=str(org_id), actor_id=str(actor_id),
        canonical_decision_id=str(identifier), pair_key=decision.pair_key,
        expected_version=recorded["version"] if recorded else 0,
        pair_fingerprint=pair["snapshot_fingerprint"], dependency_fingerprint=sources["fingerprint"],
        members=sources["members"], resources=sources["resources"], identity=pair["identity"])
    return dict(context=context, review_token=_digest(context), expected_version=context["expected_version"],
        canonical_decision_id=str(identifier), findings=pair["findings"], apply_available=False)


def metadata_preview(db, org_id, actor_id, identifier):
    """Internal read-only plan; its token is not an enabled publication contract."""
    with db.get_bind().engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
            return _prepare(snapshot, org_id, actor_id, identifier)


def _admit(db, org_id, actor_id):
    # Reuse the audited existing namespaces, in their established order:
    # job admission (two-key namespace 1), then organization publication (one-key).
    org_key = int.from_bytes(org_id.bytes[:4], "big", signed=True)
    if not db.scalar(select(func.pg_try_advisory_xact_lock(1, org_key))):
        raise HTTPException(409, "Organization job admission is busy; retry after the current operation")
    if not db.scalar(select(func.pg_try_advisory_xact_lock(_key(org_id)))):
        raise HTTPException(409, "Inventory publication is busy; retry after the current batch")
    org = db.scalar(select(Organization).where(Organization.id == org_id)
        .with_for_update(key_share=True, nowait=True).execution_options(populate_existing=True))
    member = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id,
        OrgMembership.user_id == actor_id).with_for_update(read=True, nowait=True)
        .execution_options(populate_existing=True))
    actor = db.scalar(select(User).where(User.id == actor_id).with_for_update(read=True, nowait=True)
        .execution_options(populate_existing=True))
    if member is None or member.role != UserRole.admin or actor is None or not actor.is_active or actor.must_change_password:
        raise HTTPException(403, "An active actual organization administrator is required")
    if org is None or org.archived_at is not None or org.purge_requested_at is not None:
        raise HTTPException(409, "Organization is read-only or unavailable")
    return actor


def _receipt(row, replayed):
    return dict(decision_id=str(row.id), consolidation_id=str(row.consolidation_id), version=row.version,
        state=row.state, replayed=replayed, apply_available=False)


def _stage_metadata(db, org_id, actor_id, payload):
    """PRIVATE integration primitive. Atomic savepoint; caller must commit/rollback.

    Nothing in the running application calls this function. Do not expose it
    until visibility, proof, invalidation and lifecycle work joins this transaction.
    """
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, "Complete pending ORM changes before metadata staging")
    if not payload.confirm:
        raise HTTPException(422, "Explicit confirmation is required")
    if db.connection().get_isolation_level() != "READ COMMITTED":
        raise HTTPException(409, "Metadata staging requires a fresh read-committed write transaction")
    request_hash = _digest(dict(actor_id=str(actor_id), org_id=str(org_id), request=payload.model_dump(mode="json")))
    try:
        with db.begin_nested(), _bounded_lock_wait(db):
            actor = _admit(db, org_id, actor_id)
            label = actor_label(actor)
            previous = db.scalar(select(FindingConsolidationDecision).where(
                FindingConsolidationDecision.org_id == org_id, FindingConsolidationDecision.request_id == payload.request_id))
            if previous:
                if previous.request_hash != request_hash:
                    raise HTTPException(409, "Request identifier was already used for a different operation")
                return _receipt(previous, True)
            # Discard cached reads only, after rejecting pending ORM work and
            # fencing admission. All validation below observes current versions.
            db.expire_all()
            decision = db.scalar(select(FindingCanonicalDecision).where(FindingCanonicalDecision.org_id == org_id,
                FindingCanonicalDecision.id == payload.canonical_decision_id))
            if decision is None:
                raise HTTPException(404, "Canonical decision not found")
            ids = sorted((decision.finding_a_id, decision.finding_b_id), key=str)
            locked = db.scalars(select(Finding.id).where(Finding.org_id == org_id, Finding.id.in_(ids))
                .order_by(Finding.id).with_for_update(key_share=True, nowait=True)).all()
            if len(locked) != 2:
                raise HTTPException(409, "Both retained findings are required")
            prepared = _prepare(db, org_id, actor_id, payload.canonical_decision_id)
            if prepared["review_token"] != payload.review_token or prepared["expected_version"] != payload.expected_version:
                raise HTTPException(409, "Admission context changed; reload and review again")
            context = prepared["context"]
            root = db.scalar(select(FindingConsolidation).where(FindingConsolidation.org_id == org_id,
                FindingConsolidation.pair_key == context["pair_key"]).with_for_update(nowait=True))
            if root is not None and (root.version != payload.expected_version or root.state != "undone"):
                raise HTTPException(409, "Consolidation generation changed")
            if db.scalar(select(FindingConsolidationMember.id).where(FindingConsolidationMember.org_id == org_id,
                    FindingConsolidationMember.finding_id.in_(ids)).limit(1)):
                raise HTTPException(409, "A finding already has current membership")
            instant = datetime.now(timezone.utc)
            identity = context["identity"]
            if root is None:
                if payload.expected_version != 0:
                    raise HTTPException(409, "Consolidation generation is unavailable")
                root = FindingConsolidation(org_id=org_id, pair_key=context["pair_key"],
                    finding_a_id=decision.finding_a_id, finding_b_id=decision.finding_b_id,
                    canonical_finding_id=decision.canonical_finding_id, canonical_decision_id=decision.id,
                    identity_version=identity["version"], candidate_key=identity["candidate_key"],
                    tool_id=uuid.UUID(identity["tool_id"]), canonical_asset_id=uuid.UUID(identity["canonical_asset_id"]),
                    version=1, state="active", created_at=instant, updated_at=instant)
                db.add(root)
            else:
                root.version += 1
                root.state, root.updated_at = "active", instant
                root.canonical_finding_id, root.canonical_decision_id = decision.canonical_finding_id, decision.id
                root.identity_version, root.candidate_key = identity["version"], identity["candidate_key"]
                root.tool_id, root.canonical_asset_id = uuid.UUID(identity["tool_id"]), uuid.UUID(identity["canonical_asset_id"])
            db.flush()
            receipt = FindingConsolidationDecision(org_id=org_id, consolidation_id=root.id,
                request_id=payload.request_id, request_hash=request_hash, version=root.version, state="active",
                rationale=payload.rationale, context=context, actor_id=actor_id, actor_label=label)
            db.add(receipt); db.flush()
            db.add_all([FindingConsolidationMember(org_id=org_id, consolidation_id=root.id,
                generation=root.version, finding_id=uuid.UUID(row["finding_id"]), role=row["role"])
                for row in context["members"]])
            db.add_all([FindingConsolidationDependency(org_id=org_id, consolidation_id=root.id,
                generation=root.version, resource_kind=row["resource_kind"], resource_id=uuid.UUID(row["resource_id"]),
                resource_version=row["resource_version"]) for row in context["resources"]])
            db.flush()
            return _receipt(receipt, False)
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) in ("55P03", "23505", "23503"):
            raise HTTPException(409, "Concurrent metadata or source change; reload before retrying") from exc
        raise
