"""Stage B read-only admission. No publication writer or write-authorizing token."""
import uuid
from fastapi import HTTPException
from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.orm import Session, defer

from app.models.archive import ArchiveBatch, AssetScan
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_suppression import FindingSuppression
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services.finding_identity import IDENTITY_VERSION, assess_identity
from app.services.identity_bindings import identity_reviews, _source_asset
from app.services import observation_payload as contract

PREVIEW_CONTRACT = "observation-publication-preview-v1"


def blocked(message):
    raise HTTPException(409, message)


def _check_actor(db, org_id, actor_id):
    actor = db.execute(select(User.is_active, User.must_change_password, User.password_changed_at)
        .where(User.id == actor_id)).one_or_none()
    member = db.scalar(select(OrgMembership.role).where(OrgMembership.org_id == org_id,
        OrgMembership.user_id == actor_id))
    if actor is None or not actor.is_active or actor.must_change_password or member != "admin":
        raise HTTPException(403, "An active actual organization administrator is required")
    org = db.execute(select(Organization.archived_at, Organization.purge_requested_at)
        .where(Organization.id == org_id)).one_or_none()
    if org is None or org.archived_at is not None or org.purge_requested_at is not None:
        blocked("Organization is read-only or unavailable")
    return actor


def _prepare(db, org_id, actor_id, finding_id, observation_id, *, _private=False, _require_latest=True):
    actor = _check_actor(db, org_id, actor_id)
    finding = db.scalar(select(Finding).options(defer(Finding.description), defer(Finding.raw_data),
        defer(Finding.details)).where(Finding.org_id == org_id, Finding.id == finding_id))
    if finding is None:
        raise HTTPException(404, "Finding not found")
    if finding.archived_at is not None or finding.suppression_id is not None or finding.consolidation_id is not None:
        blocked("An active, unsuppressed, non-consolidated finding is required")
    if finding.source != "nessus" or finding.event_count is not None:
        blocked("Only ordinary native Nessus findings support payload review")
    if finding.risk_verification_state == "approved":
        blocked("Explicitly revoke approved scoring evidence before reviewing publication")
    observation = db.scalar(select(FindingObservation).options(defer(FindingObservation.payload)).where(
        FindingObservation.org_id == org_id, FindingObservation.finding_id == finding_id,
        FindingObservation.id == observation_id))
    if observation is None:
        raise HTTPException(404, "Observation not found on this finding")
    if observation.scan_type != "nessus" or observation.source != "nessus" or observation.profile is not None:
        blocked("Only the strict native Nessus mapping supports payload review")
    if not isinstance(observation.source_identity, dict) or not isinstance(observation.asset_identity, dict):
        blocked("Retained native source/asset identity is malformed")
    if _require_latest:
        latest = db.execute(select(FindingObservation.id, FindingObservation.recorded_at).where(
            FindingObservation.org_id == org_id, FindingObservation.finding_id == finding_id)
            .order_by(FindingObservation.recorded_at.desc(), FindingObservation.id.desc()).limit(2)).all()
        if len(latest) > 1 and latest[0].recorded_at == latest[1].recorded_at:
            blocked("Latest observations have ambiguous equal server-recorded times")
        if latest[0].id != observation.id:
            blocked("Select the latest server-recorded observation; newer retained context exists")
    stamp, size = db.execute(select(FindingObservation.payload[contract.MAPPING_KEY].astext,
        func.octet_length(cast(FindingObservation.payload, Text))).where(
            FindingObservation.org_id == org_id, FindingObservation.id == observation_id)).one()
    if stamp != contract.MAPPING_VERSION:
        blocked("Observation is unversioned or uses an unsupported payload mapping; a new native import is required")
    if size > contract.MAX_BYTES:
        blocked("Observation payload exceeds the 16 MiB review limit")
    assessment, binding = identity_reviews(db, org_id, [observation])[observation.id]
    if not binding or not binding["current"] or not assessment["candidate_key"]:
        blocked("Selected observation needs a current independently reviewed scanner and canonical asset")
    if db.scalar(select(FindingSuppression.id).where(FindingSuppression.org_id == org_id,
            FindingSuppression.identity_version == IDENTITY_VERSION,
            FindingSuppression.candidate_key == assessment["candidate_key"],
            FindingSuppression.state == "suppressed").limit(1)):
        blocked("Clear the standing identity suppression before publication review")
    asset_ids = {finding.asset_id, _source_asset(observation), uuid.UUID(binding["canonical_asset_id"])}
    if None in asset_ids:
        blocked("Retained source and canonical asset ownership is required")
    assets = db.execute(select(Asset.id, Asset.hostname, Asset.ip, Asset.cloud_id, Asset.type,
        Asset.archived_at).where(Asset.org_id == org_id, Asset.id.in_(asset_ids))).all()
    if len(assets) != len(asset_ids) or any(row.archived_at is not None for row in assets):
        blocked("Every original, observation and canonical asset must remain active")
    creators = db.execute(select(AssetScan.asset_id, AssetScan.scan_id).where(AssetScan.asset_id.in_(asset_ids),
        AssetScan.created.is_(True)).order_by(AssetScan.asset_id, AssetScan.scan_id).limit(101)).all()
    if len(creators) > 100:
        blocked("Source ownership exceeds the bounded review limit")
    scan_ids = {finding.scan_id, observation.scan_id, *(row.scan_id for row in creators)}
    if None in scan_ids or observation.import_id != observation.scan_id:
        blocked("Retained original and observation scan ownership is required")
    scans = db.execute(select(Scan.id, Scan.filename, Scan.scan_type, Scan.profile,
        Scan.ingestion_config_fingerprint, Scan.content_hash, Scan.status, Scan.archived_at).where(
            Scan.org_id == org_id, Scan.id.in_(scan_ids))).all()
    if len(scans) != len(scan_ids) or any(row.archived_at is not None or row.status != "completed" for row in scans):
        blocked("Every source scan, including asset creators, must remain active and completed")
    original = next(row for row in scans if row.id == finding.scan_id)
    selected = next(row for row in scans if row.id == observation.scan_id)
    if any(row.scan_type != "nessus" or row.profile is not None for row in (original, selected)):
        blocked("Original and selected observation ownership must be native Nessus scans")
    affected = {*scan_ids, *asset_ids, finding_id}
    if db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id,
            ArchiveBatch.item_id.in_(affected), ArchiveBatch.state.in_(("archiving", "restoring", "purging"))).limit(1)):
        blocked("An affected source has an unfinished archive, restore or purge operation")
    if db.scalar(select(Scan.id).where(Scan.org_id == org_id, Scan.status.in_(("pending", "running"))).limit(1)):
        blocked("An import is pending or running; review after publication settles")
    current_size = db.scalar(select(func.coalesce(func.octet_length(Finding.description), 0)
        + func.coalesce(func.octet_length(cast(Finding.raw_data, Text)), 0)
        + func.coalesce(func.octet_length(cast(Finding.details, Text)), 0)).where(
            Finding.org_id == org_id, Finding.id == finding_id))
    if current_size > contract.MAX_BYTES:
        blocked("Current scanner fields exceed the 16 MiB review limit")
    try:
        replacement, material = contract.validate(observation.payload, org_id=org_id,
            source_identity=observation.source_identity)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        blocked(f"Unsupported observation payload: {error}")
    if observation.payload["domain"] != finding.domain.value or observation.payload["category"] != finding.category:
        blocked("Domain/category changes require a separate publication design")
    if not isinstance(finding.raw_data, dict):
        blocked("Current scanner payload has no supported native identity")
    current_material = assess_identity(org_id=org_id, scan_type="nessus", source="nessus",
        profile=None, raw=finding.raw_data).source_material
    if len(current_material) != 3 or material != current_material:
        blocked("Observation changes the current finding's native plugin/port/protocol identity")
    before = {field: getattr(finding, field) for field in contract.FIELDS}
    before["severity"] = finding.severity.value
    for field in ("first_seen", "last_seen"):
        before[field] = contract.timestamp(before[field].isoformat()) if before[field] else None
    changes = [dict(field=field, before=contract.summary(before[field]), after=contract.summary(replacement[field]),
        removal=replacement[field] is None and before[field] is not None)
        for field in contract.FIELDS if contract.digest(before[field]) != contract.digest(replacement[field])]
    observation_context = dict(import_id=str(observation.import_id), scan_id=str(observation.scan_id),
        occurrence=observation.occurrence, source_row=observation.source_row, source=observation.source,
        scan_type=observation.scan_type, profile=observation.profile, filename=observation.filename,
        asset_identity=observation.asset_identity, source_identity=observation.source_identity)
    context = dict(contract=PREVIEW_CONTRACT, org_id=str(org_id), actor_id=str(actor_id),
        actor_password_changed_at=str(actor.password_changed_at), finding_id=str(finding_id),
        observation_id=str(observation_id), mapping_version=stamp, native_identity=material,
        candidate_key=assessment["candidate_key"], identity_binding=binding,
        current_sha256=contract.digest(before), observation_sha256=contract.digest(observation.payload),
        observation_context_sha256=contract.digest(observation_context),
        creator_links=[dict(asset_id=str(row.asset_id), scan_id=str(row.scan_id)) for row in creators],
        workflow_version=finding.workflow_version, verification_version=finding.risk_verification_version,
        verification_state=finding.risk_verification_state,
        recorded_at=observation.recorded_at.isoformat(), observed_at=observation.observed_at.isoformat() if observation.observed_at else None,
        original_scan_id=str(finding.scan_id), original_asset_id=str(finding.asset_id),
        original_created_at=finding.created_at.isoformat() if finding.created_at else None,
        assets=[{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row._mapping.items()} for row in sorted(assets, key=lambda r:r.id)],
        scans=[{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row._mapping.items()} for row in sorted(scans, key=lambda r:r.id)])
    result = dict(preview_contract=PREVIEW_CONTRACT, mapping_version=stamp, review_token=contract.digest(context),
        publish_available=False, apply_available=False, no_op=not changes, changes=changes,
        current_sha256=context["current_sha256"], observation_sha256=context["observation_sha256"],
        observation_context_sha256=context["observation_context_sha256"],
        fixed_fields=dict(domain=finding.domain.value, category=finding.category, source=finding.source, native_identity=material),
        provenance=dict(original_scan_id=str(finding.scan_id), original_asset_id=str(finding.asset_id),
            original_filename=original.filename, original_created_at=context["original_created_at"], observation_id=str(observation.id),
            observation_scan_id=str(observation.scan_id), observation_filename=observation.filename,
            original_file_sha256=original.content_hash, observation_file_sha256=selected.content_hash,
            recorded_at=context["recorded_at"], observed_at=context["observed_at"]),
        workflow=dict(status=finding.workflow_status, version=finding.workflow_version, preserved=True),
        message="Read-only preview. No scanner fields, ownership, workflow, proof or scores were changed. This token does not authorize publication. Latest server recording does not prove latest scanner time.")
    if _private:
        result['_transaction'] = dict(before=before, after=replacement, context=context)
    return result


def preview(db, org_id, actor_id, finding_id, observation_id):
    if db.new or db.dirty or db.deleted:
        blocked("Complete pending database changes before preview")
    with db.get_bind().engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
            snapshot.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            return _prepare(snapshot, org_id, actor_id, finding_id, observation_id)
