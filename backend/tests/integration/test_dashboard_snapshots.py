"""Stored Dashboard correctness, admission and live evidence invalidation."""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models.asset import Asset
from app.models.dashboard_snapshot import DashboardSnapshot
from app.models.session import PlatformSetting
from app.models.organization import Organization
from app.services import dashboard_snapshots, platform
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import register, first_org_id
from tests.integration.test_platform_api import first_sign_in
from tests.integration.test_scoring_qualification_reviews import reviewer, make_draft, approve  # noqa: F401

pytestmark = requires_db


@pytest.fixture
def owner(client, db_session):
    headers = register(client, "snapshot-owner@example.io")
    org = uuid.UUID(first_org_id(client, headers))
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY,
        value={"enabled": True, "refresh_interval_seconds": 300, "version": 1}))
    db_session.commit()
    return headers, org, f"/api/v1/orgs/{org}/dashboard"


def test_first_read_queues_once_then_saved_reads_never_scan_inventory(client, owner, db_session, monkeypatch):
    headers, org, path = owner
    assert client.get(path, headers=headers).status_code == 202
    for _ in range(3):
        assert client.post(path + '/refresh', headers=headers).status_code == 202
    assert db_session.query(DashboardSnapshot).count() == 1
    assert runner.run_once(db_session)
    from app.api.routes import dashboard
    monkeypatch.setattr(dashboard, 'capture_inventory', lambda *args: pytest.fail('A saved read must not scan inventory'))
    result = client.get(path, headers=headers)
    assert result.status_code == 200, result.text
    assert result.headers['Cache-Control'] == 'no-store'
    body = result.json()
    assert body['snapshot_generated_at'] and body['snapshot_refresh_status'] == 'completed'
    assert body['asset_count'] == 0 and body['overall_score'] is None
    assert client.get(path + '/security-summary', headers=headers).json() == body['security_summary']


def test_new_writes_mark_snapshot_stale_until_refresh_then_exact_counts_replace_it(client, owner, db_session):
    headers, org, path = owner
    client.get(path, headers=headers)
    assert runner.run_once(db_session)
    initial = client.get(path, headers=headers).json()
    db_session.add(Asset(org_id=org, type='server', hostname='snapshot-added'))
    row = db_session.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id == org))
    row.requested_at -= timedelta(seconds=11)
    db_session.commit()
    stale = client.get(path, headers=headers).json()
    assert stale['snapshot_stale'] and stale['asset_count'] == 0
    pending = client.post(path + '/refresh', headers=headers).json()
    assert pending['asset_count'] == 0 and pending['snapshot_refresh_status'] == 'pending'
    assert runner.run_once(db_session)
    fresh = client.get(path, headers=headers).json()
    assert fresh['asset_count'] == 1 and not fresh['snapshot_stale']
    assert fresh['snapshot_generated_at'] != initial['snapshot_generated_at']


def test_periodic_scheduler_and_failure_retain_previous_snapshot(client, owner, db_session, monkeypatch):
    headers, org, path = owner
    client.get(path, headers=headers)
    assert runner.run_once(db_session)
    initial = client.get(path, headers=headers).json()
    assert dashboard_snapshots.enqueue_due(db_session) == 0
    assert dashboard_snapshots.enqueue_due(db_session, datetime.now(timezone.utc) + timedelta(seconds=331)) == 1
    from app.api.routes import dashboard
    def fail(*args):
        raise RuntimeError('Synthetic failure')
    monkeypatch.setattr(dashboard, 'capture_inventory', fail)
    assert runner.run_once(db_session)
    failed = client.get(path, headers=headers).json()
    assert failed['snapshot_refresh_status'] == 'failed' and failed['snapshot_error']
    assert failed['snapshot_generated_at'] == initial['snapshot_generated_at']
    assert failed['asset_count'] == initial['asset_count']


def test_refresh_requires_membership_and_disabled_mode_does_not_enqueue(client, owner, db_session):
    headers, org, path = owner
    outsider = register(client, 'snapshot-outsider@example.io')
    assert client.get(path, headers=outsider).status_code == 403
    assert client.post(path+'/refresh', headers=outsider).status_code == 403
    assert db_session.query(DashboardSnapshot).count() == 0
    db_session.get(PlatformSetting, dashboard_snapshots.SETTINGS_KEY).value = {'enabled': False}
    db_session.commit()
    assert client.post(path+'/refresh', headers=headers).status_code == 409
    assert client.get(path, headers=headers).status_code == 200
    assert db_session.query(DashboardSnapshot).count() == 0


def test_interrupted_snapshot_requeues_without_losing_saved_payload(client, owner, db_session):
    headers, org, path = owner
    client.get(path, headers=headers)
    assert runner.run_once(db_session)
    row = db_session.scalar(select(DashboardSnapshot))
    saved = row.payload
    row.status = 'running'
    row.heartbeat_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    runner.reap_stale(db_session)
    db_session.expire_all()
    row = db_session.get(DashboardSnapshot, row.id)
    assert row.status == 'pending' and row.retry_count == 1 and row.payload == saved
    assert runner.run_once(db_session)


