"""Private Stage B transaction core. No route calls this module.

Public writers stay unconditionally closed until proof, consumer invalidation,
provenance and lifecycle guards participate in the same transaction. Private
staging never commits: only isolated tests and a future reviewed integration may
call it. A core-only receipt cannot be silently upgraded to an integrated write.
"""
import copy
import uuid
from datetime import datetime
from contextlib import contextmanager
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints
from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.enums import Severity
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation as Observation
from app.models.asset import Asset
from app.models.scan import Scan
from app.models.archive import AssetScan, ArchiveBatch, ArchiveJob
from app.models.observation_publication import (
    ObservationPublicationDecision as Decision, ObservationPublicationSnapshot as Snapshot,
    ObservationPublicationState as State, ObservationPublicationDependency as Dependency,
    OrganizationPublicationSettings as Settings,
)
from app.services import observation_payload as payload_contract
from app.services.observation_publication import _prepare, _check_actor, blocked
from app.services.consolidation_transactions import _admit, _bounded_lock_wait
from app.services.events import actor_label, record_event
from app.services.identity_bindings import latest_bindings

CONTRACT = 'observation-publication-core-v1'
MAX_OBSERVATIONS = 1000
SOURCE_KEYS = ('native_identity', 'candidate_key', 'identity_binding', 'observation_sha256',
    'observation_context_sha256', 'recorded_at', 'observed_at', 'original_scan_id',
    'original_asset_id', 'original_created_at', 'assets', 'scans', 'creator_links')


class PublicationRequest(BaseModel):
    """Internal request, absent from HTTP/OpenAPI. No replacement data accepted."""
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    expected_version: int = Field(strict=True, ge=0, le=2_147_483_646)
    review_token: str = Field(pattern=r'^[0-9a-f]{64}$')
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    confirm: StrictBool


class SettingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(strict=True, ge=0, le=2_147_483_646)
    enabled: StrictBool


def publish(*args, **kwargs):
    blocked('Publication is unavailable until consumer, proof and lifecycle integration is complete')


def undo(*args, **kwargs):
    blocked('Publication Undo is unavailable until consumer, proof and lifecycle integration is complete')


def update_settings(*args, **kwargs):
    blocked('Publication settings are not yet available for application use')


def configuration(db, org_id):
    row = db.scalar(select(Settings).where(Settings.org_id == org_id).execution_options(populate_existing=True))
    return dict(enabled=row.enabled if row else False, version=row.version if row else 0)


def _clean(db):
    if db.new or db.dirty or db.deleted:
        blocked('Complete pending ORM changes before publication staging')
    if db.connection().get_isolation_level() != 'READ COMMITTED':
        blocked('Publication staging requires a fresh read-committed transaction')


@contextmanager
def _utc(db):
    previous = db.scalar(text("SELECT current_setting('TimeZone')"))
    db.scalar(select(func.set_config('TimeZone', 'UTC', True)))
    try:
        yield
    except BaseException:
        raise  # The enclosing savepoint restores SET LOCAL on rollback.
    else:
        db.scalar(select(func.set_config('TimeZone', previous, True)))


def _stage_setting(db, org_id, actor_id, request):
    """Private policy staging; no commit, and no production caller."""
    _clean(db)
    try:
        return _setting(db, org_id, actor_id, request)
    except DBAPIError as error:
        if getattr(error.orig, 'sqlstate', None) in ('55P03', '23505', '23503', '40001', '40P01'):
            raise HTTPException(409, 'Publication setting is busy or changed; reload before retrying') from error
        raise


def _setting(db, org_id, actor_id, request):
    with db.begin_nested(), _bounded_lock_wait(db):
        actor = _admit(db, org_id, actor_id)
        current = configuration(db, org_id)
        if current['version'] != request.expected_version:
            blocked('Publication setting changed; reload before saving')
        if current['enabled'] == request.enabled:
            return current
        if current['version'] >= 2_147_483_646 and request.enabled:
            blocked('Publication policy generation is exhausted; review recovery before enabling')
        row = db.get(Settings, org_id)
        if row is None:
            row = Settings(org_id=org_id, enabled=request.enabled, version=1)
            db.add(row)
        else:
            row.enabled = request.enabled
            row.version += 1
        record_event(db, 'settings_changed', org_id=org_id, actor=actor,
            item='Observation payload publication', details=dict(enabled=row.enabled, version=row.version))
        db.flush()
        return dict(enabled=row.enabled, version=row.version)


