"""POST /orgs/{org_id}/imports: tool exports read with an import profile, each
row becoming an asset plus any findings, in one scan."""

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.import_profile import ImportProfile
from app.models.scan import Scan
from app.services import import_profiles
from tests.conftest import requires_db
from tests.helpers import FIXTURES, first_org_id, member, register

pytestmark = requires_db

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(import_profiles, "utc_now", lambda: NOW)


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _import(client, admin, filename, profile, content=None, headers=None):
    admin_headers, org_id = admin
    if content is None:
        content = (FIXTURES / filename).read_bytes()
    return client.post(
        f"/api/v1/orgs/{org_id}/imports",
        headers=headers or admin_headers,
        files={"file": (filename, content)},
        data={"profile": profile},
    )


def _assets(client, admin):
    headers, org_id = admin
    return {a["hostname"] or a["ip"]: a for a in client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers, params={"limit": 500}).json()["items"]}


def _findings(client, admin):
    headers, org_id = admin
    return client.get(f"/api/v1/orgs/{org_id}/findings", headers=headers, params={"limit": 500}).json()["items"]


def _counts(report):
    keys = ("created", "updated", "skipped", "findings_created", "duplicates", "failed")
    return {key: report[key] for key in keys}


# --- The three sample exports ---------------------------------------------------


def test_endpoint_agent_export(client, admin, db_session):
    resp = _import(client, admin, "endpoint_agents.csv", "endpoint_agent")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    report = body["report"]
    assert _counts(report) == {
        "created": 7, "updated": 0, "skipped": 0, "findings_created": 8, "duplicates": 0, "failed": 1,
    }
    assert report["errors"] == [{"row": 7, "message": "hostname, ip or cloud_id is required"}]
    assert report["warnings"] == [
        {"row": 8, "message": "LastHeartbeat 'not-a-date' isn't a date this profile can read; stale-agent check skipped"},
        {"row": 9, "message": "ThreatsDetected '-3' isn't a count; treated as 0"},
        {"row": 9, "message": "ComplianceStatus 'Unknown' isn't a recognised value; no finding recorded"},
    ]

    asset = _assets(client, admin)["DEV-446"]
    assert (asset["type"], asset["subtype"]) == ("workstation", "endpoint")
    assert asset["details"] == {"endpoint_id": "EP-00000", "agent_version": "v5.3", "last_heartbeat": "8/8/2026 21:14"}

    by_host = {}
    for finding in _findings(client, admin):
        by_host.setdefault(finding["asset_id"], []).append((finding["domain"], finding["severity"], finding["category"]))
        assert finding["source"] == "endpoint_agent"
    assert sorted(by_host[asset["id"]]) == [
        ("compliance_alignment", "low", "Endpoint compliance"),
        ("incident_response", "high", "Active threats detected"),
        ("monitoring_detection", "medium", "Endpoint agent not reporting"),
    ]

    scan = db_session.get(Scan, body["scan_id"])
    assert (scan.scan_type, scan.profile, scan.source, scan.filename) == (
        "endpoint_agent_import", "endpoint_agent", "upload", "endpoint_agents.csv",
    )
    assert scan.summary == report
    assert {f.scan_id for f in db_session.query(Finding)} == {scan.id}


def test_network_scan_export(client, admin):
    report = _import(client, admin, "network_scan.csv", "network_scan").json()["report"]

    assert _counts(report) == {
        "created": 7, "updated": 0, "skipped": 0, "findings_created": 12, "duplicates": 0, "failed": 1,
    }
    assert report["errors"] == [{"row": 8, "message": "ip '999.1.1.1' is not a valid IP address"}]
    assert [w["row"] for w in report["warnings"]] == [2, 4, 9, 9]
    assert report["warnings"][1]["message"] == "ip 127.12.12.238 is a loopback address; imported anyway"

    assets = _assets(client, admin)
    assert (assets["SRV-503"]["type"], assets["SRV-503"]["subtype"]) == ("network_device", "Cisco IOS 15")
    assert (assets["10.0.5.22"]["type"], assets["10.0.5.22"]["subtype"]) == ("workstation", "Windows 11")
    assert assets["SRV-194"]["details"]["open_ports"] == [135, 779, 370, 292, 155, 946, 396, 21]
    assert assets["SRV-460"]["ip"] == "127.12.12.238"

    categories = {(f["category"], f["severity"], f["domain"]) for f in _findings(client, admin)}
    assert ("Open port 23 (Telnet)", "high", "network_config") in categories
    assert ("SMBv1 Enabled", "critical", "vulnerability_management") in categories
    assert ("TLS1.0", "medium", "network_config") in categories


