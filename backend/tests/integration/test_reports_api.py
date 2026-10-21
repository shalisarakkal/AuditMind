"""Integration tests for reports API (queue, list, view, download, cancel, delete, roles)."""

import pytest
from io import BytesIO
from datetime import datetime, timezone
from zipfile import ZipFile
from uuid import UUID
from sqlalchemy import select, update

from app.core.config import settings
from app.models.enums import Domain, ReportStatus, Severity, UserRole
from app.models.event import Event
from app.models.finding import Finding
from app.models.report import Report
from app.services import report_service
from tests.conftest import requires_db
from tests.helpers import approve_reports, first_org_id, member, register

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "admin_reports@acmecorp.io")
    org_id = first_org_id(client, headers)
    approve_reports(client, headers, org_id)
    return headers, org_id


def test_report_generation_requires_explicit_consent(client):
    headers = register(client, "report_consent@acmecorp.io")
    org_id = first_org_id(client, headers)

    blocked = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Blocked without consent"},
    )
    assert blocked.status_code == 409, blocked.text
    assert "approve external AI report processing" in blocked.json()["detail"]

    approve_reports(client, headers, org_id)
    allowed = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Allowed after consent", "frameworks": ["CIS", "NIST"]},
    )
    assert allowed.status_code == 202, allowed.text
    data = allowed.json()
    assert data["title"] == "Allowed after consent"
    assert data["status"] == "pending"
    assert "CIS,NIST" in data["frameworks"]


