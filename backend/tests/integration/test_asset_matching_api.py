"""Import matching by hostname + category: a row whose category is known only
merges into an asset of the same category, or one whose type was a guess
(a profile default, an unrecognised OS, a findings upload's placeholder)."""

import pytest

from tests.conftest import requires_db
from tests.helpers import first_org_id, register, upload

pytestmark = requires_db

FINDING = b"hostname,domain,severity,category,description,source\nHOST-1,vulnerability_management,high,CVE-1,Old,scan\n"


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _upload(client, admin, kind, content):
    headers, org_id = admin
    return upload(client, f"/api/v1/orgs/{org_id}/{kind}/import", headers, "a.csv", content).json()["report"]


def _profile_import(client, admin, profile, content):
    headers, org_id = admin
    resp = client.post(
        f"/api/v1/orgs/{org_id}/imports",
        headers=headers,
        files={"file": ("a.csv", content)},
        data={"profile": profile},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["report"]


def _assets(client, admin):
    headers, org_id = admin
    return client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers).json()["items"]


def test_a_name_shared_by_two_kinds_of_device_stays_two_assets(client, admin):
    _upload(client, admin, "assets", b"type,hostname\nserver,HOST-1\n")

    report = _upload(client, admin, "assets", b"type,hostname\nrouter,host-1\n")

    assert (report["created"], report["updated"]) == (1, 0)
    assert report["warnings"] == [
        {"row": 2, "message": "host-1 is already recorded as a server; this network_device was added as a separate asset"}
    ]
    assert sorted(a["type"] for a in _assets(client, admin)) == ["network_device", "server"]


def test_an_inventory_import_replaces_the_guessed_type_of_a_findings_host(client, admin):
    _upload(client, admin, "findings", FINDING)
    [placeholder] = _assets(client, admin)
    assert (placeholder["type"], placeholder["type_known"]) == ("server", False)

    report = _upload(client, admin, "assets", b"type,hostname\nLaptop,host-1\n")

    assert (report["created"], report["updated"], report["warnings"]) == (0, 1, [])
    [asset] = _assets(client, admin)
    assert asset["id"] == placeholder["id"]  # the finding stays on it
    assert (asset["type"], asset["subtype"], asset["type_known"]) == ("workstation", "Laptop", True)


def test_a_guessed_type_never_replaces_a_known_one(client, admin):
    _upload(client, admin, "assets", b"type,hostname\nserver,DEV-1\n")

    # The endpoint agent profile defaults the type to workstation: a guess.
    report = _profile_import(
        client,
        admin,
        "endpoint_agent",
        b"EndPointID,DeviceName,AgentVersion,LastHeartbeat,ThreatsDetected,ComplianceStatus\n"
        b"EP-1,DEV-1,v5.3,2026-09-27 10:00,0,Compliant\n",
    )

    assert (report["created"], report["updated"]) == (0, 1)
    [asset] = _assets(client, admin)
    assert (asset["type"], asset["subtype"], asset["type_known"]) == ("server", None, True)
    assert asset["details"]["agent_version"] == "v5.3"


def test_an_unrecognised_os_is_a_guess_that_a_directory_export_settles(client, admin):
    _profile_import(client, admin, "network_scan", b"IPAddress,Hostname,OSDetected\n10.0.0.1,HOST-1,Plan 9\n")
    [asset] = _assets(client, admin)
    assert (asset["type"], asset["type_known"]) == ("server", False)

    report = _profile_import(client, admin, "directory", b"AssetID,Hostname,Type,OS\nAD-1,HOST-1,Laptop,Windows 11\n")

    assert (report["created"], report["updated"]) == (0, 1)
    [asset] = _assets(client, admin)
    assert (asset["type"], asset["type_known"], asset["ip"]) == ("workstation", True, "10.0.0.1")


def test_a_finding_for_a_shared_name_goes_to_the_oldest_asset_with_a_warning(client, admin):
    _upload(client, admin, "assets", b"type,hostname\nserver,HOST-1\nrouter,HOST-1\n")

    report = _upload(client, admin, "findings", FINDING)

    assert report["created"] == 1
    assert report["warnings"] == [
        {
            "row": 2,
            "message": "HOST-1 matches 2 assets (network_device, server) and this row doesn't say which; "
            "recorded the finding on the server (the oldest)",
        }
    ]
    headers, org_id = admin
    [finding] = client.get(f"/api/v1/orgs/{org_id}/findings", headers=headers).json()["items"]
    server = next(a for a in _assets(client, admin) if a["type"] == "server")
    assert finding["asset_id"] == server["id"]
