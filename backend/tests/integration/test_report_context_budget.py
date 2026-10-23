"""Real PostgreSQL oversized evidence and post-budget reference allowlists."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.core.config import settings
from app.models.enums import Domain, ReportStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.report import Report
from app.schemas.report_ai import AuditReportSnapshot, DomainScoreAI, RemediationActionAI
from app.services import report_ai_service as service, knowledge_service, report_provider
from tests.conftest import requires_db

pytestmark = requires_db


def test_postgres_bounds_text_before_retrieval_and_preserves_original_hash(db_session, monkeypatch):
    org = Organization(name='Oversized UTF8 fixture'); db_session.add(org); db_session.flush()
    original = '界😀' * 10000
    finding = Finding(org_id=org.id, domain=Domain.identity_access, severity=Severity.high,
        category='界' * 90, description=original)
    db_session.add(finding); db_session.commit()
    def retrieve(db, findings, **kwargs):
        assert len(findings[0]['description'].encode('utf-8')) <= settings.REPORT_AI_FINDING_TEXT_BYTES
        return []
    monkeypatch.setattr(service, 'retrieve_standards_for_findings', retrieve)
    context = service._gather_org_audit_context(db_session, org.id, report_title='Bounded')
    captured = context['sample_findings'][0]
    assert len(captured['category'].encode('utf-8')) <= 256
    info = captured['text_limits']['description']
    assert info['original_bytes'] == len(original.encode('utf-8'))
    assert info['original_sha256'] == hashlib.sha256(original.encode('utf-8')).hexdigest()
    db_session.refresh(finding)
    assert finding.description == original


@pytest.mark.parametrize('reference', ['included', 'omitted'])
def test_oversized_capture_has_explicit_omissions_and_rejects_omitted_references(db_session, monkeypatch, reference):
    monkeypatch.setattr(settings, 'REPORT_AI_MAX_INPUT_BYTES', 16384)
    monkeypatch.setattr(settings, 'REPORT_AI_PROVIDER', 'anthropic')
    monkeypatch.setattr(report_provider, 'require_configured', lambda: None)
    monkeypatch.setattr(knowledge_service, 'require_report_consent', lambda *a: None)
    monkeypatch.setattr(service, 'retrieve_standards_for_findings', lambda *a, **kw: [])
    org = Organization(name='Budget allowlist fixture'); db_session.add(org); db_session.flush()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add_all([Finding(org_id=org.id, domain=Domain.identity_access, severity=Severity.high,
        description='untrusted source text ' * 1000, created_at=start + timedelta(seconds=i)) for i in range(20)])
    report = Report(org_id=org.id, title='Budget fixture', status=ReportStatus.running,
        data={'_processing_target': knowledge_service.report_target()})
    db_session.add(report); db_session.commit()
    read = service._gather_org_audit_context
    captured = {}
    def capture(*args, **kwargs):
        result = read(*args, **kwargs); captured.update(result); return result
    monkeypatch.setattr(service, '_gather_org_audit_context', capture)
    def provider(prompt, **kwargs):
        kwargs['before_attempt']()
        assert service.structured_input_bytes(prompt, AuditReportSnapshot) <= 16384
        assert captured['input_budget']['omitted_finding_ids']
        finding_id = captured['sample_findings'][0]['finding_id'] if reference == 'included' else captured['input_budget']['omitted_finding_ids'][0]
        return AuditReportSnapshot(title='Synthetic', executive_summary='Synthetic', resilience_summary='Limited',
            overall_score=60, overall_tier='medium',
            domains=[DomainScoreAI(domain=d, score=60, tier='medium', justification='Synthetic') for d in Domain],
            remediations=[RemediationActionAI(title='Review', description='Limited excerpt', priority='High',
                domain=Domain.identity_access, estimated_effort='Moderate', expected_impact='Verify', confidence=.5,
                affected_finding_ids=[UUID(finding_id)], affected_asset_ids=[])])
    monkeypatch.setattr(service, 'ask_claude_structured', provider)
    if reference == 'omitted':
        with pytest.raises(ValueError, match='outside captured evidence'):
            service.generate_ai_audit_snapshot(db_session, org.id, report.title, report_id=report.id)
    else:
        snapshot = service.generate_ai_audit_snapshot(db_session, org.id, report.title, report_id=report.id)
        assert snapshot.provenance['input_budget']['actual_input_bytes'] <= 16384
        assert snapshot.provenance['input_budget']['omitted_finding_ids']
        assert len(snapshot.provenance['sampled_findings']) < 20
        assert 'marked UTF-8 prefix' in snapshot.provenance['evidence_limitation']
        from app.services.report_service import render_report_html, render_report_pdf
        report.data = snapshot.model_dump(mode='json')
        assert 'omitted_finding_ids' in render_report_html(report)
        assert render_report_pdf(report).startswith(b'%PDF')
