import json

import pytest

from app.models.asset import Asset
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import first_org_id, register, upload

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _import(client, admin, filename, content=None):
    headers, org_id = admin
    return upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, filename, content)


def _assets(client, admin):
    headers, org_id = admin
    return client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers, params={"limit": 500}).json()["items"]


def test_csv_import_creates_assets_and_records_a_scan(client, admin, db_session):
    resp = _import(client, admin, "assets_valid.csv")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["report"] == {
        "created": 4,
        "updated": 0,
        "skipped": 0,
        "repeated": 0,
        "duplicates": 0,
        "failed": 0,
        "findings_created": 0,
        "errors": [],
        "warnings": [],
        "warnings_total": 0,
        "skipped_rows": [],
        "duplicate_rows": [],
    }

    assets = {a["hostname"] or a["ip"]: a for a in _assets(client, admin)}
    assert set(assets) == {"web-01.acme.io", "db-01.acme.io", "10.0.5.101", "s3-backups"}
    assert assets["web-01.acme.io"]["tags"] == ["web", "dmz"]
    assert assets["s3-backups"]["cloud_id"] == "arn:aws:s3:::acme-backups"

    scan = db_session.get(Scan, body["scan_id"])
    assert (scan.scan_type, scan.source, scan.filename) == ("asset_import", "upload", "assets_valid.csv")
    assert scan.status.value == "completed"
    assert scan.summary == body["report"]
    assert scan.completed_at is not None


def test_partial_import_reports_bad_rows_with_line_numbers(client, admin):
    body = _import(client, admin, "assets_with_errors.csv").json()

    assert body["status"] == "completed"
    report = body["report"]
    assert (report["created"], report["failed"]) == (2, 3)
    assert report["errors"] == [
        {
            "row": 3,
            "message": "type 'hologram' must be one of: server, workstation, network_device, database, "
            "cloud_resource, application, or a known name for one (see Settings > Asset type names)",
        },
        {"row": 4, "message": "hostname, ip or cloud_id is required"},
        {"row": 5, "message": "ip '999.1.1.1' is not a valid IP address"},
    ]
    assert {a["hostname"] for a in _assets(client, admin)} == {"app-01.acme.io", "fw-01.acme.io"}


def test_json_import_updates_matching_assets_by_default(client, admin):
    _import(client, admin, "assets_valid.csv")

    body = _import(client, admin, "assets_valid.json").json()

    # web-01 matches by hostname; 10.0.0.1 and crm are new.
    assert (body["report"]["created"], body["report"]["updated"]) == (2, 1)
    web = next(a for a in _assets(client, admin) if a["hostname"] == "web-01.acme.io")
    assert web["tags"] == ["web", "dmz"]
    assert web["criticality"] == "high"


def test_update_only_overwrites_non_empty_fields_and_matches_case_insensitively(client, admin):
    _import(client, admin, "a.csv", b"type,hostname,ip,environment,criticality\nserver,Web-01,10.0.0.1,prod,high\n")

    body = _import(client, admin, "b.csv", b"type,hostname,environment\nVM,WEB-01,staging\n").json()

    assert body["report"]["updated"] == 1
    [asset] = _assets(client, admin)
    assert (asset["type"], asset["subtype"]) == ("server", "VM")
    assert asset["environment"] == "staging"
    assert asset["criticality"] == "high"  # empty in the second file, kept
    assert asset["ip"] == "10.0.0.1"
    assert asset["hostname"] == "WEB-01"


def test_ip_only_match_never_merges_differently_named_hosts(client, admin):
    _import(client, admin, "a.csv", b"type,hostname,ip\nserver,alpha,10.0.0.1\nserver,,10.0.0.2\n")

    body = _import(client, admin, "b.csv", b"type,hostname,ip\nserver,beta,10.0.0.1\nserver,gamma,10.0.0.2\n").json()

    # beta shares alpha's IP but has another name: new asset. gamma adopts the
    # nameless 10.0.0.2 record.
    assert (body["report"]["created"], body["report"]["updated"]) == (1, 1)
    by_ip = {}
    for asset in _assets(client, admin):
        by_ip.setdefault(asset["ip"], set()).add(asset["hostname"])
    assert by_ip == {"10.0.0.1": {"alpha", "beta"}, "10.0.0.2": {"gamma"}}


def test_duplicate_rows_within_one_file_are_matched(client, admin):
    body = _import(client, admin, "a.csv", b"type,hostname\nserver,web\nserver,WEB\n").json()
    # The second row repeats the first: one asset, not one created and one updated.
    assert (body["report"]["created"], body["report"]["updated"], body["report"]["repeated"]) == (1, 0, 1)
    assert len(_assets(client, admin)) == 1