def test_cloud_inventory_export(client, admin):
    report = _import(client, admin, "cloud_inventory.csv", "cloud_inventory").json()["report"]

    assert (report["created"], report["failed"], report["findings_created"]) == (7, 1, 0)
    assert report["errors"][0]["row"] == 9
    assert report["errors"][0]["message"].startswith("type 'Hologram' must be one of")

    assets = _assets(client, admin)
    assert {name: (a["type"], a["subtype"]) for name, a in assets.items()} == {
        "web-prod-01": ("server", "VM"),
        "invoice-processor": ("cloud_resource", "Lambda"),
        "acme-backups": ("cloud_resource", "Bucket"),
        "web-prod-01-data": ("cloud_resource", "Storage"),
        "orders-db": ("database", None),
        "az-app-01": ("server", "Virtual Machine"),
        "LAPTOP-FIN-07": ("workstation", "Laptop"),
    }
    assert assets["invoice-processor"]["cloud_id"] == "arn:aws:lambda:us-east-1:111122223333:function:invoice-processor"
    assert assets["web-prod-01"]["details"] == {"region": "us-east-1"}
    assert assets["web-prod-01"]["tags"] == ["web", "dmz"]


def test_json_records_are_accepted(client, admin):
    content = json.dumps(
        {"records": [{"IPAddress": "10.2.2.2", "Hostname": "h1", "OSDetected": "Debian 12", "OpenPorts": [23]}]}
    ).encode()

    report = _import(client, admin, "scan.json", "network_scan", content).json()["report"]

    assert (report["created"], report["findings_created"]) == (1, 1)
    assert _assets(client, admin)["h1"]["details"] == {"os": "Debian 12", "open_ports": [23]}


# --- Re-imports, strategies, modes ------------------------------------------------


def test_reimport_updates_assets_and_skips_duplicate_findings(client, admin, db_session):
    _import(client, admin, "endpoint_agents.csv", "endpoint_agent")
    report = _import(client, admin, "endpoint_agents.csv", "endpoint_agent").json()["report"]

    assert _counts(report) == {
        "created": 0, "updated": 7, "skipped": 0, "findings_created": 0, "duplicates": 8, "failed": 1,
    }
    assert db_session.query(Asset).count() == 7
    assert db_session.query(Finding).count() == 8


def test_details_from_different_sources_are_merged(client, admin):
    _import(client, admin, "e.csv", "endpoint_agent", b"DeviceName,EndPointID,AgentVersion\nSRV-1,EP-9,v1\n")
    _import(client, admin, "e.csv", "endpoint_agent", b"DeviceName,AgentVersion\nSRV-1,v2\n")
    _import(client, admin, "n.csv", "network_scan", b"IPAddress,Hostname,OSDetected\n10.1.1.1,SRV-1,Ubuntu 24.04\n")

    asset = _assets(client, admin)["SRV-1"]
    assert asset["details"] == {"endpoint_id": "EP-9", "agent_version": "v2", "os": "Ubuntu 24.04"}
    # The latest source's classification wins, as for any updated field.
    assert (asset["type"], asset["subtype"], asset["ip"]) == ("server", "Ubuntu 24.04", "10.1.1.1")


def test_skip_strategy_leaves_assets_alone_but_records_their_findings(client, admin, db_session):
    headers, org_id = admin
    client.post(f"/api/v1/orgs/{org_id}/assets", headers=headers, json={"type": "server", "hostname": "DEV-446"})
    client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"asset_existing_strategy": "skip"})

    report = _import(client, admin, "endpoint_agents.csv", "endpoint_agent").json()["report"]

    assert (report["created"], report["skipped"], report["findings_created"]) == (6, 1, 8)
    asset = _assets(client, admin)["DEV-446"]
    assert (asset["type"], asset["details"]) == ("server", {})
    assert db_session.query(Finding).filter(Finding.asset_id == asset["id"]).count() == 3


