"""Reserved membership/manifest schema and bounded source dependency diagnostics."""
import uuid

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_consolidation import FindingConsolidationMember, FindingConsolidationDependency
from app.models.finding_observation import FindingObservation
from app.models.organization import Organization
from app.models.scan import Scan
from app.services.consolidation_dependencies import manifest
from tests.conftest import requires_db
from tests.integration.test_finding_consolidation_foundation import native, preview, group, receipt

pytestmark = requires_db


def make_member(db, n, root, **changes):
    values = dict(org_id=root.org_id, consolidation_id=root.id, generation=1,
        finding_id=n['source'].finding_id, role='canonical')
    row = FindingConsolidationMember(**{**values, **changes})
    db.add(row)
    db.flush()
    return row


def make_dependency(db, root, **changes):
    values = dict(org_id=root.org_id, consolidation_id=root.id, generation=1,
        resource_kind='scan', resource_id=uuid.uuid4())
    row = FindingConsolidationDependency(**{**values, **changes})
    db.add(row)
    db.flush()
    return row


def prepared_manifest(db, n):
    db.flush()
    decision = db.get(FindingCanonicalDecision, uuid.UUID(n['decision']))
    findings = {row.id: row for row in db.scalars(select(Finding).where(Finding.org_id == decision.org_id))}
    observations = db.scalars(select(FindingObservation).where(FindingObservation.org_id == decision.org_id)).all()
    identity = dict(tool_id=n['tool'], canonical_asset_id=n['asset'])
    return manifest(db, decision.org_id, decision, findings, observations, identity)


def test_manifest_is_stable_and_includes_every_source_without_payloads(client, db_session, native):
    n = native
    result = prepared_manifest(db_session, n)
    assert result == prepared_manifest(db_session, n)
    assert result['resource_counts'] == dict(asset=2, canonical_decision=1, finding=2,
        identity_binding=2, observation=2, scan=2, tool=1)
    assert {row['role'] for row in result['members']} == {'canonical', 'alias'}
    assert {row['resource_id'] for row in result['resources'] if row['resource_kind'] == 'scan'} == {
        str(n['source'].scan_id), str(n['target'].scan_id)}
    assert all(set(row) == {'resource_kind', 'resource_id', 'resource_version'} for row in result['resources'])
    response = preview(client, n)
    assert response.status_code == 200, response.text
    assert response.json()['dependency_summary']['fingerprint'] == result['fingerprint']
    assert 'resources' not in response.json()['dependency_summary']
    assert response.json()['apply_available'] is False
    assert db_session.query(FindingConsolidationMember).count() == 0
    assert db_session.query(FindingConsolidationDependency).count() == 0


def test_manifest_tracks_tool_version_and_refuses_retired_tool(db_session, native):
    from app.models.finding_identity_binding import IdentityTool
    before = prepared_manifest(db_session, native)
    tool = db_session.get(IdentityTool, uuid.UUID(native['tool']))
    tool.version += 1
    after = prepared_manifest(db_session, native)
    assert before['fingerprint'] != after['fingerprint']
    assert next(row['resource_version'] for row in after['resources'] if row['resource_kind'] == 'tool') == tool.version
    tool.active = False
    assert prepared_manifest(db_session, native) is None


def test_preview_works_with_single_connection_pool(client, db_session, native):
    from app.api.deps import get_db
    from app.main import app
    limited = create_engine(db_session.get_bind().url, pool_size=1, max_overflow=0, pool_timeout=0.2)
    previous = app.dependency_overrides[get_db]
    def request_session():
        with Session(limited) as request:
            yield request
    try:
        app.dependency_overrides[get_db] = request_session
        response = preview(client, native)
        assert response.status_code == 200, response.text
        assert response.json()['prerequisites_met'] and not response.json()['apply_available']
    finally:
        app.dependency_overrides[get_db] = previous
        limited.dispose()


