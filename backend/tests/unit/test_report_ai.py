"""Unit tests for AI report schemas and provider metadata."""

from app.models.enums import Domain, RiskTier
from app.schemas.report_ai import (
    AuditReportSnapshot,
    DomainScoreAI,
    RemediationActionAI,
)
import uuid
from unittest.mock import Mock

from app.services.report_ai_service import generate_ai_audit_snapshot


def test_audit_report_snapshot_schema():
    snapshot = AuditReportSnapshot(
        title="Q3 Resilience Audit",
        executive_summary="Organization exhibits good security posture.",
        overall_score=78,
        overall_tier=RiskTier.medium,
        resilience_summary="Strong network security, opportunities in vulnerability management.",
        domains=[
            DomainScoreAI(
                domain=domain,
                score=80,
                tier=RiskTier.low,
                justification="MFA enforced for all admins.",
                strengths=["MFA"],
                weaknesses=[],
            ) for domain in Domain
        ],
        remediations=[
            RemediationActionAI(
                title="Patch critical servers",
                description="Apply security updates",
                priority="High",
                domain=Domain.vulnerability_management,
                estimated_effort="Quick Win",
                expected_impact="Reduces RCE risk",
                related_controls=["CIS-7.1"],
                affected_asset_types=["server"],
            )
        ],
        compliance_citations=[],
        total_assets=10,
        total_findings=5,
    )
    assert snapshot.overall_score == 78
    assert snapshot.domains[0].domain == Domain.identity_access
    dump = snapshot.model_dump()
    assert dump["overall_tier"] == "medium"


def test_generate_report_preserves_server_metadata(monkeypatch):
    context = {
        "total_assets": 50,
        "total_findings": 12,
        "findings_by_severity": {"critical": 2, "high": 4, "medium": 6},
        "citations": [{"citation_id": "chunk-1", "control_id": "CIS-5.2", "title": "MFA", "framework": "CIS"}],
        "captured_at": "2026-10-08T12:00:00+00:00", "period_start": None, "period_end": None,
        "rule_based": {"overall_score": 60},
    }
    provider_snapshot = AuditReportSnapshot(
        title="Provider title", executive_summary="Mock evidence", overall_score=70, overall_tier="medium",
        resilience_summary="Mock evidence", domains=[DomainScoreAI(domain=d, score=70, tier="medium", justification="Mock") for d in Domain],
        remediations=[],
    )
    monkeypatch.setattr("app.services.report_ai_service.settings.ANTHROPIC_API_KEY", "mock")
    monkeypatch.setattr("app.services.knowledge_service.require_report_consent", lambda *a: None)
    monkeypatch.setattr("app.services.report_ai_service._gather_org_audit_context", lambda *a, **k: {**context, "assets_by_category": {}, "sample_findings": []})
    monkeypatch.setattr("app.services.report_ai_service.ask_claude_structured", lambda *a, **k: provider_snapshot)
    snapshot = generate_ai_audit_snapshot(Mock(), uuid.uuid4(), "Test Audit Report", ["CIS", "NIST"])
    assert snapshot.title == "Test Audit Report"
    assert snapshot.total_assets == 50
    assert snapshot.total_findings == 12
    assert len(snapshot.domains) >= 5
    assert snapshot.remediations == []
    assert snapshot.overall_score <= 100
    assert snapshot.overall_tier in [RiskTier.low, RiskTier.medium, RiskTier.high, RiskTier.critical]