def test_all_or_nothing_writes_nothing_but_still_reports_warnings(client, admin, db_session):
    headers, org_id = admin
    client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"import_partial_success": False})

    body = _import(client, admin, "endpoint_agents.csv", "endpoint_agent").json()

    assert body["status"] == "failed"
    assert (body["report"]["failed"], len(body["report"]["warnings"])) == (1, 3)
    assert db_session.query(Asset).count() == 0
    assert db_session.query(Finding).count() == 0


def test_warnings_alone_never_fail_an_import(client, admin):
    headers, org_id = admin
    client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"import_partial_success": False})

    body = _import(client, admin, "n.csv", "network_scan", b"IPAddress,Hostname,OpenPorts\n127.0.0.1,lo,x\n").json()

    assert body["status"] == "completed"
    assert (body["report"]["created"], body["report"]["failed"], len(body["report"]["warnings"])) == (1, 0, 3)


def test_large_files_are_imported_in_the_background(client, admin, monkeypatch):
    headers, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)

    resp = _import(client, admin, "network_scan.csv", "network_scan")

    assert resp.status_code == 202
    scan = client.get(f"/api/v1/orgs/{org_id}/scans/{resp.json()['scan_id']}", headers=headers).json()
    assert (scan["status"], scan["profile"], scan["scan_type"]) == ("completed", "network_scan", "network_scan_import")
    assert (scan["summary"]["created"], scan["summary"]["findings_created"]) == (7, 12)


def test_generic_profiles_match_the_plain_import_endpoints(client, admin):
    assets_report = _import(client, admin, "assets_valid.csv", "generic_assets").json()["report"]
    findings_report = _import(client, admin, "findings_generic.csv", "generic_findings").json()["report"]

    assert (assets_report["created"], assets_report["findings_created"]) == (4, 0)
    # A findings-only profile counts findings as created, like /findings/import.
    assert (findings_report["created"], findings_report["findings_created"], findings_report["failed"]) == (4, 0, 2)


# --- Custom profiles -------------------------------------------------------------


def test_custom_profile_reads_renamed_columns_with_its_own_settings(client, admin, db_session):
    headers, org_id = admin
    profile = client.post(
        f"/api/v1/orgs/{org_id}/import-profiles",
        headers=headers,
        json={
            "name": "Our EDR",
            "copy_from": "endpoint_agent",
            "column_map": {"hostname": "Device_Name", "threats_detected": "Threats", "last_heartbeat": "Seen"},
            "params": {"threats_high_at": 3, "stale_after_days": 60, "default_values": {"type": "workstation", "environment": "production"}},
        },
    ).json()
    content = b"Device_Name,Threats,Seen\nPC-1,2,8/8/2026 21:14\nPC-2,4,7/1/2026 11:30\n"

    body = _import(client, admin, "edr.csv", profile["key"], content).json()

    assert (body["report"]["created"], body["report"]["findings_created"]) == (2, 2)
    assets = _assets(client, admin)
    assert (assets["PC-1"]["environment"], assets["PC-1"]["type"]) == ("production", "workstation")
    findings = {(f["category"], f["severity"]) for f in _findings(client, admin)}
    assert findings == {("Active threats detected", "high"), ("Endpoint agent not reporting", "medium")}
    assert db_session.get(Scan, body["scan_id"]).profile == profile["key"]


def test_findings_from_a_copy_dedup_against_the_builtin(client, admin):
    headers, org_id = admin
    copy = client.post(
        f"/api/v1/orgs/{org_id}/import-profiles", headers=headers, json={"name": "Copy", "copy_from": "endpoint_agent"}
    ).json()

    _import(client, admin, "endpoint_agents.csv", "endpoint_agent")
    report = _import(client, admin, "endpoint_agents.csv", copy["key"]).json()["report"]

    assert (report["findings_created"], report["duplicates"]) == (0, 8)