def test_platform_settings_are_admin_only_versioned_and_validated(client, owner, db_session):
    headers, _, _ = owner
    endpoint = '/api/v1/platform/dashboard-settings'
    assert client.get(endpoint, headers=headers).status_code == 403
    assert client.patch(endpoint, headers=headers, json={'enabled': False, 'expected_version': 1}).status_code == 403
    temporary = platform.create_sysadmin(db_session, 'snapshot-platform@example.io', 'Root')
    db_session.commit()
    root = first_sign_in(client, 'snapshot-platform@example.io', temporary)
    assert client.get(endpoint, headers=root).json()['version'] == 1
    assert client.patch(endpoint, headers=root, json={'enabled': True, 'refresh_interval_seconds': 0, 'expected_version': 1}).status_code == 422
    saved = client.patch(endpoint, headers=root, json={'enabled': False, 'refresh_interval_seconds': 600, 'expected_version': 1})
    assert saved.status_code == 200 and saved.json()['version'] == 2
    assert client.patch(endpoint, headers=root, json={'enabled': True, 'expected_version': 1}).status_code == 409


def test_scheduler_warms_active_orgs_and_archive_respects_refresh_jobs(client, owner, db_session):
    from app.models.user import User
    from app.services.people import PeopleError
    headers, org, _ = owner
    other = register(client, 'archived-snapshot@example.io')
    other_org = db_session.get(Organization, uuid.UUID(first_org_id(client, other)))
    other_org.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert dashboard_snapshots.enqueue_due(db_session) == 1
    assert platform.running_jobs(db_session, org) == 1
    active = db_session.get(Organization, org)
    actor = db_session.scalar(select(User).where(User.email == 'snapshot-owner@example.io'))
    with pytest.raises(PeopleError, match='background job'):
        platform.archive_org(db_session, active, actor)
    db_session.rollback()
    assert runner.run_once(db_session)
    platform.archive_org(db_session, active, actor)
    db_session.commit()
    assert dashboard_snapshots.enqueue(db_session, org) is None
    assert db_session.query(DashboardSnapshot).count() == 1


def test_two_sessions_coalesce_the_first_snapshot_request(client, owner, db_session):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    _, org, _ = owner
    barrier = threading.Barrier(2)
    def enqueue():
        with Session(db_session.get_bind()) as independent:
            barrier.wait(timeout=5)
            return dashboard_snapshots.enqueue(independent, org).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(enqueue) for _ in range(2)]
        ids = [future.result(timeout=10) for future in futures]
    assert ids[0] == ids[1]
    assert db_session.query(DashboardSnapshot).count() == 1


def test_inventory_change_during_build_leaves_a_consistent_but_stale_snapshot(client, owner, db_session, monkeypatch):
    from sqlalchemy.orm import Session
    from app.api.routes import dashboard
    headers, org, path = owner
    client.get(path, headers=headers)
    original = dashboard.capture_inventory
    def concurrent(snapshot, transaction):
        value = original(snapshot, transaction)
        with Session(db_session.get_bind()) as writer:
            writer.add(Asset(org_id=org, type='server', hostname='during-dashboard-refresh'))
            writer.commit()
        return value
    monkeypatch.setattr(dashboard, 'capture_inventory', concurrent)
    assert runner.run_once(db_session)
    body = client.get(path, headers=headers).json()
    assert body['asset_count'] == 0 and body['snapshot_stale']
    assert db_session.query(Asset).filter(Asset.org_id == org).count() == 1


@pytest.mark.parametrize('mutation', ['expiry', 'revocation', 'inventory', 'policy'])
def test_saved_inventory_never_bypasses_live_evidence_checks(client, reviewer, db_session, mutation):
    from app.models.evidence_evaluation import EvidenceEvaluation
    from sqlalchemy import text
    headers, org, path, _ = reviewer
    assert approve(client, reviewer, make_draft(client, reviewer)).status_code == 200
    assert client.post(path+'/evaluations', headers=headers).status_code == 202
    assert runner.run_once(db_session)
    assert client.patch(path+'/settings', headers=headers, json={'expected_version': 0, 'evidence_qualified_enabled': True}).status_code == 200
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY, value={'enabled': True}))
    db_session.commit()
    dashboard = f'/api/v1/orgs/{org}/dashboard'
    assert client.get(dashboard, headers=headers).status_code == 202
    assert runner.run_once(db_session)
    before = client.get(dashboard, headers=headers).json()
    assert next(d for d in before['domains'] if d['domain']=='network_config')['score'] is not None
    evaluation = db_session.scalar(select(EvidenceEvaluation))
    if mutation == 'expiry':
        evaluation.valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif mutation == 'policy':
        evaluation.policy_identity = 'old-policy'
    elif mutation == 'revocation':
        db_session.execute(text("UPDATE domain_evidence_qualifications SET status='revoked',version=version+1 WHERE org_id=:org"), {'org': uuid.UUID(org)})
    else:
        db_session.add(Asset(org_id=uuid.UUID(org), type='server', hostname='new-after-snapshot'))
    db_session.commit()
    after = client.get(dashboard, headers=headers).json()
    assert after['snapshot_generated_at'] == before['snapshot_generated_at']
    assert after['overall_score'] is None and after['qualified_domain_count'] == 0
    assert all(d['score'] is None for d in after['domains'])