@pytest.mark.parametrize(
    "strategy, expected_report, expected_assets",
    [("skip", {"created": 0, "skipped": 1}, ["prod"]), ("duplicate", {"created": 1, "skipped": 0}, ["prod", "staging"])],
)
def test_existing_asset_strategy_from_env(client, admin, monkeypatch, strategy, expected_report, expected_assets):
    from app.core.config import settings

    _import(client, admin, "a.csv", b"type,hostname,environment\nserver,web,prod\n")
    monkeypatch.setattr(settings, "ASSET_EXISTING_STRATEGY", strategy)

    report = _import(client, admin, "b.csv", b"type,hostname,environment\nserver,web,staging\n").json()["report"]

    assert {k: report[k] for k in expected_report} == expected_report
    assert sorted(a["environment"] for a in _assets(client, admin)) == expected_assets
    if strategy == "skip":
        assert report["skipped_rows"] == [
            {
                "row": 2,
                "item": "web",
                "message": "Already recorded: left unchanged, as Settings say (Asset already in inventory: Leave it unchanged)",
            }
        ]


def test_all_or_nothing_writes_nothing_and_fails_the_scan(client, admin, monkeypatch, db_session):
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMPORT_PARTIAL_SUCCESS", False)
    resp = _import(client, admin, "assets_with_errors.csv")

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert (body["report"]["created"], body["report"]["failed"], len(body["report"]["errors"])) == (0, 3, 3)
    assert _assets(client, admin) == []
    assert db_session.get(Scan, body["scan_id"]).status.value == "failed"


def test_file_where_every_row_fails_is_marked_failed(client, admin):
    body = _import(client, admin, "a.csv", b"type,hostname\nhologram,a\n").json()
    assert body["status"] == "failed"
    assert body["report"]["failed"] == 1


@pytest.mark.parametrize(
    "filename, content, message",
    [
        ("empty.csv", b"", "The CSV file has no header row"),
        ("header-only.csv", b"type,hostname\n", "The file contains no rows"),
        ("bad.json", b"{oops", "Invalid JSON"),
        ("wrong-shape.json", json.dumps({"items": []}).encode(), 'Expected a JSON list of records, or {"assets": [...]}'),
        ("latin1.csv", "type,hostname\nserver,caf\xe9".encode("latin-1"), "The file is not valid UTF-8 text"),
    ],
)
def test_unreadable_files_fail_the_scan_with_a_file_level_error(client, admin, filename, content, message):
    resp = _import(client, admin, filename, content)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    [error] = body["report"]["errors"]
    assert error["row"] == 0
    assert error["message"].startswith(message)
    assert _assets(client, admin) == []


def test_unsupported_file_type_is_rejected_before_any_scan(client, admin, db_session):
    resp = _import(client, admin, "scan.nessus", b"<NessusClientData_v2/>")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unsupported file type; expected .csv, .json"
    assert db_session.query(Scan).count() == 0


def test_assets_are_scoped_to_the_org(client, admin, db_session):
    _import(client, admin, "assets_valid.csv")
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)

    body = upload(client, f"/api/v1/orgs/{other_org}/assets/import", other, "assets_valid.csv").json()

    # Same hostnames in another org are new assets there, not updates.
    assert body["report"]["created"] == 4
    assert db_session.query(Asset).count() == 8


def test_unusual_ips_are_imported_with_a_warning(client, admin):
    body = _import(client, admin, "a.csv", b"type,hostname,ip\nserver,lo,127.0.0.1\nlaptop,pc,10.0.0.9\n").json()

    assert body["status"] == "completed"
    assert (body["report"]["created"], body["report"]["failed"]) == (2, 0)
    assert body["report"]["warnings"] == [{"row": 2, "message": "ip 127.0.0.1 is a loopback address; imported anyway"}]
    assert {a["hostname"]: (a["type"], a["subtype"]) for a in _assets(client, admin)} == {
        "lo": ("server", None),
        "pc": ("workstation", "laptop"),
    }


def test_a_later_row_replaces_the_type_and_its_subtype_together(client, admin):
    # The same host twice: the last row wins, and "Workstation" (a category,
    # so no subtype) must not keep the earlier row's "Laptop" subtype.
    body = _import(client, admin, "a.csv", b"type,hostname\nLaptop,host-1\nWorkstation,host-1\n").json()

    assert (body["report"]["created"], body["report"]["updated"], body["report"]["repeated"]) == (1, 0, 1)
    [asset] = _assets(client, admin)
    assert (asset["type"], asset["subtype"]) == ("workstation", None)

    _import(client, admin, "a.csv", b"type,subtype,hostname\nworkstation,thin client,host-1\nLaptop,,host-1\n")
    [asset] = _assets(client, admin)
    assert (asset["type"], asset["subtype"]) == ("workstation", "Laptop")


def test_an_asset_listed_twice_with_different_values_is_warned_about(client, admin):
    content = (
        b"type,hostname,environment\n"
        b"Laptop,host-1,dev\n"
        b"server,host-2,prod\n"
        b"Desktop,HOST-1,prod\n"  # same host and category, other values
        b"server,host-2,prod\n"  # an exact repeat: no warning
    )

    report = _import(client, admin, "a.csv", content).json()["report"]

    assert (report["created"], report["updated"], report["repeated"]) == (2, 0, 2)
    assert report["warnings"] == [
        {
            "row": 4,
            "message": "HOST-1 appears on 2 rows with different values; later rows overwrite earlier ones (the last is row 4)",
        }
    ]