def test_rule_based_test_report_is_opt_in_and_does_not_use_providers(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "RULE_BASED_TEST_REPORTS_ENABLED", False)
    headers = register(client, "rule_based_report@acmecorp.io")
    org_id = first_org_id(client, headers)
    endpoint = f"/api/v1/orgs/{org_id}/reports/rule-based-test"

    disabled = client.post(endpoint, headers=headers, json={"title": "Hidden test report"})
    assert disabled.status_code == 404
    assert client.get(f"/api/v1/orgs/{org_id}/reports/capabilities", headers=headers).json() == {
        "rule_based_test_enabled": False
    }

    monkeypatch.setattr(settings, "RULE_BASED_TEST_REPORTS_ENABLED", True)
    monkeypatch.setattr(
        report_service,
        "generate_ai_audit_snapshot",
        lambda **_: pytest.fail("Rule-based test report must not call the AI service"),
    )
    db_session.add(
        Finding(
            org_id=org_id,
            domain=Domain.identity_access,
            severity=Severity.critical,
            description="Test fixture finding",
        )
    )
    db_session.commit()

    capabilities = client.get(f"/api/v1/orgs/{org_id}/reports/capabilities", headers=headers)
    assert capabilities.status_code == 200
    assert capabilities.json() == {"rule_based_test_enabled": True}

    created = client.post(endpoint, headers=headers, json={"title": "Rule-based preview"})
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    detail = client.get(f"/api/v1/orgs/{org_id}/reports/{report_id}", headers=headers)
    assert detail.status_code == 200
    snapshot = detail.json()["data"]
    assert detail.json()["status"] == "completed"
    assert detail.json()["format"] == "json"
    assert detail.json()["assessment_type"] == "rule_based_test"
    assert detail.json()["frameworks"] is None
    assert snapshot["total_findings"] == 1
    assert snapshot["findings_by_severity"]["critical"] == 1
    assert snapshot["frameworks_evaluated"] == []
    assert snapshot["provenance"]["assessment_type"] == "rule_based_test"
    assert snapshot["provenance"]["external_processing"] is False
    assert snapshot["provenance"]["framework_evaluation"] == "not performed"

    listed = client.get(f"/api/v1/orgs/{org_id}/reports", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["assessment_type"] == "rule_based_test"
    label_filter = client.get(
        f"/api/v1/orgs/{org_id}/reports",
        headers=headers,
        params={"frameworks": "Rule-based test"},
    )
    assert label_filter.status_code == 200
    assert len(label_filter.json()["items"]) == 1
    global_search = client.get(
        f"/api/v1/orgs/{org_id}/reports",
        headers=headers,
        params={"q": "no framework assessment"},
    )
    assert global_search.status_code == 200
    assert len(global_search.json()["items"]) == 1

    downloaded = client.get(
        f"/api/v1/orgs/{org_id}/reports/{report_id}/download?format=html",
        headers=headers,
    )
    assert downloaded.status_code == 200
    assert "Rule-based test report — no external AI" in downloaded.text
    assert "does not evaluate framework controls" in downloaded.text

    event = db_session.scalar(
        select(Event).where(Event.org_id == org_id, Event.type == "report_test_generated")
    )
    assert event is not None
    assert event.item == "Rule-based preview"


def test_queue_report_generation(client, admin, db_session):
    headers, org_id = admin
    payload = {
        "title": "Annual Resilience Audit 2026",
        "frameworks": ["CIS", "NIST", "ISO"],
    }
    resp = client.post(f"/api/v1/orgs/{org_id}/reports/generate", headers=headers, json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["title"] == "Annual Resilience Audit 2026"
    assert data["status"] == "pending"
    assert "CIS,NIST,ISO" in data["frameworks"]
    queued_event = db_session.scalar(
        select(Event).where(Event.org_id == org_id, Event.type == "report_queued", Event.item == payload["title"])
    )
    assert queued_event is not None
    assert queued_event.actor_label == "admin_reports@acmecorp.io"


def test_list_reports_paged(client, admin):
    headers, org_id = admin
    # Create 2 reports
    client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Report Alpha", "frameworks": ["CIS"]},
    )
    client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Report Beta", "frameworks": ["NIST"]},
    )

    resp = client.get(f"/api/v1/orgs/{org_id}/reports", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert len(body["items"]) >= 2
    titles = [item["title"] for item in body["items"]]
    assert "Report Alpha" in titles
    assert "Report Beta" in titles


def test_list_reports_sort_filters_date_range_facets_and_paging(client, admin, db_session):
    headers, org_id = admin
    reports = [
        ("Cyber Audit Alpha", ["CIS"], ReportStatus.completed, 82, datetime(2026, 10, 4, tzinfo=timezone.utc)),
        ("Cyber Audit Beta", ["NIST", "ISO"], ReportStatus.failed, 45, datetime(2026, 10, 5, tzinfo=timezone.utc)),
        ("Legacy Audit Gamma", ["CIS"], ReportStatus.completed, 9, datetime(2026, 9, 4, tzinfo=timezone.utc)),
    ]
    for title, frameworks, report_status, score, created_at in reports:
        response = client.post(
            f"/api/v1/orgs/{org_id}/reports/generate",
            headers=headers,
            json={"title": title, "frameworks": frameworks},
        )
        assert response.status_code == 202, response.text
        db_session.execute(
            update(Report)
            .where(Report.id == response.json()["id"])
            .values(
                status=report_status,
                frameworks=",".join(frameworks),
                data={"overall_score": score},
                created_at=created_at,
            )
        )
    db_session.commit()
    base = f"/api/v1/orgs/{org_id}/reports"

    ascending_score = client.get(base, headers=headers, params={"sort": "score", "order": "asc"})
    assert ascending_score.status_code == 200, ascending_score.text
    assert [item["overall_score"] for item in ascending_score.json()["items"][:3]] == [9, 45, 82]

    filtered = client.get(
        base,
        headers=headers,
        params={"frameworks": "CIS", "status": ["completed"], "title": "Cyber"},
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["title"] for item in filtered.json()["items"]] == ["Cyber Audit Alpha"]

    date_filtered = client.get(base, headers=headers, params={"since": "2026-10-05", "until": "2026-10-05"})
    assert date_filtered.status_code == 200, date_filtered.text
    assert [item["title"] for item in date_filtered.json()["items"]] == ["Cyber Audit Beta"]

    searched = client.get(base, headers=headers, params={"q": "failed"})
    assert searched.status_code == 200, searched.text
    assert [item["title"] for item in searched.json()["items"]] == ["Cyber Audit Beta"]

    paged = client.get(base, headers=headers, params={"sort": "title", "order": "asc", "limit": 1, "offset": 1})
    assert paged.status_code == 200, paged.text
    assert paged.json()["total"] == 3
    assert len(paged.json()["items"]) == 1
    assert paged.json()["items"][0]["title"] == "Cyber Audit Beta"

    facets = client.get(f"{base}/facets", headers=headers)
    assert facets.status_code == 200, facets.text
    assert facets.json()["status"] == ["completed", "failed"]
    assert facets.json()["frameworks"] == ["CIS", "ISO", "NIST"]


def test_report_facets_are_scoped_and_include_rule_based_labels(client, admin, db_session):
    headers, org_id = admin
    base = f"/api/v1/orgs/{org_id}/reports"
    assert client.get(f"{base}/facets", headers=headers).json() == {"status": [], "frameworks": []}
    other = register(client, "other_facets@example.io")
    other_org = first_org_id(client, other)
    db_session.add_all([
        Report(org_id=UUID(org_id), title="Combined", frameworks="CIS, NIST,CIS", status=ReportStatus.completed),
        Report(org_id=UUID(org_id), title="Rule test", status=ReportStatus.completed,
               data={"provenance": {"assessment_type": "rule_based_test"}}),
        Report(org_id=UUID(other_org), title="Other", frameworks="ISO", status=ReportStatus.failed),
    ])
    db_session.commit()
    facets = client.get(f"{base}/facets", headers=headers)
    assert facets.status_code == 200
    assert facets.json() == {
        "status": ["completed"],
        "frameworks": ["CIS", "NIST", "Rule-based test · no framework assessment"],
    }
    assert client.get(f"{base}/facets", headers=other).status_code == 403
    filtered = client.get(base, headers=headers, params={"frameworks": "NIST"})
    assert [report["title"] for report in filtered.json()["items"]] == ["Combined"]


def test_viewer_cannot_generate_or_delete_report(client, admin):
    headers, org_id = admin
    viewer_headers = member(client, headers, org_id, UserRole.viewer.value)

    # 1. Viewer trying to generate report -> 403

    resp = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=viewer_headers,
        json={"title": "Viewer Report"},
    )
    assert resp.status_code == 403

    # Admin queues a report
    gen_resp = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Admin Report"},
    )
    rep_id = gen_resp.json()["id"]

    # 2. Viewer can view report -> 200
    view_resp = client.get(f"/api/v1/orgs/{org_id}/reports/{rep_id}", headers=viewer_headers)
    assert view_resp.status_code == 200

    # 3. Viewer cannot delete report -> 403
    del_resp = client.delete(f"/api/v1/orgs/{org_id}/reports/{rep_id}", headers=viewer_headers)
    assert del_resp.status_code == 403


