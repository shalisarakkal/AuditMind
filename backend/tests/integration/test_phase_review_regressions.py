import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Domain, ReportStatus, Severity, UserRole
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.report import Report
from app.models.user import User
from app.services import people, platform, report_service
from app.services.report_ai_service import _gather_org_audit_context
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import first_org_id, register

pytestmark = requires_db


@pytest.fixture
def org(client):
    headers = register(client, 'review@example.com')
    return headers, first_org_id(client, headers)


def test_cloudtrail_accounts_do_not_collide(client, org):
    headers, org_id = org
    def upload(account):
        body = {'Records': [{'eventTime': '2026-06-01T12:00:00Z', 'eventName': 'ConsoleLogin',
                'userIdentity': {'type': 'Root', 'accountId': account}, 'recipientAccountId': account,
                'awsRegion': 'us-east-1', 'responseElements': {'ConsoleLogin': 'Success'}}]}
        response = client.post(f'/api/v1/orgs/{org_id}/imports', headers=headers,
            files={'file': ('trail.json', json.dumps(body).encode())},
            data={'profile': 'aws_cloudtrail', 'confirm': 'true'})
        assert response.status_code == 201, response.text
        return response.json()['report']
    assert upload('111111111111')['created'] == 1
    assert upload('222222222222')['created'] == 1
    assert upload('111111111111')['duplicates'] == 1


