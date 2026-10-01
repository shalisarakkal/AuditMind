import pytest

from app.models.asset import Asset
from app.models.finding import Finding
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import first_org_id, register, upload

pytestmark = requires_db

DOMAINS = "identity_access, network_config, vulnerability_management, backup_recovery, monitoring_detection, incident_response, compliance_alignment"


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _upload(client, admin, filename, content=None):
    headers, org_id = admin
    return upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, filename, content)


def _url(admin, path):
    return f"/api/v1/orgs/{admin[1]}{path}"


def _findings(db_session):
    return db_session.query(Finding).order_by(Finding.created_at).all()


def test_generic_csv_creates_findings_and_missing_assets(client, admin, db_session):
    resp = _upload(client, admin, "findings_generic.csv")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    report = body["report"]
    assert (report["created"], report["failed"], report["duplicates"]) == (4, 2, 0)
    assert report["errors"] == [
        {"row": 6, "message": f"domain 'not_a_domain' must be one of: {DOMAINS}"},
        {"row": 7, "message": "severity 'urgent' must be one of: critical, high, medium, low"},
    ]

    findings = {f.category: f for f in _findings(db_session)}
    assert set(findings) == {"CVE-2024-3400", "MFA-DISABLED", "EDR-MISSING", "BACKUP-UNTESTED"}
    cve = findings["CVE-2024-3400"]
    assert (cve.domain.value, cve.severity.value, cve.source) == ("vulnerability_management", "critical", "pentest-2026")
    assert str(cve.scan_id) == body["scan_id"]
    assert cve.raw_data["description"] == "Unpatched remote code execution in web tier"
    assert findings["BACKUP-UNTESTED"].severity.value == "low"  # "Low" in the file
    assert findings["BACKUP-UNTESTED"].source == "manual"  # empty source column

    assets = db_session.query(Asset).all()
    assert {(a.hostname, a.ip, a.type) for a in assets} == {
        ("web-01.acme.io", "10.0.1.10", "server"),
        ("db-01.acme.io", "10.0.2.20", "server"),
        (None, "10.0.5.101", "server"),
        ("backup-01.acme.io", None, "server"),
    }
    assert db_session.get(Scan, body["scan_id"]).scan_type == "findings_csv"


def test_reuploading_the_same_findings_counts_duplicates(client, admin, db_session):
    _upload(client, admin, "findings_generic.csv")
    _upload(client, admin, "findings_generic.json")

    csv_again = _upload(client, admin, "findings_generic.csv").json()
    json_again = _upload(client, admin, "findings_generic.json").json()

    assert csv_again["status"] == "completed"
    assert (csv_again["report"]["created"], csv_again["report"]["duplicates"]) == (0, 4)
    assert (json_again["report"]["created"], json_again["report"]["duplicates"]) == (0, 3)
    assert len(_findings(db_session)) == 7
    # Each duplicate is listed with the upload whose finding it repeats.
    listed = csv_again["report"]["duplicate_rows"]
    assert len(listed) == 4
    assert {n["message"] for n in listed} == {"Same as a finding from findings_generic.csv"}
    assert listed[0]["row"] == 2 and listed[0]["item"].startswith("web-01.acme.io: ")


def test_uncategorised_findings_dedup_on_description(client, admin, db_session):
    content = (
        b"hostname,domain,severity,description\n"
        b"mail,incident_response,medium,No runbook\n"
        b"mail,incident_response,medium,No on-call rota\n"
        b"mail,incident_response,medium,No runbook\n"
    )
    report = _upload(client, admin, "f.csv", content).json()["report"]
    assert (report["created"], report["duplicates"]) == (2, 1)
    assert report["duplicate_rows"] == [{"row": 4, "item": "mail: No runbook", "message": "Same as row 2 of this file"}]


def test_findings_attach_to_inventory_assets(client, admin, db_session):
    headers, org_id = admin
    upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "assets_valid.csv")

    _upload(client, admin, "f.csv", b"hostname,ip,domain,severity\nWEB-01.ACME.IO,,network_config,high\nlaptop-9,10.0.5.101,monitoring_detection,low\n")

    assert db_session.query(Asset).count() == 4  # nothing new
    ip_only = db_session.query(Asset).filter(Asset.ip == "10.0.5.101").one()
    assert ip_only.hostname == "laptop-9"  # filled in from the finding
    assert {f.asset.hostname for f in _findings(db_session)} == {"web-01.acme.io", "laptop-9"}