def test_no_repeat_warning_when_repeats_become_separate_assets(client, admin):
    headers, org_id = admin
    client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"asset_existing_strategy": "duplicate"})

    report = _import(client, admin, "a.csv", b"type,hostname\nLaptop,host-1\nServer,host-1\n").json()["report"]

    assert (report["created"], report["warnings"]) == (2, [])


def test_a_tool_export_imported_as_a_generic_list_explains_itself(client, admin):
    # Some rows also fail for another reason first (an unknown type name).
    records = [{"ResourceID": f"res-{i}", "Type": "Lambda"} for i in range(3)] + [{"ResourceID": "x", "Type": "Hologram"}]
    content = json.dumps(records).encode()

    report = _import(client, admin, "cloud_assets.json", content).json()["report"]

    assert (report["created"], report["failed"]) == (0, 4)
    assert report["errors"][0]["message"] == "hostname, ip or cloud_id is required"
    assert report["warnings"] == [
        {
            "row": 0,
            "message": "Nothing was imported: this file's columns (resourceid, type) don't match this source, which "
            "needs a hostname, ip or cloud_id column and expects type, hostname and/or ip or cloud_id, and "
            "optionally subtype, environment, criticality, tags. If the file is a tool's export or an event log "
            "(Azure Activity, CloudTrail, GCP Audit, endpoint security events), import it with that source.",
        }
    ]


def test_an_activity_log_imported_as_a_generic_list_explains_itself(client, admin):
    # Fails with "type is required", not the identity error: the note is about
    # the columns, whichever error the rows hit.
    columns = ["operation_id", "time", "operation_name", "subscription_id", "resource_group", "resource_type"]
    records = [dict.fromkeys(columns + ["status", "caller", "extra"], "x")]

    report = _import(client, admin, "azure_activity.json", json.dumps(records).encode()).json()["report"]

    assert report["errors"][0]["message"] == "type is required"
    [note] = report["warnings"]
    assert note["row"] == 0
    assert note["message"].startswith(
        "Nothing was imported: this file's columns (operation_id, time, operation_name, subscription_id, "
        "resource_group, resource_type, status, caller, ...) don't match this source"
    )

    headers, org_id = admin
    findings = upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "a.json", json.dumps(records).encode())
    assert "expects hostname and/or ip or cloud_id, domain, severity" in findings.json()["report"]["warnings"][0]["message"]


def test_no_source_note_for_a_generic_file_with_bad_values(client, admin):
    # The right columns, but nothing valid: the rows' own errors say why.
    report = _import(client, admin, "a.csv", b"type,hostname\nhologram,web-01\n").json()["report"]
    assert (report["created"], report["failed"], report["warnings"]) == (0, 1, [])


def test_no_source_hint_when_only_some_rows_lack_an_identity(client, admin):
    report = _import(client, admin, "a.csv", b"type,hostname\nserver,web-01\nserver,\n").json()["report"]

    assert (report["created"], report["failed"], report["warnings"]) == (1, 1, [])


def test_type_names_match_whatever_their_spacing(client, admin):
    content = b"type,hostname\nLoadBalancer,lb-1\nload-balancer,lb-2\nVIRTUAL_MACHINE,vm-1\n"

    report = _import(client, admin, "a.csv", content).json()["report"]

    assert (report["created"], report["failed"]) == (3, 0)
    assert {(a["hostname"], a["type"], a["subtype"]) for a in _assets(client, admin)} == {
        ("lb-1", "network_device", "LoadBalancer"),
        ("lb-2", "network_device", "load-balancer"),
        ("vm-1", "server", "VIRTUAL_MACHINE"),
    }


@pytest.mark.parametrize(
    "strategy, expected",
    [
        ("update", {"created": 1, "updated": 1, "skipped": 0, "repeated": 2}),
        ("skip", {"created": 1, "updated": 0, "skipped": 1, "repeated": 2}),
    ],
)
def test_each_asset_is_counted_once_and_its_other_rows_as_repeats(client, admin, monkeypatch, strategy, expected):
    """web was in the inventory, db is new; each is named twice more. The
    assets the upload names: created + updated + skipped = 2."""
    from app.core.config import settings

    _import(client, admin, "a.csv", b"type,hostname\nserver,web\n")
    monkeypatch.setattr(settings, "ASSET_EXISTING_STRATEGY", strategy)
    content = b"type,hostname,environment\nserver,web,prod\nserver,db,prod\nserver,web,test\nserver,db,test\n"
    report = _import(client, admin, "b.csv", content).json()["report"]
    assert {k: report[k] for k in expected} == expected
