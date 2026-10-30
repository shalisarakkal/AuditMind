"""Platform inheritance, organization overrides and deterministic scheduling."""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models.organization import Organization
from app.models.dashboard_snapshot import DashboardSnapshot
from app.models.session import PlatformSetting
from app.models.event import Event
from app.services import dashboard_snapshots
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member

pytestmark = requires_db


@pytest.fixture
def owner(client):
    headers = register(client, 'refresh-interval@example.io')
    org_id = uuid.UUID(first_org_id(client, headers))
    return headers, org_id, f'/api/v1/orgs/{org_id}/dashboard/settings'


def test_builtin_hour_inherits_platform_changes_override_and_reset(client, owner, db_session):
    headers, org_id, path = owner
    initial = client.get(path, headers=headers).json()
    assert initial['refresh_interval_seconds'] == 3600
    assert initial['refresh_interval_override_seconds'] is None
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY, value={'enabled': True, 'refresh_interval_seconds': 7200}))
    db_session.commit()
    assert client.get(path, headers=headers).json()['refresh_interval_seconds'] == 7200
    saved = client.patch(path, headers=headers, json={'expected_version': 0, 'refresh_interval_override_seconds': 600})
    assert saved.status_code == 200 and saved.json()['version'] == 1
    assert saved.json()['refresh_interval_seconds'] == 600
    db_session.get(PlatformSetting, dashboard_snapshots.SETTINGS_KEY).value = {'enabled': True, 'refresh_interval_seconds': 14400}
    db_session.commit()
    assert client.get(path, headers=headers).json()['refresh_interval_seconds'] == 600
    reset = client.patch(path, headers=headers, json={'expected_version': 1, 'refresh_interval_override_seconds': None})
    assert reset.status_code == 200 and reset.json()['refresh_interval_seconds'] == 14400
    assert reset.json()['version'] == 2 and reset.json()['refresh_interval_override_seconds'] is None
    assert db_session.query(Event).filter(Event.type == 'settings_changed', Event.org_id == org_id).count() == 2


def test_override_permissions_validation_and_conflict(client, owner, db_session):
    headers, org_id, path = owner
    viewer = member(client, headers, str(org_id), 'viewer')
    foreign = register(client, 'other-interval@example.io')
    payload = {'expected_version': 0, 'refresh_interval_override_seconds': 60}
    assert client.get(path, headers=viewer).status_code == 200
    assert client.patch(path, headers=viewer, json=payload).status_code == 403
    assert client.get(path, headers=foreign).status_code == 403
    for invalid in (0, 59, 86401):
        assert client.patch(path, headers=headers, json={**payload, 'refresh_interval_override_seconds': invalid}).status_code == 422
    assert client.patch(path, headers=headers, json=payload).status_code == 200
    assert client.patch(path, headers=headers, json={**payload, 'refresh_interval_override_seconds': 120}).status_code == 409
    assert client.get(path, headers=headers).json()['refresh_interval_seconds'] == 60


def test_staggered_due_query_honors_override_and_platform_change(client, owner, db_session):
    headers, org_id, path = owner
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY, value={'enabled': True, 'refresh_interval_seconds': 3600}))
    db_session.commit()
    assert dashboard_snapshots.enqueue_due(db_session) == 1
    assert runner.run_once(db_session)
    row = db_session.scalar(select(DashboardSnapshot))
    generated = row.generated_at
    due = dashboard_snapshots.refresh_due_at(org_id, generated, 3600)
    assert timedelta(hours=1) <= due - generated <= timedelta(hours=1, minutes=5)
    assert dashboard_snapshots.enqueue_due(db_session, due - timedelta(microseconds=1)) == 0
    assert dashboard_snapshots.enqueue_due(db_session, due) == 1
    # A settings change leaves already-admitted work intact.
    assert client.patch(path, headers=headers, json={'expected_version': 0, 'refresh_interval_override_seconds': 60}).status_code == 200
    assert db_session.get(DashboardSnapshot, row.id).status == 'pending'
    assert runner.run_once(db_session)
    row = db_session.get(DashboardSnapshot, row.id, populate_existing=True)
    overridden_due = dashboard_snapshots.refresh_due_at(org_id, row.generated_at, 60)
    assert dashboard_snapshots.enqueue_due(db_session, overridden_due - timedelta(microseconds=1)) == 0
    assert dashboard_snapshots.enqueue_due(db_session, overridden_due) == 1


def test_changing_platform_interval_recalculates_inherited_schedule_without_catchup(client, owner, db_session):
    _, org_id, _ = owner
    config = PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY, value={'enabled': True, 'refresh_interval_seconds': 60})
    db_session.add(config); db_session.commit()
    dashboard_snapshots.enqueue_due(db_session)
    assert runner.run_once(db_session)
    row = db_session.scalar(select(DashboardSnapshot))
    generated = row.generated_at
    config.value = {'enabled': True, 'refresh_interval_seconds': 3600}
    db_session.commit()
    assert dashboard_snapshots.enqueue_due(db_session, generated + timedelta(minutes=2)) == 0
    assert dashboard_snapshots.enqueue_due(db_session, dashboard_snapshots.refresh_due_at(org_id, generated, 3600)) == 1


def test_sql_and_python_spread_agree_for_non_round_intervals(client, owner, db_session):
    _, org_id, _ = owner
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY, value={'enabled': True, 'refresh_interval_seconds': 65}))
    db_session.commit()
    dashboard_snapshots.enqueue_due(db_session)
    assert runner.run_once(db_session)
    generated = db_session.scalar(select(DashboardSnapshot)).generated_at
    due = dashboard_snapshots.refresh_due_at(org_id, generated, 65)
    assert dashboard_snapshots.enqueue_due(db_session, due - timedelta(microseconds=1)) == 0
    assert dashboard_snapshots.enqueue_due(db_session, due) == 1


def test_saved_age_warning_matches_the_staggered_deadline(client, owner, db_session, monkeypatch):
    headers, org_id, path = owner
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY, value={'enabled': True}))
    db_session.commit()
    dashboard_snapshots.enqueue_due(db_session)
    assert runner.run_once(db_session)
    generated = db_session.scalar(select(DashboardSnapshot)).generated_at
    due = dashboard_snapshots.refresh_due_at(org_id, generated, 3600)
    monkeypatch.setattr(dashboard_snapshots, 'now', lambda: due - timedelta(microseconds=1))
    assert not client.get(path.removesuffix('/settings'), headers=headers).json()['snapshot_stale']
    monkeypatch.setattr(dashboard_snapshots, 'now', lambda: due)
    assert client.get(path.removesuffix('/settings'), headers=headers).json()['snapshot_stale']
