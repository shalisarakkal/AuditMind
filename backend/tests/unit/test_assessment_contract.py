"""New contracts are strict; retained JSON snapshots are never reinterpreted."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import Domain
from app.schemas.report_ai import AuditReportSnapshot, DomainScoreAI, RemediationActionAI
from app.services import report_ai_service, report_service, scoring_service, knowledge_service
from app.core.assessment_contract import REPORT_PROMPT_VERSION


@pytest.mark.parametrize("score,tier", [(0,"critical"),(29,"critical"),(30,"critical"),
    (35,"critical"),(39,"critical"),(40,"high"),(59,"high"),(60,"medium"),
    (79,"medium"),(80,"low"),(100,"low")])
def test_shared_boundaries_apply_to_domains_overall_and_test_reports(score, tier):
    domains = [DomainScoreAI(domain=d, score=score, tier=tier, justification="Evidence") for d in Domain]
    snapshot = AuditReportSnapshot(title="Synthetic", executive_summary="Evidence", resilience_summary="Evidence",
        overall_score=score, overall_tier=tier, domains=domains, remediations=[])
    assert snapshot.overall_tier == scoring_service.tier_for_score(score)
    assert report_service._snapshot_tier(score) == snapshot.overall_tier


def action(**changes):
    return dict(title="Patch", description="Captured finding requires patching", priority="High",
        domain="vulnerability_management", estimated_effort="Moderate", expected_impact="Reduce exposure",
        confidence=.8, affected_finding_ids=[], affected_asset_ids=[], **changes)


@pytest.mark.parametrize("value", [-.1, 1.1, float("nan"), float("inf"), True, "0.8"])
def test_invalid_confidence_rejected(value):
    data = action()
    data["confidence"] = value
    with pytest.raises(ValidationError):
        RemediationActionAI.model_validate(data)


@pytest.mark.parametrize("field", ["confidence", "affected_finding_ids", "affected_asset_ids"])
def test_new_remediation_fields_are_explicitly_required(field):
    data = action()
    del data[field]
    with pytest.raises(ValidationError):
        RemediationActionAI.model_validate(data)


@pytest.mark.parametrize("field", ["affected_finding_ids", "affected_asset_ids"])
@pytest.mark.parametrize("bad_ids", [["not-a-uuid"], [str(uuid4())] * 2])
def test_malformed_and_duplicate_ids_rejected(field, bad_ids):
    data = action()
    data[field] = bad_ids
    with pytest.raises(ValidationError):
        RemediationActionAI.model_validate(data)


@pytest.mark.parametrize("case", ["valid", "assetless", "general", "foreign-finding", "unlinked-asset", "null-confidence"])
def test_generation_validates_references_against_captured_evidence(monkeypatch, case):
    finding, asset, other = uuid4(), uuid4(), uuid4()
    data = action()
    data.update(affected_finding_ids=[finding], affected_asset_ids=[asset])
    if case == "assetless":
        data["affected_asset_ids"] = []
    if case == "general":
        data.update(affected_finding_ids=[], affected_asset_ids=[])
    if case == "foreign-finding":
        data["affected_finding_ids"] = [other]
    if case == "unlinked-asset":
        data["affected_asset_ids"] = [other]
    if case == "null-confidence":
        data["confidence"] = None
    snapshot = AuditReportSnapshot(title="Synthetic", executive_summary="Evidence", resilience_summary="Evidence",
        overall_score=35, overall_tier="critical", domains=[DomainScoreAI(domain=d, score=35,
            tier="critical", justification="Evidence") for d in Domain], remediations=[RemediationActionAI(**data)])
    context = dict(total_assets=1, assets_by_category={}, total_findings=1, findings_by_severity={},
        sample_findings=[dict(finding_id=str(finding), asset_id=None if case == "assetless" else str(asset))],
        citations=[], rule_based={}, captured_at="2026-10-21T00:00:00Z", period_start=None, period_end=None)
    monkeypatch.setattr(report_ai_service.settings, "ANTHROPIC_API_KEY", "synthetic")
    monkeypatch.setattr(knowledge_service, "require_report_consent", Mock())
    monkeypatch.setattr(report_ai_service, "_gather_org_audit_context", Mock(return_value=context))
    provider = Mock(return_value=snapshot)
    monkeypatch.setattr(report_ai_service, "ask_claude_structured", provider)
    if case in {"foreign-finding", "unlinked-asset", "null-confidence"}:
        with pytest.raises(ValueError, match="AI remediation"):
            report_ai_service.generate_ai_audit_snapshot(Mock(), uuid4(), "Synthetic")
    else:
        result = report_ai_service.generate_ai_audit_snapshot(Mock(), uuid4(), "Synthetic")
        assert result.provenance["prompt_version"] == REPORT_PROMPT_VERSION
        assert result.model_dump(mode="json")["remediations"][0]["confidence"] == .8
        assert "high: 40-59" in provider.call_args.args[0]
    assert knowledge_service.report_target().endswith(REPORT_PROMPT_VERSION)


def test_legacy_rendering_preserves_old_tier_and_missing_reference_fields():
    stored = dict(overall_score=35, overall_tier="high", remediations=[{
        "title": "Legacy", "description": "Legacy", "priority": "High"}], domains=[])
    report = SimpleNamespace(title="Legacy", frameworks="NIST", generated_at=datetime.now(timezone.utc), data=stored)
    html = report_service.render_report_html(report)
    assert "35" in html and "High" in html and "Confidence: not recorded" in html
    assert report_service.render_report_pdf(report).startswith(b"%PDF")
    assert stored["overall_tier"] == "high" and "confidence" not in stored["remediations"][0]


def test_html_evidence_metadata_is_escaped():
    report = SimpleNamespace(title="Synthetic", frameworks="NIST", generated_at=None,
        data={"remediations": [{"affected_finding_ids": ["<script>bad</script>"], "confidence": .8}]})
    html = report_service.render_report_html(report)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Model-estimated confidence: 80% (not calibrated)" in html


def test_pdf_includes_confidence_and_reference_ids(monkeypatch):
    seen = []
    original = report_service.Paragraph
    def capture(text, style):
        seen.append(text)
        return original(text, style)
    monkeypatch.setattr(report_service, "Paragraph", capture)
    finding, asset = str(uuid4()), str(uuid4())
    report = SimpleNamespace(title="Synthetic", frameworks="NIST", generated_at=None,
        data={"remediations": [{"confidence": .8, "affected_finding_ids": [finding], "affected_asset_ids": [asset]}]})
    assert report_service.render_report_pdf(report).startswith(b"%PDF")
    assert any("Model-estimated confidence: 80% (not calibrated)" in line for line in seen)
    assert any(finding in line for line in seen) and any(asset in line for line in seen)
