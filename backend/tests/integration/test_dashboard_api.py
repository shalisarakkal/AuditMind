from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import Domain, Severity
from app.models.finding import Finding
from app.services.scoring_service import overall_score, score_all_domains
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register, upload

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _dashboard(client, admin, headers=None):
    admin_headers, org_id = admin
    return client.get(f"/api/v1/orgs/{org_id}/dashboard", headers=headers or admin_headers)


def _seed(db_session, org_id, severity, minutes_ago, domain=Domain.vulnerability_management):
    finding = Finding(
        org_id=org_id,
        domain=domain,
        severity=severity,
        category=f"{severity.value}-{minutes_ago}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    db_session.add(finding)
    db_session.commit()
    return finding


def test_empty_org_is_not_assessed(client, admin):
    response = _dashboard(client, admin)
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()

    assert body["assessment_status"] == "not_assessed"
    assert (body["overall_score"], body["overall_tier"]) == (None, None)
    assert len(body["domains"]) == 7
    assert all(d["score"] is None and d["tier"] is None and d["assessment_status"] == "not_assessed" for d in body["domains"])
    assert body["top_findings"] == []
    assert body["recent_scans"] == []
    assert body["asset_count"] == 0
    assert body["findings_by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}


def test_scores_match_the_scoring_service_after_an_upload(client, admin, db_session):
    headers, org_id = admin
    upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "sample.nessus")

    body = _dashboard(client, admin).json()

    findings = db_session.query(Finding).all()
    expected_domains = score_all_domains(findings)
    expected_overall, expected_tier = overall_score(expected_domains)
    assert body["overall_score"] == pytest.approx(expected_overall)
    assert body["overall_tier"] == expected_tier.value
    assert {d["domain"]: d["score"] for d in body["domains"]} == {
        domain.value: score for domain, (score, _, _) in expected_domains.items()
    }
    vuln = next(d for d in body["domains"] if d["domain"] == "vulnerability_management")
    assert vuln["justification"]  # e.g. "1 critical finding(s); ..."
    assert body["asset_count"] == 2
    assert body["findings_by_severity"] == {"critical": 1, "high": 2, "medium": 2, "low": 1}
    assert [s["scan_type"] for s in body["recent_scans"]] == ["nessus"]


def test_top_findings_are_most_severe_then_newest(client, admin, db_session):
    _, org_id = admin
    _seed(db_session, org_id, Severity.low, 1)
    _seed(db_session, org_id, Severity.high, 50)
    _seed(db_session, org_id, Severity.critical, 30)
    _seed(db_session, org_id, Severity.high, 5)
    _seed(db_session, org_id, Severity.critical, 10)
    _seed(db_session, org_id, Severity.medium, 2)
    _seed(db_session, org_id, Severity.medium, 1)

    top = _dashboard(client, admin).json()["top_findings"]

    assert [f["category"] for f in top] == ["critical-10", "critical-30", "high-5", "high-50", "medium-1"]


def test_recent_scans_are_limited_to_five_newest(client, admin):
    headers, org_id = admin
    for n in range(6):
        upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, f"batch-{n}.csv", b"type,hostname\nserver,web\n")

    scans = _dashboard(client, admin).json()["recent_scans"]

    assert [s["filename"] for s in scans] == [f"batch-{n}.csv" for n in (5, 4, 3, 2, 1)]


def test_viewer_can_read_dashboard_but_outsiders_cannot(client, admin):
    admin_headers, org_id = admin
    viewer = member(client, admin_headers, org_id, "viewer")
    outsider = register(client, "someone@globex.io", "Globex")

    assert _dashboard(client, admin, viewer).status_code == 200
    assert _dashboard(client, admin, outsider).status_code == 403


def test_dashboard_only_counts_the_orgs_own_data(client, admin, db_session):
    _, org_id = admin
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)
    _seed(db_session, other_org, Severity.critical, 1)

    body = _dashboard(client, admin).json()

    assert body["overall_score"] is None
    assert body["assessment_status"] == "not_assessed"
    assert body["top_findings"] == []


def test_findings_without_assets_keep_existing_baseline(client, admin, db_session):
    _seed(db_session, admin[1], Severity.critical, 1)
    body = _dashboard(client, admin).json()
    assert body["asset_count"] == 0
    assert body["assessment_status"] == "findings_based"
    assert body["overall_score"] is not None


def test_asset_only_org_keeps_baseline_pending_coverage_design(client, admin):
    headers, org_id = admin
    upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "asset-only.csv", b"type,hostname\nserver,web\n")
    body = _dashboard(client, admin).json()
    assert body["asset_count"] == 1
    assert body["assessment_status"] == "findings_based"
    assert body["overall_score"] == 100


def test_archived_findings_do_not_make_empty_org_assessed(client, admin, db_session):
    finding = _seed(db_session, admin[1], Severity.critical, 1)
    finding.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    body = _dashboard(client, admin).json()
    assert body["assessment_status"] == "not_assessed"
    assert body["overall_score"] is None