def test_cancel_and_delete_report(client, admin, db_session):
    headers, org_id = admin
    gen_resp = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Report to Cancel"},
    )
    rep_id = gen_resp.json()["id"]

    # A running report must be cancelled, not silently deleted.
    delete_running = client.delete(f"/api/v1/orgs/{org_id}/reports/{rep_id}", headers=headers)
    assert delete_running.status_code == 409
    assert "Cancel report generation" in delete_running.json()["detail"]

    # Cancel
    cancel_resp = client.post(f"/api/v1/orgs/{org_id}/reports/{rep_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "failed"

    cancelled_event = db_session.scalar(
        select(Event).where(Event.org_id == org_id, Event.type == "report_cancelled", Event.item == "Report to Cancel")
    )
    assert cancelled_event is not None
    assert cancelled_event.actor_label == "admin_reports@acmecorp.io"

    # Delete
    del_resp = client.delete(f"/api/v1/orgs/{org_id}/reports/{rep_id}", headers=headers)
    assert del_resp.status_code == 204

    deleted_event = db_session.scalar(
        select(Event).where(Event.org_id == org_id, Event.type == "report_deleted", Event.item == "Report to Cancel")
    )
    assert deleted_event is not None
    assert deleted_event.actor_label == "admin_reports@acmecorp.io"

    # Verify deleted
    get_resp = client.get(f"/api/v1/orgs/{org_id}/reports/{rep_id}", headers=headers)
    assert get_resp.status_code == 404


def test_bulk_delete_reports_is_atomic_and_records_each_deletion(client, admin, db_session):
    headers, org_id = admin
    report_ids = []
    for title, report_status in (
        ("Finished report one", ReportStatus.completed),
        ("Failed report two", ReportStatus.failed),
        ("Running report", ReportStatus.running),
    ):
        response = client.post(
            f"/api/v1/orgs/{org_id}/reports/generate",
            headers=headers,
            json={"title": title},
        )
        assert response.status_code == 202, response.text
        report_ids.append(response.json()["id"])
        db_session.execute(
            update(Report).where(Report.id == response.json()["id"]).values(status=report_status)
        )
    db_session.commit()
    endpoint = f"/api/v1/orgs/{org_id}/reports/bulk-delete"

    blocked = client.post(endpoint, headers=headers, json={"ids": report_ids})
    assert blocked.status_code == 409, blocked.text
    assert "Cancel report generation" in blocked.json()["detail"]
    assert all(client.get(f"/api/v1/orgs/{org_id}/reports/{report_id}", headers=headers).status_code == 200 for report_id in report_ids)

    deleted = client.post(endpoint, headers=headers, json={"ids": report_ids[:2]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": 2}
    assert all(client.get(f"/api/v1/orgs/{org_id}/reports/{report_id}", headers=headers).status_code == 404 for report_id in report_ids[:2])
    assert client.get(f"/api/v1/orgs/{org_id}/reports/{report_ids[2]}", headers=headers).status_code == 200
    events = db_session.scalars(
        select(Event).where(Event.org_id == org_id, Event.type == "report_deleted")
    ).all()
    assert {event.item for event in events} >= {"Finished report one", "Failed report two"}


def test_bulk_delete_reports_requires_admin(client, admin):
    headers, org_id = admin
    generated = client.post(
        f"/api/v1/orgs/{org_id}/reports/generate",
        headers=headers,
        json={"title": "Report owned by admin"},
    )
    viewer_headers = member(client, headers, org_id, UserRole.viewer.value)

    response = client.post(
        f"/api/v1/orgs/{org_id}/reports/bulk-delete",
        headers=viewer_headers,
        json={"ids": [generated.json()["id"]]},
    )
    assert response.status_code == 403


def test_download_report_pdf_and_bulk_download_selected_pdfs(client, admin, db_session):
    headers, org_id = admin
    report_ids = []
    for title, report_status in (
        ("Finished report one", ReportStatus.completed),
        ("Finished report two", ReportStatus.generated),
        ("Failed report", ReportStatus.failed),
    ):
        response = client.post(
            f"/api/v1/orgs/{org_id}/reports/generate",
            headers=headers,
            json={"title": title},
        )
        assert response.status_code == 202, response.text
        report_id = response.json()["id"]
        report_ids.append(report_id)
        db_session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(
                status=report_status,
                generated_at=datetime.now(timezone.utc),
                data={
                    "overall_score": 82,
                    "overall_tier": "low",
                    "executive_summary": title,
                    "resilience_summary": "Test resilience summary.",
                    "domains": [],
                    "remediations": [],
                    "compliance_citations": [],
                    "provenance": {"assessment_type": "ai", "model": "test-model"},
                },
            )
        )
    db_session.commit()
    base = f"/api/v1/orgs/{org_id}/reports"

    single = client.get(
        f"{base}/{report_ids[0]}/download?format=pdf",
        headers=headers,
    )
    assert single.status_code == 200, single.text
    assert single.headers["content-type"] == "application/pdf"
    assert single.headers["content-disposition"].endswith(f"{report_ids[0]}.pdf\"")
    assert single.content.startswith(b"%PDF-")

    blocked = client.post(
        f"{base}/bulk-download",
        headers=headers,
        json={"ids": report_ids},
    )
    assert blocked.status_code == 409
    assert "Only completed reports can be downloaded" in blocked.json()["detail"]

    bulk = client.post(
        f"{base}/bulk-download",
        headers=headers,
        json={"ids": report_ids[:2]},
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(bulk.content)) as archive:
        assert len(archive.namelist()) == 2
        assert all(name.endswith(".pdf") for name in archive.namelist())
        assert all(archive.read(name).startswith(b"%PDF-") for name in archive.namelist())

    viewer_headers = member(client, headers, org_id, UserRole.viewer.value)
    viewer_download = client.post(
        f"{base}/bulk-download",
        headers=viewer_headers,
        json={"ids": report_ids[:1]},
    )
    assert viewer_download.status_code == 200
