"""Persist and download real captured IDs, rejecting out-of-organization output."""
from uuid import UUID

import pytest

from app.core.config import settings
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.enums import Domain, ReportStatus, Severity
from app.models.knowledge import KnowledgeConsent
from app.models.report import Report
from app.schemas.report_ai import AuditReportSnapshot, DomainScoreAI, RemediationActionAI
from app.services import report_ai_service
from app.worker.runner import drain
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, approve_reports

pytestmark = requires_db


@pytest.mark.parametrize("case", ["valid", "assetless", "foreign-finding", "foreign-asset"])
def test_report_references_are_scoped_and_persisted(client, db_session, monkeypatch, case):
    headers = register(client, "reference-owner@example.com")
    org = UUID(first_org_id(client, headers))
    approve_reports(client, headers, str(org))
    other_headers = register(client, "reference-other@example.com")
    other_org = UUID(first_org_id(client, other_headers))
    asset = Asset(org_id=org, type="server", hostname="own-host")
    foreign_asset = Asset(org_id=other_org, type="server", hostname="other-host")
    db_session.add_all([asset, foreign_asset])
    db_session.flush()
    finding = Finding(org_id=org, asset_id=None if case == "assetless" else asset.id,
        domain=Domain.vulnerability_management, severity=Severity.high, description="Synthetic finding")
    foreign_finding = Finding(org_id=other_org, asset_id=foreign_asset.id,
        domain=Domain.vulnerability_management, severity=Severity.high, description="Other tenant evidence")
    db_session.add_all([finding, foreign_finding])
    db_session.commit()
    own_finding_id, own_asset_id = str(finding.id), str(asset.id)
    foreign_finding_id, foreign_asset_id = str(foreign_finding.id), str(foreign_asset.id)

    def provider(prompt, **kwargs):
        assert own_finding_id in prompt and foreign_finding_id not in prompt
        return AuditReportSnapshot(title="Synthetic", executive_summary="Evidence", resilience_summary="Evidence",
            overall_score=35, overall_tier="critical", domains=[DomainScoreAI(domain=d,
                score=35, tier="critical", justification="Evidence") for d in Domain],
            remediations=[RemediationActionAI(title="Patch", description="Address captured finding",
                priority="High", domain=Domain.vulnerability_management, estimated_effort="Moderate",
                expected_impact="Reduce exposure", confidence=.8,
                affected_finding_ids=[foreign_finding_id if case == "foreign-finding" else own_finding_id],
                affected_asset_ids=[] if case == "assetless" else [foreign_asset_id if case == "foreign-asset" else own_asset_id])])

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "synthetic")
    monkeypatch.setattr(report_ai_service, "ask_claude_structured", provider)
    queued = client.post(f"/api/v1/orgs/{org}/reports/generate", headers=headers, json={"title": "Reference audit"})
    assert queued.status_code == 202
    assert drain(db_session) == 1
    endpoint = f"/api/v1/orgs/{org}/reports/{queued.json()['id']}"
    detail = client.get(endpoint, headers=headers).json()
    if case.startswith("foreign"):
        assert detail["status"] == "failed" and detail["data"] is None
        assert client.get(endpoint + "/download?format=pdf", headers=headers).status_code == 400
    else:
        assert detail["status"] == "completed"
        action = detail["data"]["remediations"][0]
        assert action["confidence"] == .8 and action["affected_finding_ids"] == [own_finding_id]
        assert action["affected_asset_ids"] == ([] if case == "assetless" else [own_asset_id])
        html = client.get(endpoint + "/download?format=html", headers=headers)
        assert own_finding_id in html.text and "Model-estimated confidence: 80%" in html.text
        pdf = client.get(endpoint + "/download?format=pdf", headers=headers)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_legacy_report_is_not_revalidated_or_rewritten(client, db_session):
    headers = register(client, "legacy-reference@example.com")
    org = UUID(first_org_id(client, headers))
    data = {"overall_score": 35, "overall_tier": "high", "remediations": [{"title": "Legacy recommendation"}]}
    report = Report(org_id=org, title="Legacy", status=ReportStatus.completed, data=data)
    db_session.add(report)
    db_session.commit()
    endpoint = f"/api/v1/orgs/{org}/reports/{report.id}"
    response = client.get(endpoint, headers=headers)
    assert response.status_code == 200 and response.json()["data"] == data
    assert client.get(endpoint + "/download?format=pdf", headers=headers).status_code == 200
    db_session.refresh(report)
    assert report.data == data


def test_v1_consent_does_not_authorize_v2_generation(client, db_session):
    headers = register(client, "old-prompt-consent@example.com")
    org = UUID(first_org_id(client, headers))
    approve_reports(client, headers, str(org))
    consent = db_session.get(KnowledgeConsent, (org, "report"))
    consent.target = f"anthropic:{settings.CLAUDE_MODEL}:audit-evidence-v1"
    db_session.commit()
    response = client.post(f"/api/v1/orgs/{org}/reports/generate", headers=headers, json={"title": "Needs approval"})
    assert response.status_code == 409
    approve_reports(client, headers, str(org))
    assert client.post(f"/api/v1/orgs/{org}/reports/generate", headers=headers,
        json={"title": "New approval"}).status_code == 202