def test_concurrent_previews_do_not_hold_request_and_snapshot_connections(client, db_session, native):
    from concurrent.futures import ThreadPoolExecutor
    from app.api.deps import get_db
    from app.main import app
    limited = create_engine(db_session.get_bind().url, pool_size=2, max_overflow=0, pool_timeout=3)
    previous = app.dependency_overrides[get_db]
    def request_session():
        with Session(limited) as request:
            yield request
    try:
        app.dependency_overrides[get_db] = request_session
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(preview, client, native) for _ in range(4)]
            responses = [future.result(timeout=15) for future in futures]
        assert all(response.status_code == 200 for response in responses)
        assert all(not response.json()['apply_available'] for response in responses)
        assert len({response.json()['snapshot_fingerprint'] for response in responses}) == 1
        assert limited.pool.checkedout() == 0
    finally:
        app.dependency_overrides[get_db] = previous
        limited.dispose()


def test_manifest_rejects_missing_or_cross_tenant_physical_ownership(db_session, native):
    n = native
    finding = db_session.get(Finding, n['source'].finding_id)
    original = finding.scan_id
    finding.scan_id = None
    assert prepared_manifest(db_session, n) is None
    finding.scan_id = original
    other = Organization(name='Other owner')
    db_session.add(other)
    db_session.flush()
    scan = db_session.get(Scan, original)
    scan.org_id = other.id
    assert prepared_manifest(db_session, n) is None


def test_membership_is_unique_but_not_operational_visibility(client, db_session, native):
    n = native
    root = group(db_session, n)
    receipt(db_session, n, root)
    make_member(db_session, n, root)
    make_member(db_session, n, root, finding_id=n['target'].finding_id, role='alias')
    with pytest.raises(IntegrityError), db_session.begin_nested():
        make_member(db_session, n, root, role='alias')
    with pytest.raises(IntegrityError), db_session.begin_nested():
        make_member(db_session, n, root, finding_id=uuid.uuid4())
    db_session.commit()
    response = client.get(n['base']+'/findings', headers=n['headers'])
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 2


@pytest.mark.parametrize('kind', ['member', 'dependency'])
def test_child_generation_cannot_cross_organization_or_reference_unknown_receipt(db_session, native, kind):
    n = native
    root = group(db_session, n)
    receipt(db_session, n, root)
    other = Organization(name='Other generation owner')
    db_session.add(other)
    db_session.flush()
    create = (lambda **kwargs: make_member(db_session, n, root, **kwargs)) if kind == 'member' else (
        lambda **kwargs: make_dependency(db_session, root, **kwargs))
    for values in (dict(org_id=other.id), dict(generation=2), dict(generation=0)):
        with pytest.raises(IntegrityError), db_session.begin_nested():
            create(**values)


@pytest.mark.parametrize('values', [dict(resource_kind='arbitrary'), dict(resource_version=0), dict(resource_version=-1)])
def test_dependency_kind_and_versions_are_constrained(db_session, native, values):
    root = group(db_session, native)
    receipt(db_session, native, root)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        make_dependency(db_session, root, **values)


def test_dependency_dedup_and_retention_survive_source_purge_but_not_org_delete(db_session, native):
    n = native
    root = group(db_session, n)
    receipt(db_session, n, root)
    source_id = n['source'].scan_id
    make_member(db_session, n, root)
    make_dependency(db_session, root, resource_id=source_id)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        make_dependency(db_session, root, resource_id=source_id)
    db_session.execute(delete(Scan).where(Scan.id == source_id))
    db_session.flush()
    assert db_session.query(FindingConsolidationDependency).count() == 1
    assert db_session.query(FindingConsolidationMember).count() == 1
    # Current rows are reserved metadata only. Future source guards must remove
    # current membership on explicit undo; audit dependencies remain retained.
    db_session.execute(delete(Organization).where(Organization.id == root.org_id))
    db_session.flush()
    assert db_session.query(FindingConsolidationDependency).count() == 0
    assert db_session.query(FindingConsolidationMember).count() == 0