def test_a_profile_saved_with_stale_settings_fails_the_scan_cleanly(client, admin, db_session):
    headers, org_id = admin
    copy = client.post(
        f"/api/v1/orgs/{org_id}/import-profiles", headers=headers, json={"name": "Copy", "copy_from": "network_scan"}
    ).json()
    # Simulate settings that no longer validate (e.g. after a rule change).
    row = db_session.get(ImportProfile, uuid.UUID(copy["key"]))
    row.params = {"risk_high_at": 99}
    db_session.commit()

    resp = _import(client, admin, "network_scan.csv", copy["key"])

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("Import profile 'Copy' is invalid")
    assert db_session.query(Scan).count() == 0


# --- Request errors ------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, profile, status, detail",
    [
        ("e.csv", "no_such_profile", 400, "Unknown import profile 'no_such_profile'"),
        ("e.csv", "00000000-0000-0000-0000-000000000000", 400, "Unknown import profile"),
        ("scan.nessus", "network_scan", 400, "Unsupported file type; expected .csv, .json"),
        ("e.xlsx", "endpoint_agent", 400, "Unsupported file type"),
    ],
)
def test_bad_requests(client, admin, db_session, filename, profile, status, detail):
    resp = _import(client, admin, filename, profile, b"DeviceName\nDEV-1\n")

    assert resp.status_code == status
    assert resp.json()["detail"].startswith(detail)
    assert db_session.query(Scan).count() == 0


def test_profile_field_is_required(client, admin):
    headers, org_id = admin
    resp = client.post(f"/api/v1/orgs/{org_id}/imports", headers=headers, files={"file": ("e.csv", b"a\n1\n")})
    assert resp.status_code == 422


def test_another_orgs_profile_cannot_be_used(client, admin):
    headers, org_id = admin
    copy = client.post(
        f"/api/v1/orgs/{org_id}/import-profiles", headers=headers, json={"name": "Mine", "copy_from": "endpoint_agent"}
    ).json()
    other = register(client, "other@globex.io", "Globex")

    resp = _import(client, (other, first_org_id(client, other)), "e.csv", copy["key"], b"DeviceName\nDEV-1\n")

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("Unknown import profile")


def test_viewers_cannot_import(client, admin, db_session):
    headers, org_id = admin
    viewer = member(client, headers, org_id, "viewer")

    resp = _import(client, admin, "endpoint_agents.csv", "endpoint_agent", headers=viewer)

    assert resp.status_code == 403
    assert db_session.query(Scan).count() == 0


def test_oversized_upload_is_rejected_before_authentication(client, admin, monkeypatch, db_session):
    _, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", 100)

    resp = client.post(
        f"/api/v1/orgs/{org_id}/imports",
        files={"file": ("big.csv", b"DeviceName\n" + b"DEV-1\n" * 400_000)},
        data={"profile": "endpoint_agent"},
    )

    assert resp.status_code == 413
    assert db_session.query(Scan).count() == 0


# --- Cloud IDs and directory exports ---------------------------------------------


def test_cloud_resources_are_matched_by_their_cloud_id(client, admin, db_session):
    first = _import(client, admin, "cloud_assets.json", "cloud_inventory").json()["report"]
    assert (first["created"], first["failed"]) == (4, 2)
    assert first["errors"] == [
        {"row": 5, "message": first["errors"][0]["message"]},
        {"row": 6, "message": "hostname, ip or cloud_id is required"},
    ]
    assert first["errors"][0]["message"].startswith("type 'Hologram' must be one of")

    again = _import(client, admin, "cloud_assets.json", "cloud_inventory").json()["report"]
    assert (again["created"], again["updated"]) == (0, 4)

    assets = {a.cloud_id: a for a in db_session.query(Asset)}
    assert set(assets) == {"res-00001", "res-00002", "res-00003", "res-00004"}
    lam = assets["res-00001"]
    assert (lam.type, lam.subtype, lam.hostname, lam.tags) == ("cloud_resource", "Lambda", None, ["env:prod", "app:risk"])
    assert lam.details == {"region": "us-east-1", "provider": "Azure", "owner": "team1", "status": "Running"}


