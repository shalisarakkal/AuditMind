"""Bounded read-only provenance. Retention metadata never authorizes publication."""
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.services.observation_payload import MAPPING_VERSION
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.asset import Asset
from app.models.finding_observation import FindingObservation as Observation
from app.models.observation_publication import (
    ObservationPublicationDecision as Decision, ObservationPublicationState as State,
    ObservationPublicationSnapshot as Snapshot,
)

CONTRACTS = ('observation-publication-core-v1', 'observation-publication-consumers-v1')
NOTICE = 'Read-only retention metadata. Current scanner fields, identity and eligibility require a fresh review. This view does not authorize Publish or Undo.'


def storage_available(db):
    tables = ('observation_publication_decisions', 'observation_publication_states', 'observation_publication_snapshots')
    installed = all(db.scalar(select(func.to_regclass(name))) is not None for name in tables)
    if installed:
        # Reserved storage (0056) can exist before the core receipt columns (0057).
        # Inspect catalog metadata before projecting the current ORM contract.
        installed = db.scalar(text('''SELECT count(*) = 2 FROM pg_attribute
            WHERE attrelid = to_regclass('observation_publication_decisions')
              AND attname IN ('admission_contract', 'source_context_hash')
              AND attnum > 0 AND NOT attisdropped'''))
    return bool(installed)


def _read(db, org_id, finding_id, *, limit=20, before_version=None):
    finding = db.execute(select(Finding.scan_id, Finding.asset_id, Finding.created_at).where(
        Finding.org_id == org_id, Finding.id == finding_id)).one_or_none()
    if finding is None:
        raise HTTPException(404, 'Finding not found')
    installed = storage_available(db)
    if not installed:
        return dict(availability='not_installed', status='unavailable', current=None, items=[],
            has_more=False, next_before_version=None, publish_available=False, undo_available=False,
            recovery=['Publication history will be available after scheduled database activation.'], message=NOTICE)
    state = db.get(State, (org_id, finding_id))
    query = select(Decision).where(Decision.org_id == org_id, Decision.finding_id == finding_id)
    latest = db.scalar(query.order_by(Decision.version.desc()).limit(1))
    current = db.scalar(query.where(Decision.id == state.decision_id)) if state else None
    page = query.where(Decision.version < before_version) if before_version is not None else query
    rows = db.scalars(page.order_by(Decision.version.desc()).limit(limit + 1)).all()
    visible = rows[:limit]
    included = {row.id: row for row in visible}
    if current is not None:
        included[current.id] = current
    scan_ids = {row.source_scan_id for row in included.values()}
    if finding.scan_id:
        scan_ids.add(finding.scan_id)
    scans = {row.id: row for row in db.execute(select(Scan.id, Scan.filename, Scan.archived_at, Scan.status).where(
        Scan.org_id == org_id, Scan.id.in_(scan_ids)))}
    observed = {row.id: row for row in db.execute(select(Observation.id, Observation.scan_id,
        Observation.recorded_at, Observation.observed_at).where(Observation.org_id == org_id,
            Observation.finding_id == finding_id, Observation.id.in_({r.observation_id for r in included.values()})))}
    # Do not project payloads or size/hash their TOAST values merely to list history.
    snapshots = {}
    for row in db.execute(select(Snapshot.decision_id, Snapshot.side, Snapshot.source_scan_id).where(
            Snapshot.org_id == org_id, Snapshot.finding_id == finding_id, Snapshot.decision_id.in_(included))):
        snapshots.setdefault(row.decision_id, {})[row.side] = str(row.source_scan_id)

    def scan_info(identifier):
        row = scans.get(identifier)
        return dict(id=str(identifier) if identifier else None, retained=row is not None,
            filename=row.filename[:300] if row and row.filename else None,
            archived=bool(row and row.archived_at), status=row.status if row else None)

    def item(row):
        occurrence = observed.get(row.observation_id)
        return dict(id=str(row.id), version=row.version, operation=row.operation,
            created_at=row.created_at, actor_label=row.actor_label, rationale=row.rationale,
            admission_contract=row.admission_contract, observation_id=str(row.observation_id),
            observation_retained=occurrence is not None,
            observation_owner_retained=bool(occurrence and occurrence.scan_id == row.source_scan_id and row.source_scan_id in scans),
            recorded_at=occurrence.recorded_at if occurrence else None,
            observed_at=occurrence.observed_at if occurrence else None,
            source=scan_info(row.source_scan_id), snapshots=snapshots.get(row.id, {}))

    recovery = []
    status = 'not_published' if latest is None else 'recovery_required'
    if state is None and latest is not None:
        recovery.append('Retained decisions have no current generation. An administrator must review recovery; history cannot be applied directly.')
    if state is not None:
        if (current is None or current.version != state.version or latest is None or latest.id != current.id
                or current.operation != ('publish' if state.state == 'active' else 'undo')):
            recovery.append('The current generation does not match retained history. An administrator must review recovery.')
        elif current.admission_contract not in CONTRACTS or current.source_context_hash is None or current.mapping_version != MAPPING_VERSION:
            recovery.append('This retained generation has an unsupported admission contract. It cannot be upgraded or replayed as a new publication.')
        else:
            status = 'published' if state.state == 'active' else 'undone'
            if state.state == 'active':
                original, source = scans.get(finding.scan_id), scans.get(current.source_scan_id)
                asset = db.scalar(select(Asset.archived_at).where(Asset.org_id == org_id, Asset.id == finding.asset_id))
                asset_exists = db.scalar(select(Asset.id).where(Asset.org_id == org_id, Asset.id == finding.asset_id))
                if original is None or source is None or asset_exists is None:
                    recovery.append('An original owner or published source is no longer retained. Purged data cannot be restored by Undo; request reviewed recovery.')
                elif original.archived_at or source.archived_at or asset is not None or original.status != 'completed' or source.status != 'completed':
                    recovery.append('An original owner or published source is archived or unavailable. Review its lifecycle state before any future action.')
                occurrence = observed.get(current.observation_id)
                if occurrence is None or occurrence.scan_id != current.source_scan_id:
                    recovery.append('The published observation is missing or its retention owner changed. Request reviewed recovery.')
                pair = snapshots.get(current.id, {})
                if pair.get('before') != str(finding.scan_id) or pair.get('after') != str(current.source_scan_id):
                    recovery.append('An exact before/after source snapshot is unavailable. Do not reconstruct missing payloads from history.')
                if recovery:
                    status = 'recovery_required'
    return dict(availability='installed', status=status,
        current=item(current) if current else None,
        original_source=scan_info(finding.scan_id), original_asset_id=str(finding.asset_id) if finding.asset_id else None,
        finding_created_at=finding.created_at, items=[item(row) for row in visible], has_more=len(rows)>limit,
        next_before_version=visible[-1].version if len(rows)>limit and visible else None,
        recovery=recovery, publish_available=False, undo_available=False, message=NOTICE)


def read(db, org_id, finding_id, *, limit=20, before_version=None):
    if not 1 <= limit <= 20 or (before_version is not None and before_version < 1):
        raise HTTPException(422, 'Publication history requires a bounded page and positive version cursor')
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, 'Complete pending database changes before reading publication history')
    with db.get_bind().engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text('SET TRANSACTION READ ONLY'))
            return _read(snapshot, org_id, finding_id, limit=limit, before_version=before_version)