def test_restore_assetless_event_duplicates(client, org):
    headers, org_id = org
    url = f'/api/v1/orgs/{org_id}'
    body = [{'time': '2026-06-01', 'operation_name': 'Microsoft.Authorization/roleAssignments/write',
             'status': 'Succeeded', 'caller': 'ann', 'subscription_id': 'sub-1'}]
    def upload():
        response = client.post(url + '/imports', headers=headers,
            files={'file': ('events.json', json.dumps(body).encode())},
            data={'profile': 'azure_activity', 'confirm': 'true'})
        assert response.status_code == 201, response.text
    upload()
    scan_id = client.get(url + '/uploads', headers=headers).json()['items'][0]['id']
    response = client.post(url + f'/scans/{scan_id}/archive', headers=headers)
    assert response.status_code == 200, response.text
    upload()
    archived = client.get(url + '/archive?type=upload', headers=headers).json()
    item = archived['items'][0]
    restored = client.post(url + f"/archive/{item['id']}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()['summary']['duplicates_purged'] == 1
    assert client.get(url + '/findings', headers=headers).json()['total'] == 1


def test_stale_report_is_requeued(db_session):
    org = Organization(name='Recovery')
    db_session.add(org)
    db_session.flush()
    report = Report(org_id=org.id, title='Interrupted', status=ReportStatus.running,
                    heartbeat_at=datetime.now(timezone.utc) - timedelta(days=1), retry_count=0)
    db_session.add(report)
    db_session.commit()
    runner.reap_stale(db_session)
    db_session.refresh(report)
    assert report.status == ReportStatus.pending
    assert report.retry_count == 1


@pytest.mark.parametrize('retries,cancelled,expected', [(3, False, ReportStatus.failed), (0, True, ReportStatus.failed)])
def test_stale_report_terminal_cases(db_session, retries, cancelled, expected):
    org = Organization(name='Recovery limits')
    db_session.add(org)
    db_session.flush()
    report = Report(org_id=org.id, title='Interrupted', status=ReportStatus.running, retry_count=retries,
        heartbeat_at=datetime.now(timezone.utc) - timedelta(days=1),
        cancel_requested_at=datetime.now(timezone.utc) if cancelled else None)
    db_session.add(report)
    db_session.commit()
    runner.reap_stale(db_session)
    db_session.refresh(report)
    assert report.status == expected
    assert report.error_message


def test_live_report_is_not_reaped(db_session):
    from app.services.org_lock import REPORT_JOB, job_running
    org = Organization(name='Live')
    db_session.add(org)
    db_session.flush()
    report = Report(org_id=org.id, title='Live', status=ReportStatus.running,
                    heartbeat_at=datetime.now(timezone.utc) - timedelta(days=1))
    db_session.add(report)
    db_session.commit()
    with job_running(db_session, REPORT_JOB, report.id):
        runner.reap_stale(db_session)
        db_session.refresh(report)
        assert report.status == ReportStatus.running
    db_session.rollback()


@pytest.mark.parametrize('provider_fails', [False, True])
def test_running_report_cancellation_wins(db_session, monkeypatch, provider_fails):
    monkeypatch.setattr(report_service, 'require_report_consent', lambda *a: None)
    org = Organization(name='Cancellation')
    db_session.add(org)
    db_session.flush()
    report = Report(org_id=org.id, title='Cancel', status=ReportStatus.running)
    db_session.add(report)
    db_session.commit()
    def generate(**kwargs):
        with Session(db_session.get_bind()) as other:
            report_service.cancel_report_job(other, report.id, org.id)
        if provider_fails:
            raise TimeoutError('cancelled provider failed')
        return Mock(model_dump=lambda: {'overall_score': 90}, overall_score=90,
                    overall_tier=Mock(value='low'))
    monkeypatch.setattr(report_service, 'generate_ai_audit_snapshot', generate)
    report_service.process_report_job(db_session, report.id)
    db_session.refresh(report)
    assert report.status == ReportStatus.failed
    assert report.data is None
    assert 'cancelled' in report.error_message.lower()


def test_critical_findings_precede_medium(db_session, monkeypatch):
    org = Organization(name='Severity')
    db_session.add(org)
    db_session.flush()
    for index in range(21):
        db_session.add(Finding(org_id=org.id, domain=Domain.identity_access,
            severity=Severity.critical if index == 0 else Severity.medium, category=f'finding-{index}'))
    db_session.commit()
    monkeypatch.setattr('app.services.report_ai_service.retrieve_standards_for_findings', lambda *a, **k: [])
    context = _gather_org_audit_context(db_session, org.id)
    assert context['sample_findings'][0]['severity'] == 'critical'


def test_report_period_filters_findings(db_session, monkeypatch):
    monkeypatch.setattr(report_service, 'require_report_consent', lambda *a: None)
    from datetime import date
    org = Organization(name='Period')
    db_session.add(org)
    db_session.flush()
    for day in (1, 15, 31):
        db_session.add(Finding(org_id=org.id, domain=Domain.identity_access, severity=Severity.high,
            category=f'day-{day}', created_at=datetime(2026, 1, day, 23, 59, tzinfo=timezone.utc)))
    report = Report(org_id=org.id, title='January window', status=ReportStatus.running,
                    period_start=date(2026, 1, 15), period_end=date(2026, 1, 15))
    db_session.add(report)
    db_session.commit()
    captured = {}
    def generate(**kwargs):
        captured.update(kwargs)
        raise RuntimeError('stop before provider')
    monkeypatch.setattr(report_service, 'generate_ai_audit_snapshot', generate)
    with pytest.raises(RuntimeError):
        report_service.process_report_job(db_session, report.id)
    assert captured.get('period_start') == date(2026, 1, 15)
    monkeypatch.setattr('app.services.report_ai_service.retrieve_standards_for_findings', lambda *a, **k: [])
    context = _gather_org_audit_context(db_session, org.id, period_start=date(2026, 1, 15), period_end=date(2026, 1, 15))
    assert context['total_findings'] == 1
    assert context['sample_findings'][0]['category'] == 'day-15'


def test_list_report_has_summary_score_without_snapshot(client, org, db_session):
    headers, org_id = org
    db_session.add(Report(org_id=uuid.UUID(org_id), title='Complete', status=ReportStatus.completed,
                          data={'overall_score': 82, 'executive_summary': 'large snapshot'}))
    db_session.commit()
    item = client.get(f'/api/v1/orgs/{org_id}/reports', headers=headers).json()['items'][0]
    assert item.get('overall_score') == 82
    assert 'data' not in item


def test_concurrent_deactivation_keeps_admin(db_session, monkeypatch):
    org = Organization(name='Concurrent')
    actor = User(email='root-review@example.com', is_sysadmin=True, is_active=True)
    users = [User(email=f'admin-review-{i}@example.com', is_active=True) for i in range(2)]
    db_session.add_all([org, actor, *users])
    db_session.flush()
    db_session.add_all([OrgMembership(org_id=org.id, user_id=u.id, role=UserRole.admin) for u in users])
    db_session.commit()
    ids, actor_id, org_id = [u.id for u in users], actor.id, org.id
    barrier = threading.Barrier(2)
    original = people.orgs_needing
    def overlap(db, user):
        result = original(db, user)
        try:
            barrier.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass
        return result
    monkeypatch.setattr(people, 'orgs_needing', overlap)
    def deactivate(user_id):
        with Session(db_session.get_bind()) as db:
            try:
                platform.set_active(db, db.get(User, user_id), db.get(User, actor_id), False)
                db.commit()
                return 'deactivated'
            except people.PeopleError as exc:
                db.rollback()
                return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(deactivate, ids))
    assert sorted(outcomes) == ['deactivated', 'last_admin']
    db_session.expire_all()
    assert people._admins(db_session, org_id) == 1