def test_a_different_cloud_id_is_a_different_resource_even_with_the_same_name(client, admin, db_session):
    content = b"ResourceID,ResourceName,ResourceType\ni-1,web,VM\ni-2,web,VM\ni-1,web-renamed,VM\n"

    report = _import(client, admin, "c.csv", "cloud_inventory", content).json()["report"]

    assert (report["created"], report["updated"]) == (2, 1)
    names = {a.cloud_id: a.hostname for a in db_session.query(Asset)}
    assert names == {"i-1": "web-renamed", "i-2": "web"}


def test_a_name_only_asset_is_matched_by_a_row_that_adds_its_cloud_id(client, admin, db_session):
    headers, org_id = admin
    client.post(f"/api/v1/orgs/{org_id}/assets", headers=headers, json={"type": "server", "hostname": "web"})

    report = _import(client, admin, "c.csv", "cloud_inventory", b"ResourceID,ResourceName,ResourceType\ni-1,web,VM\n").json()["report"]

    assert (report["created"], report["updated"]) == (0, 1)
    [asset] = db_session.query(Asset).all()
    assert (asset.hostname, asset.cloud_id) == ("web", "i-1")


def test_findings_can_name_just_a_cloud_id(client, admin, db_session):
    content = b'[{"cloud_id": "arn:aws:s3:::logs", "domain": "backup_recovery", "severity": "high", "category": "No versioning"}]'

    report = _import(client, admin, "f.json", "generic_findings", content).json()["report"]

    assert (report["created"], report["failed"]) == (1, 0)
    [asset] = db_session.query(Asset).all()
    assert (asset.type, asset.cloud_id, asset.hostname) == ("cloud_resource", "arn:aws:s3:::logs", None)


def test_directory_export(client, admin):
    report = _import(client, admin, "active_directory.csv", "directory").json()["report"]

    assert _counts(report) == {
        "created": 5, "updated": 0, "skipped": 0, "findings_created": 2, "duplicates": 0, "failed": 1,
    }
    assert report["errors"] == [{"row": 7, "message": "hostname, ip or cloud_id is required"}]
    assert [w["row"] for w in report["warnings"]] == [5, 6]

    assets = _assets(client, admin)
    assert (assets["HOST-102"]["type"], assets["HOST-102"]["subtype"]) == ("workstation", "Laptop")
    assert (assets["HOST-103"]["type"], assets["HOST-103"]["subtype"]) == ("workstation", "macOS 14")
    assert assets["HOST-101"]["details"]["owner"] == "user1@acme.io"
    findings = {(f["category"], f["severity"], f["domain"]) for f in _findings(client, admin)}
    assert findings == {
        ("Disabled directory account", "low", "identity_access"),
        ("Stale directory account", "medium", "identity_access"),
    }


def test_warnings_beyond_the_report_limit_are_still_counted(client, admin, monkeypatch):
    from app.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "MAX_REPORTED_ERRORS", 2)
    content = b"IPAddress,Hostname,OSDetected\n127.0.0.1,a,Linux\n127.0.0.2,b,Linux\n127.0.0.3,c,Linux\n"

    report = _import(client, admin, "n.csv", "network_scan", content).json()["report"]

    assert (len(report["warnings"]), report["warnings_total"]) == (2, 3)


def test_repeated_hosts_in_a_directory_export_are_warned_about_in_row_order(client, admin):
    content = (
        b"AssetID,Hostname,Type,OS,Status\n"
        b"AD-1,HOST-1,Server,Ubuntu 22.04,Active\n"
        b"AD-2,HOST-2,Laptop,Windows 11,Active\n"
        b"AD-3,HOST-1,VM,Ubuntu 24.04,Quarantined\n"
    )

    report = _import(client, admin, "ad.csv", "directory", content).json()["report"]

    assert [(w["row"], w["message"][:40]) for w in report["warnings"]] == [
        (4, "Status 'Quarantined' isn't a recognised "),
        (4, "HOST-1 appears on 2 rows with different "),
    ]
    assert _assets(client, admin)["HOST-1"]["subtype"] == "VM"