def _source(plan, db, org_id, observation_id):
    context = plan['_transaction']['context']
    binding = latest_bindings(db, org_id, [observation_id]).get(observation_id)
    if binding is None or binding.version != context['identity_binding']['version']:
        blocked('Current independently reviewed source binding is required')
    resources = {('finding', context['finding_id']), ('observation', context['observation_id']),
        ('tool', context['identity_binding']['tool_id']), ('identity_binding', str(binding.id))}
    resources.update(('asset', row['id']) for row in context['assets'])
    resources.update(('scan', row['id']) for row in context['scans'])
    material = {key: context[key] for key in SOURCE_KEYS}
    material['binding_id'] = str(binding.id)
    return payload_contract.digest(material), sorted(resources)


def _observations(db, org_id, finding_id):
    """Bounded reference manifest, including backdated imports; never payloads."""
    rows = db.execute(select(Observation.id, Observation.import_id, Observation.scan_id,
        Observation.asset_identity['asset_id'].astext.label('asset_id'), Observation.recorded_at,
        Observation.observed_at).where(Observation.org_id == org_id, Observation.finding_id == finding_id)
        .order_by(Observation.recorded_at.desc(), Observation.id.desc()).limit(MAX_OBSERVATIONS + 1)).all()
    if len(rows) > MAX_OBSERVATIONS:
        blocked('More than 1,000 retained observations require a separate bounded review path')
    try:
        assets = {uuid.UUID(row.asset_id) for row in rows}
    except (ValueError, TypeError, AttributeError):
        blocked('Every retained observation requires its original source asset')
    scans = {row.scan_id for row in rows}
    if not rows or None in scans or any(row.import_id != row.scan_id for row in rows):
        blocked('Every retained observation requires its original retained scan')
    creators = db.execute(select(AssetScan.asset_id, AssetScan.scan_id).where(
        AssetScan.asset_id.in_(assets), AssetScan.created.is_(True))
        .order_by(AssetScan.asset_id, AssetScan.scan_id).limit(MAX_OBSERVATIONS + 1)).all()
    if len(creators) > MAX_OBSERVATIONS:
        blocked('Retained asset-creator dependencies exceed the bounded review limit')
    scans.update(row.scan_id for row in creators)
    live_assets = db.execute(select(Asset.id, Asset.hostname, Asset.ip, Asset.cloud_id, Asset.type,
        Asset.archived_at).where(Asset.org_id == org_id, Asset.id.in_(assets)).order_by(Asset.id)).all()
    live_scans = db.execute(select(Scan.id, Scan.filename, Scan.scan_type, Scan.profile,
        Scan.ingestion_config_fingerprint, Scan.content_hash, Scan.status, Scan.archived_at).where(
            Scan.org_id == org_id, Scan.id.in_(scans)).order_by(Scan.id)).all()
    if (len(live_assets) != len(assets) or any(row.archived_at is not None for row in live_assets)
            or len(live_scans) != len(scans)
            or any(row.archived_at is not None or row.status != 'completed' for row in live_scans)):
        blocked('Every retained observation and creator must have active same-organization owners')
    resources = {('observation', str(row.id)) for row in rows}
    resources.update(('asset', str(identifier)) for identifier in assets)
    resources.update(('scan', str(identifier)) for identifier in scans)
    affected = {*scans, *assets, finding_id}
    if (db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id == org_id,
            ArchiveBatch.item_id.in_(affected), ArchiveBatch.state.in_(('archiving','restoring','purging'))).limit(1))
            or db.scalar(select(ArchiveJob.id).join(ArchiveBatch, ArchiveBatch.id == ArchiveJob.batch_id).where(
                ArchiveJob.org_id == org_id, ArchiveBatch.org_id == org_id,
                ArchiveBatch.item_id.in_(affected), ArchiveJob.status.in_(('pending','running'))).limit(1))):
        blocked('A retained observation owner has a pending source lifecycle operation')
    def material(items):
        return [{key: value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, uuid.UUID)
            else value for key,value in row._mapping.items()} for row in items]
    fingerprint = payload_contract.digest(dict(observations=material(rows), assets=material(live_assets),
        scans=material(live_scans), creators=material(creators)))
    return fingerprint, resources


