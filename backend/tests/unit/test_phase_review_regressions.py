import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.models.enums import Domain
from app.schemas.report import ReportCreate
from app.schemas.report_ai import AuditReportSnapshot, RemediationActionAI
from app.services import claude_service, report_ai_service, sessions


def snapshot_data():
    return dict(title='Audit', executive_summary='Evidence', overall_score=90, overall_tier='low',
        resilience_summary='Evidence', domains=[dict(domain=d.value, score=90, tier='low', justification='Evidence') for d in Domain],
        remediations=[])


def test_renewal_enforces_shortened_idle_before_touch(monkeypatch):
    now = datetime.now(timezone.utc)
    session = SimpleNamespace(revoked_at=None, revoked_reason=None, expires_at=now + timedelta(days=7),
        created_at=now-timedelta(days=1), last_seen_at=now-timedelta(minutes=30), idle_minutes=480,
        user=SimpleNamespace(is_active=True))
    monkeypatch.setattr(sessions, 'session_from_cookie', lambda *a: session)
    monkeypatch.setattr(sessions, 'effective_policy', lambda *a: SimpleNamespace(idle_minutes=10, max_session_days=7))
    with pytest.raises(sessions.SessionEnded):
        sessions.renew(Mock(), 'cookie', now=now)
    assert session.revoked_reason == 'idle'


@pytest.mark.parametrize('configured', [False, True])
def test_ai_failure_does_not_fabricate_report(monkeypatch, configured):
    monkeypatch.setattr(report_ai_service.knowledge_service, 'require_report_consent', lambda *a: None)
    context = dict(total_assets=0, assets_by_category={}, total_findings=0, findings_by_severity={}, sample_findings=[], citations=[])
    monkeypatch.setattr(report_ai_service, '_gather_org_audit_context', lambda *a, **k: context)
    monkeypatch.setattr(report_ai_service.settings, 'ANTHROPIC_API_KEY', 'mock' if configured else '')
    monkeypatch.setattr(report_ai_service, 'ask_claude_structured', Mock(side_effect=TimeoutError('provider timeout')))
    with pytest.raises((RuntimeError, TimeoutError)):
        report_ai_service.generate_ai_audit_snapshot(Mock(), uuid.uuid4(), 'Audit')


def test_structured_prompt_includes_actual_schema(monkeypatch):
    raw = Mock(return_value=json.dumps(snapshot_data()))
    monkeypatch.setattr(claude_service, 'ask_claude', raw)
    claude_service.ask_claude_structured('Audit', AuditReportSnapshot)
    args, kwargs = raw.call_args
    supplied = str(args) + str(kwargs)
    assert 'overall_score' in supplied and 'required' in supplied and 'DomainScoreAI' in supplied


@pytest.mark.parametrize('change', [{'overall_tier': 'critical'}, {'domains': []},
    {'domains': [dict(domain='identity_access', score=90, tier='low', justification='x')]*7}])
def test_snapshot_rejects_inconsistent_scores_and_missing_domains(change):
    data = snapshot_data()
    data.update(change)
    with pytest.raises(ValidationError):
        AuditReportSnapshot.model_validate(data)


@pytest.mark.parametrize('field,value', [('priority', 'Urgent-ish'), ('estimated_effort', 'Unknown')])
def test_remediation_rejects_unknown_labels(field, value):
    data = dict(title='Patch', description='Updates', priority='High', domain='vulnerability_management',
                estimated_effort='Moderate', expected_impact='Reduced exposure')
    data[field] = value
    with pytest.raises(ValidationError):
        RemediationActionAI.model_validate(data)


def test_report_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        ReportCreate(title='Reversed', period_start='2026-02-01', period_end='2026-01-01')
