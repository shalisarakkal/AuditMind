"""Integration tests for background worker report generation jobs and RAG execution."""

import pytest

from app.models.enums import ReportStatus
from app.models.report import Report
from app.services.standards_service import seed_standards_knowledge_base
from app.worker.runner import drain
from tests.conftest import requires_db
from tests.helpers import approve_reports, first_org_id, register, upload

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "admin_worker_reports@acmecorp.io")
    org_id = first_org_id(client, headers)
    approve_reports(client, headers, org_id)
    return headers, org_id


def test_worker_processes_report_job(client, admin, db_session, monkeypatch):
    from app.models.enums import Domain
    from app.models.event import Event
    from app.schemas.report_ai import AuditReportSnapshot, DomainScoreAI, RemediationActionAI
    from sqlalchemy import select
    monkeypatch.setattr("app.services.report_ai_service.settings.ANTHROPIC_API_KEY", "mock")
    monkeypatch.setattr("app.services.report_ai_service.ask_claude_structured", lambda *a, **k: AuditReportSnapshot(
        title="Mock", executive_summary="Mocked provider evidence", overall_score=70, overall_tier="medium",
        resilience_summary="Mocked evidence", domains=[DomainScoreAI(domain=d, score=70, tier="medium", justification="Mock") for d in Domain],
        remediations=[RemediationActionAI(title="Patch", description="Apply updates", priority="High",
            domain=Domain.vulnerability_management, estimated_effort="Moderate", expected_impact="Reduce exposure",
            confidence=0.8, affected_finding_ids=[], affected_asset_ids=[])],
    ))
    headers, org_id = admin

    # Report generation without an indexed corpus must disclose missing evidence.
    monkeypatch.setattr("app.services.knowledge_embeddings.embed", lambda profile, texts, **kw: [[1.0] + [0.0] * 1023 for _ in texts])

    # 2. Upload sample findings to provide audit context
    upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "sample.nessus")

    # 3. Queue an audit report
    resp = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Comprehensive Resilience Audit 2026", "frameworks": ["CIS", "NIST", "ISO"]},
    )
    assert resp.status_code == 202
    report_id = resp.json()["id"]

    # 4. Drain worker queue to process report
    ran = drain(db_session)
    assert ran >= 1

    # 5. Verify report is completed with rich snapshot
    get_resp = client.get(f"/api/v1/orgs/{org_id}/reports/{report_id}", headers=headers)
    assert get_resp.status_code == 200
    report_data = get_resp.json()
    assert report_data["status"] == "completed"
    assert report_data["data"] is not None

    snapshot = report_data["data"]
    assert "executive_summary" in snapshot
    assert "overall_score" in snapshot
    assert len(snapshot["domains"]) >= 5
    assert len(snapshot["remediations"]) >= 1

    # 6. Verify HTML download
    dl_resp = client.get(f"/api/v1/orgs/{org_id}/reports/{report_id}/download?format=html", headers=headers)
    assert dl_resp.status_code == 200
    assert "text/html" in dl_resp.headers["content-type"]
    assert "Comprehensive Resilience Audit 2026" in dl_resp.text
    assert "Executive Summary" in dl_resp.text
    generated_event = db_session.scalar(
        select(Event).where(
            Event.org_id == org_id,
            Event.type == "report_generated",
            Event.item == "Comprehensive Resilience Audit 2026",
        )
    )
    assert generated_event is not None
    assert generated_event.actor_label == "admin_worker_reports@acmecorp.io"


def test_anthropic_credit_failure_marks_report_failed_and_records_activity(client, admin, db_session, monkeypatch):
    from app.models.event import Event
    from sqlalchemy import select

    headers, org_id = admin
    monkeypatch.setattr(
        "app.services.report_service.generate_ai_audit_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError(
                "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
                "'message': 'Your credit balance is too low to access the Anthropic API.'}}"
            )
        ),
    )
    queued = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Credit failure audit"},
    )
    assert queued.status_code == 202

    assert drain(db_session) >= 1

    response = client.get(f"/api/v1/orgs/{org_id}/reports/{queued.json()['id']}", headers=headers)
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "failed"
    assert "insufficient credits" in report["error_message"]
    assert "generate a new report" in report["error_message"]

    failed_event = db_session.scalar(
        select(Event).where(Event.org_id == org_id, Event.type == "report_failed", Event.item == "Credit failure audit")
    )
    assert failed_event is not None
    assert "insufficient credits" in failed_event.details["error"]