def _state(db, org_id, finding_id):
    row = db.get(State, (org_id, finding_id), populate_existing=True)
    if row is None:
        if db.scalar(select(Decision.id).where(Decision.org_id == org_id,
                Decision.finding_id == finding_id).limit(1)):
            blocked('Retained publication generation is missing; review recovery before writing')
        return None, None
    receipt = db.get(Decision, row.decision_id, populate_existing=True)
    if (receipt is None or receipt.org_id != org_id or receipt.finding_id != finding_id
            or receipt.version != row.version or receipt.admission_contract != CONTRACT
            or receipt.mapping_version != payload_contract.MAPPING_VERSION or receipt.source_context_hash is None
            or receipt.operation != ('publish' if row.state == 'active' else 'undo')):
        blocked('Publication generation has an unsupported admission contract; it cannot be upgraded by replay')
    return row, receipt


def _publish_prepare(db, org_id, actor_id, finding_id, observation_id):
    plan = _prepare(db, org_id, actor_id, finding_id, observation_id, _private=True)
    policy = configuration(db, org_id)
    if not policy['enabled']:
        blocked('Observation payload publication is disabled for this organization')
    state, receipt = _state(db, org_id, finding_id)
    if state and state.state == 'active':
        if plan['_transaction']['context']['current_sha256'] != receipt.after_hash:
            blocked('Current scanner fields differ from the active publication; review recovery first')
        if not plan['no_op']:
            blocked('Undo the exact current publication before reviewing a different one')
    source_hash, resources = _source(plan, db, org_id, observation_id)
    observations, retained = _observations(db, org_id, finding_id)
    resources = sorted(set(resources) | retained)
    version = state.version if state else 0
    if version >= 2_147_483_646 and not plan['no_op']:
        blocked('Publication generation is exhausted; reserve the final generation for Undo')
    token = payload_contract.digest(dict(contract=CONTRACT, operation='publish',
        admission=plan['review_token'], policy=policy, expected_version=version,
        decision_id=str(receipt.id) if receipt else None, source_hash=source_hash, resources=resources,
        observations=observations))
    return dict(review_token=token, expected_version=version, plan=plan,
        source_hash=source_hash, resources=resources)


def _snapshot_pair(db, org_id, finding_id, receipt):
    metadata = db.execute(select(Snapshot.id, Snapshot.side, Snapshot.source_scan_id,
        func.octet_length(cast(Snapshot.payload, Text)).label('bytes')).where(
            Snapshot.org_id == org_id, Snapshot.finding_id == finding_id,
            Snapshot.decision_id == receipt.id).order_by(Snapshot.side)).all()
    if len(metadata) != 2 or {row.side for row in metadata} != {'before', 'after'}:
        blocked('Both original source snapshots must be retained; purged data cannot be recreated')
    if any(row.bytes > payload_contract.MAX_BYTES for row in metadata):
        blocked('A retained source snapshot exceeds the supported review limit')
    result = {}
    for row in metadata:
        values = db.scalar(select(Snapshot.payload).where(Snapshot.id == row.id, Snapshot.org_id == org_id))
        if not isinstance(values, dict) or values.keys() != set(payload_contract.FIELDS):
            blocked('Retained source snapshot has an unsupported field contract')
        expected = receipt.before_hash if row.side == 'before' else receipt.after_hash
        if payload_contract.digest(values) != expected:
            blocked('Retained source snapshot changed; review recovery before Undo')
        result[row.side] = dict(values=values, id=str(row.id), scan_id=str(row.source_scan_id), sha256=expected)
    return result