def test_nessus_upload_maps_severity_domain_and_skips_info(client, admin, db_session):
    resp = _upload(client, admin, "sample.nessus")

    body = resp.json()
    assert body["status"] == "completed"
    report = body["report"]
    assert (report["created"], report["skipped"], report["failed"]) == (6, 2, 1)
    assert report["errors"] == [{"row": 8, "message": "invalid Nessus severity '9'"}]

    findings = {f.category: f for f in _findings(db_session)}
    assert {c: (f.severity.value, f.domain.value) for c, f in findings.items()} == {
        "Nessus 187095 (443/tcp)": ("critical", "vulnerability_management"),
        "Nessus 51192 (8443/tcp)": ("medium", "vulnerability_management"),
        "Nessus 51192 (443/tcp)": ("medium", "vulnerability_management"),
        "Nessus 18405 (3389/tcp)": ("high", "vulnerability_management"),
        "Nessus 10399": ("low", "identity_access"),
        "Nessus 42263": ("high", "network_config"),
    }
    apache = findings["Nessus 187095 (443/tcp)"]
    assert apache.source == "nessus"
    assert apache.description.startswith("Apache 2.4.x < 2.4.58 Multiple Vulnerabilities: ")
    assert apache.raw_data["cve"] == ["CVE-2023-45802", "CVE-2023-43622"]

    # The 10.0.3.30 host only had an Info item and a bad one: no asset for it.
    assert {(a.hostname, a.ip) for a in db_session.query(Asset)} == {
        ("web-01.acme.io", "10.0.1.10"),
        ("db-01", "10.0.2.20"),
    }
    assert db_session.get(Scan, body["scan_id"]).scan_type == "nessus"


def test_nessus_reupload_is_all_duplicates(client, admin, db_session):
    _upload(client, admin, "sample.nessus")
    report = _upload(client, admin, "sample.nessus").json()["report"]
    assert (report["created"], report["duplicates"], report["skipped"]) == (0, 6, 2)
    assert len(_findings(db_session)) == 6
    assert len(report["duplicate_rows"]) == 6
    skipped = report["skipped_rows"]
    assert len(skipped) == 2 and " Nessus " in skipped[0]["item"]
    assert skipped[0]["message"] == "Info severity: skipped, as Settings say (Nessus Info items: Skip them)"


def test_duplicates_of_a_finding_added_by_hand_say_so(client, admin):
    asset = client.post(_url(admin, "/assets"), headers=admin[0], json={"type": "server", "hostname": "mail"}).json()
    client.post(
        _url(admin, "/findings"),
        headers=admin[0],
        json={"asset_id": asset["id"], "domain": "incident_response", "severity": "low", "category": "IR-1", "source": "audit"},
    )
    content = b"hostname,domain,severity,category,source\nmail,incident_response,low,IR-1,audit\n"
    report = _upload(client, admin, "f.csv", content).json()["report"]
    assert report["duplicate_rows"] == [{"row": 2, "item": "mail: IR-1", "message": "Same as a finding added by hand"}]


@pytest.mark.parametrize("fixture", ["malicious_xxe.nessus", "billion_laughs.nessus"])
def test_malicious_nessus_files_are_rejected_safely(client, admin, db_session, fixture):
    body = _upload(client, admin, fixture).json()

    assert body["status"] == "failed"
    assert body["report"]["errors"] == [
        {"row": 0, "message": "Invalid .nessus file: DTDs and entity declarations are not allowed"}
    ]
    assert _findings(db_session) == []
    assert db_session.query(Asset).count() == 0


def test_nessus_file_with_no_findings_fails(client, admin):
    body = _upload(client, admin, "empty.nessus", b"<NessusClientData_v2><Report name='r'/></NessusClientData_v2>").json()
    assert body["status"] == "failed"
    assert body["report"]["errors"] == [{"row": 0, "message": "The .nessus file contains no findings"}]


def test_org_overrides_change_nessus_mapping(client, admin, db_session):
    headers, org_id = admin
    resp = client.patch(
        f"/api/v1/orgs/{org_id}/settings",
        headers=headers,
        json={
            "nessus_info_severity": "low",
            "nessus_domain_map": {"Web Servers": "network_config"},
            "nessus_default_domain": "compliance_alignment",
        },
    )
    assert resp.status_code == 200, resp.text

    report = _upload(client, admin, "sample.nessus").json()["report"]

    assert (report["created"], report["skipped"]) == (8, 0)  # Info items now recorded as low
    findings = {f.category: f for f in _findings(db_session)}
    assert findings["Nessus 187095 (443/tcp)"].domain.value == "network_config"  # org map
    assert findings["Nessus 18405 (3389/tcp)"].domain.value == "compliance_alignment"  # org default
    assert findings["Nessus 42263"].domain.value == "network_config"  # built-in map kept
    assert findings["Nessus 19506"].severity.value == "low"


def test_org_override_only_affects_that_org(client, admin, db_session):
    headers, org_id = admin
    client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"nessus_info_severity": "low"})
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)

    report = upload(client, f"/api/v1/orgs/{other_org}/findings/import", other, "sample.nessus").json()["report"]

    assert report["skipped"] == 2


def test_same_findings_in_another_org_are_not_duplicates(client, admin):
    _upload(client, admin, "findings_generic.json")
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)

    report = upload(client, f"/api/v1/orgs/{other_org}/findings/import", other, "findings_generic.json").json()["report"]

    assert (report["created"], report["duplicates"]) == (3, 0)