def _undo_prepare(db, org_id, actor_id, finding_id):
    _check_actor(db, org_id, actor_id)
    state, receipt = _state(db, org_id, finding_id)
    if state is None or state.state != 'active':
        blocked('An exact active publication is required for Undo')
    # Undo restores already-reviewed retained data; it does not select the latest
    # source as a replacement. New observations still fence the preview below.
    plan = _prepare(db, org_id, actor_id, finding_id, receipt.observation_id,
        _private=True, _require_latest=False)
    source_hash, resources = _source(plan, db, org_id, receipt.observation_id)
    observations, retained = _observations(db, org_id, finding_id)
    resources = sorted(set(resources) | retained)
    if source_hash != receipt.source_context_hash:
        blocked('Published source context changed; review recovery before Undo')
    snapshots = _snapshot_pair(db, org_id, finding_id, receipt)
    context = plan['_transaction']['context']
    if (snapshots['before']['scan_id'] != context['original_scan_id']
            or snapshots['after']['scan_id'] != str(receipt.source_scan_id)):
        blocked('Source snapshot retention ownership changed')
    if context['current_sha256'] != receipt.after_hash:
        blocked('Current scanner fields differ from the publication; Undo cannot overwrite later edits')
    current = plan['_transaction']['before']
    restored = snapshots['before']['values']
    changes = [dict(field=field, before=payload_contract.summary(current[field]),
        after=payload_contract.summary(restored[field]),
        removal=restored[field] is None and current[field] is not None)
        for field in payload_contract.FIELDS
        if payload_contract.digest(current[field]) != payload_contract.digest(restored[field])]
    policy = configuration(db, org_id)
    token = payload_contract.digest(dict(contract=CONTRACT, operation='undo',
        admission=plan['review_token'], policy=policy, expected_version=state.version,
        decision_id=str(receipt.id), source_hash=source_hash, resources=resources,
        snapshots={side: {k:v for k,v in snap.items() if k != 'values'} for side,snap in snapshots.items()},
        observations=observations))
    return dict(review_token=token, expected_version=state.version, receipt=receipt,
        snapshots=snapshots, plan=plan, source_hash=source_hash, resources=resources, changes=changes)


def _preview(db, org_id, actor_id, finding_id, observation_id=None):
    """Private read-only plan. Its receipt contract is not publicly enabled."""
    if db.new or db.dirty or db.deleted:
        blocked('Complete pending ORM changes before preview')
    with db.get_bind().engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text('SET TRANSACTION READ ONLY'))
            snapshot.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            if observation_id is None:
                result = _undo_prepare(snapshot, org_id, actor_id, finding_id)
            else:
                result = _publish_prepare(snapshot, org_id, actor_id, finding_id, observation_id)
            return dict(contract=CONTRACT, review_token=result['review_token'],
                operation='publish' if observation_id is not None else 'undo', finding_id=str(finding_id),
                expected_version=result['expected_version'], apply_available=False,
                no_op=result['plan']['no_op'] if observation_id is not None else False,
                changes=result['plan']['changes'] if observation_id is not None else result['changes'],
                provenance=result['plan']['provenance'])


def _materialize(finding, values):
    for field in payload_contract.FIELDS:
        value = values[field]
        if field == 'severity':
            value = Severity(value)
        elif field in ('first_seen', 'last_seen'):
            value = datetime.fromisoformat(payload_contract.timestamp(value)) if value is not None else None
        setattr(finding, field, copy.deepcopy(value))


def _receipt(row, replayed):
    return dict(decision_id=str(row.id), finding_id=str(row.finding_id), version=row.version,
        operation=row.operation, replayed=replayed, no_op=False, apply_available=False,
        admission_contract=row.admission_contract)


def _stage(db, org_id, actor_id, finding_id, request, observation_id=None):
    """PRIVATE core only. Savepoint-atomic; caller owns commit/rollback.

    Never wire this directly to HTTP or a background worker. Additional consumer
    and lifecycle work must be staged in the SAME outer transaction before any
    future integrated writer may commit it.
    """
    _clean(db)
    if request.confirm is not True:
        raise HTTPException(422, 'Explicit source-field review acknowledgment is required')
    operation = 'publish' if observation_id is not None else 'undo'
    request_hash = payload_contract.digest(dict(contract=CONTRACT, operation=operation,
        org_id=str(org_id), actor_id=str(actor_id), finding_id=str(finding_id),
        observation_id=str(observation_id) if observation_id else None, request=request.model_dump(mode='json')))
    try:
        with db.begin_nested(), _bounded_lock_wait(db), _utc(db):
            actor = _admit(db, org_id, actor_id)
            previous = db.scalar(select(Decision).where(Decision.org_id == org_id,
                Decision.request_id == request.request_id))
            if previous:
                if previous.request_hash != request_hash or previous.admission_contract != CONTRACT:
                    blocked('Request identifier was used for a different operation or admission contract')
                return _receipt(previous, True)
            db.expire_all()
            finding = db.scalar(select(Finding).where(Finding.org_id == org_id, Finding.id == finding_id)
                .with_for_update(key_share=True, nowait=True).execution_options(populate_existing=True))
            if finding is None:
                raise HTTPException(404, 'Finding not found')
            prepared = (_publish_prepare(db, org_id, actor_id, finding_id, observation_id)
                if observation_id is not None else _undo_prepare(db, org_id, actor_id, finding_id))
            if request.expected_version != prepared['expected_version'] or request.review_token != prepared['review_token']:
                blocked('Publication context changed; reload and review again')
            if observation_id is not None and prepared['plan']['no_op']:
                return dict(decision_id=None, finding_id=str(finding_id), version=request.expected_version,
                    operation='publish', replayed=False, no_op=True, apply_available=False, admission_contract=CONTRACT)
            before = prepared['plan']['_transaction']['before']
            after = (prepared['plan']['_transaction']['after'] if observation_id is not None
                else prepared['snapshots']['before']['values'])
            source = observation_id if observation_id is not None else prepared['receipt'].observation_id
            source_scan = (prepared['plan']['provenance']['observation_scan_id'] if observation_id is not None
                else str(prepared['receipt'].source_scan_id))
            row = Decision(org_id=org_id, finding_id=finding_id, observation_id=source,
                source_scan_id=uuid.UUID(source_scan), request_id=request.request_id, request_hash=request_hash,
                before_hash=payload_contract.digest(before), after_hash=payload_contract.digest(after),
                mapping_version=prepared['plan']['mapping_version'], admission_contract=CONTRACT,
                source_context_hash=prepared['source_hash'], version=request.expected_version + 1,
                operation=operation, rationale=request.rationale, actor_id=actor_id, actor_label=actor_label(actor))
            db.add(row); db.flush()
            if observation_id is not None:
                for side, values, scan in (
                    ('before', before, prepared['plan']['provenance']['original_scan_id']),
                    ('after', after, source_scan)):
                    db.add(Snapshot(org_id=org_id, finding_id=finding_id, decision_id=row.id,
                        source_scan_id=uuid.UUID(scan), side=side, payload=copy.deepcopy(values)))
                db.add_all([Dependency(org_id=org_id, decision_id=row.id, resource_kind=kind,
                    resource_id=uuid.UUID(identifier)) for kind,identifier in prepared['resources']])
                db.flush()
                _snapshot_pair(db, org_id, finding_id, row)  # Same DB-side size gate as Undo.
            state = db.get(State, (org_id, finding_id))
            if state is None:
                state = State(org_id=org_id, finding_id=finding_id)
                db.add(state)
            state.decision_id, state.version = row.id, row.version
            state.state = 'active' if observation_id is not None else 'undone'
            _materialize(finding, after)
            db.flush()
            record_event(db, 'finding_payload_published' if observation_id is not None else 'finding_payload_undone',
                org_id=org_id, actor=actor, item=str(finding_id),
                details=dict(finding_id=str(finding_id), observation_id=str(source),
                    decision_id=str(row.id), version=row.version, admission_contract=CONTRACT))
            db.flush()
            return _receipt(row, False)
    except DBAPIError as error:
        if getattr(error.orig, 'sqlstate', None) in ('55P03', '23505', '23503', '23514', '40001', '40P01'):
            raise HTTPException(409, 'Concurrent publication or source change; reload before retrying') from error
        raise
