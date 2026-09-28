"""The import-profiles API: built-ins plus each org's own copies."""

import pytest

from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register

pytestmark = requires_db

BUILTIN_KEYS = ["generic_assets", "generic_findings", "endpoint_agent", "network_scan", "cloud_inventory", "directory"]


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _url(admin, key=""):
    _, org_id = admin
    return f"/api/v1/orgs/{org_id}/import-profiles" + (f"/{key}" if key else "")


def _create(client, admin, headers=None, **body):
    return client.post(_url(admin), headers=headers or admin[0], json=body)


def test_builtins_are_listed_with_their_fields_and_settings(client, admin):
    profiles = client.get(_url(admin), headers=admin[0]).json()

    assert [p["key"] for p in profiles] == BUILTIN_KEYS
    endpoint = profiles[2]
    assert (endpoint["name"], endpoint["family"], endpoint["builtin"], endpoint["creates_assets"]) == (
        "Endpoint agent export", "endpoint_agent", True, True,
    )
    assert endpoint["column_map"]["hostname"] == "DeviceName|Hostname|ComputerName"
    assert endpoint["params"]["stale_after_days"] == 7
    assert endpoint["params"]["default_values"] == {"type": "workstation", "subtype": "endpoint"}
    assert {"name": "last_heartbeat", "label": "Last heartbeat", "detail": True} in endpoint["fields"]
    assert [(p["creates_assets"], p["creates_findings"]) for p in profiles] == [
        (True, False),  # generic asset list
        (False, True),  # generic findings
        (True, True),  # endpoint agent
        (True, True),  # network scan
        (True, False),  # cloud inventory
        (True, True),  # directory
    ]
    assert profiles[3]["params"]["risky_ports"]["23"] == {"label": "Telnet", "severity": "high"}


def test_copy_a_builtin_as_is(client, admin):
    resp = _create(client, admin, name="  Our scanner ", copy_from="network_scan")

    assert resp.status_code == 201, resp.text
    copy = resp.json()
    builtin = client.get(_url(admin, "network_scan"), headers=admin[0]).json()
    assert (copy["name"], copy["family"], copy["builtin"]) == ("Our scanner", "network_scan", False)
    assert (copy["column_map"], copy["params"]) == (builtin["column_map"], builtin["params"])
    assert copy["created_at"] is not None
    assert client.get(_url(admin, copy["key"]), headers=admin[0]).json() == copy


def test_copy_with_changes_then_copy_the_copy(client, admin):
    first = _create(
        client, admin, name="EDR", copy_from="endpoint_agent",
        column_map={"hostname": "Host"}, params={"stale_after_days": 30},
    ).json()
    assert (first["column_map"], first["params"]["stale_after_days"]) == ({"hostname": "Host"}, 30)
    # Settings not given take the defaults.
    assert first["params"]["threats_high_at"] == 1

    second = _create(client, admin, name="EDR 2", copy_from=first["key"]).json()
    assert (second["column_map"], second["params"]) == (first["column_map"], first["params"])

    names = [p["name"] for p in client.get(_url(admin), headers=admin[0]).json() if not p["builtin"]]
    assert names == ["EDR", "EDR 2"]


@pytest.mark.parametrize(
    "body, status, detail",
    [
        ({"copy_from": "nope"}, 404, "Unknown import profile 'nope'"),
        ({"copy_from": "endpoint_agent", "column_map": {"colour": "C"}}, 422, "column_map: 'colour' is not a field"),
        ({"copy_from": "endpoint_agent", "params": {"stale_after_days": 0}}, 422, "params.stale_after_days"),
        ({"copy_from": "endpoint_agent", "params": {"formula": "1"}}, 422, "params.formula"),
        ({"copy_from": "network_scan", "name": "Network Scan Export"}, 409, "A profile named"),
    ],
)
def test_create_errors(client, admin, body, status, detail):
    resp = _create(client, admin, **{"name": "Mine", **body})

    assert resp.status_code == status
    assert resp.json()["detail"].startswith(detail)
    assert len(client.get(_url(admin), headers=admin[0]).json()) == len(BUILTIN_KEYS)


def test_names_are_unique_per_org_ignoring_case(client, admin):
    _create(client, admin, name="EDR", copy_from="endpoint_agent")
    assert _create(client, admin, name="edr", copy_from="endpoint_agent").status_code == 409

    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)
    resp = client.post(
        f"/api/v1/orgs/{other_org}/import-profiles", headers=other, json={"name": "EDR", "copy_from": "endpoint_agent"}
    )
    assert resp.status_code == 201


def test_blank_name_is_rejected(client, admin):
    assert _create(client, admin, name="   ", copy_from="endpoint_agent").status_code == 422


def test_update_renames_and_replaces_parts(client, admin):
    key = _create(client, admin, name="EDR", copy_from="endpoint_agent", params={"stale_after_days": 30}).json()["key"]

    body = client.patch(_url(admin, key), headers=admin[0], json={"name": "EDR v2"}).json()
    assert (body["name"], body["params"]["stale_after_days"]) == ("EDR v2", 30)

    # params are replaced wholesale: omitted settings go back to the defaults.
    body = client.patch(_url(admin, key), headers=admin[0], json={"params": {"threats_high_at": 2}}).json()
    assert (body["params"]["threats_high_at"], body["params"]["stale_after_days"]) == (2, 7)

    body = client.patch(_url(admin, key), headers=admin[0], json={"column_map": {"hostname": "Name"}}).json()
    assert body["column_map"] == {"hostname": "Name"}
    assert body["params"]["threats_high_at"] == 2


def test_update_errors_leave_the_profile_unchanged(client, admin):
    created = _create(client, admin, name="EDR", copy_from="endpoint_agent").json()
    _create(client, admin, name="Other", copy_from="endpoint_agent")

    assert client.patch(_url(admin, created["key"]), headers=admin[0], json={"name": "other"}).status_code == 409
    resp = client.patch(_url(admin, created["key"]), headers=admin[0], json={"column_map": {}})
    assert (resp.status_code, resp.json()["detail"]) == (422, "column_map must map at least one field")
    assert client.patch(_url(admin, "endpoint_agent"), headers=admin[0], json={"name": "X"}).status_code == 400
    assert client.patch(_url(admin, "not-an-id"), headers=admin[0], json={"name": "X"}).status_code == 404

    assert client.get(_url(admin, created["key"]), headers=admin[0]).json() == created


def test_delete_keeps_past_scans(client, admin, db_session):
    headers, org_id = admin
    key = _create(client, admin, name="EDR", copy_from="endpoint_agent").json()["key"]
    client.post(
        f"/api/v1/orgs/{org_id}/imports",
        headers=headers,
        files={"file": ("e.csv", b"DeviceName\nDEV-1\n")},
        data={"profile": key},
    )

    assert client.delete(_url(admin, key), headers=headers).status_code == 204
    assert client.get(_url(admin, key), headers=headers).status_code == 404
    assert client.delete(_url(admin, key), headers=headers).status_code == 404
    assert client.delete(_url(admin, "endpoint_agent"), headers=headers).status_code == 400
    [scan] = db_session.query(Scan).all()
    assert (scan.profile, scan.summary["created"]) == (key, 1)


def test_only_admins_change_profiles_and_members_read_them(client, admin):
    headers, org_id = admin
    key = _create(client, admin, name="EDR", copy_from="endpoint_agent").json()["key"]
    auditor = member(client, headers, org_id, "auditor")
    viewer = member(client, headers, org_id, "viewer")

    for role_headers in (auditor, viewer):
        assert client.get(_url(admin, key), headers=role_headers).status_code == 200
        assert _create(client, admin, role_headers, name="X", copy_from="endpoint_agent").status_code == 403
        assert client.patch(_url(admin, key), headers=role_headers, json={"name": "X"}).status_code == 403
        assert client.delete(_url(admin, key), headers=role_headers).status_code == 403


def test_profiles_are_private_to_their_org(client, admin):
    key = _create(client, admin, name="EDR", copy_from="endpoint_agent").json()["key"]
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)

    # Not visible through the other org, and the owning org is off limits.
    assert client.get(f"/api/v1/orgs/{other_org}/import-profiles/{key}", headers=other).status_code == 404
    listed = client.get(f"/api/v1/orgs/{other_org}/import-profiles", headers=other).json()
    assert [p["key"] for p in listed] == BUILTIN_KEYS
    assert client.get(_url(admin, key), headers=other).status_code == 403
    resp = client.post(f"/api/v1/orgs/{other_org}/import-profiles", headers=other, json={"name": "Steal", "copy_from": key})
    assert resp.status_code == 404


# --- Asset type names: manual create and the org setting ------------------------


def _assets_url(admin):
    return f"/api/v1/orgs/{admin[1]}/assets"


def test_manual_asset_create_resolves_type_names(client, admin):
    headers = admin[0]

    body = client.post(_assets_url(admin), headers=headers, json={"type": "VM", "hostname": "vm-1"}).json()
    assert (body["type"], body["subtype"], body["details"]) == ("server", "VM", {})

    body = client.post(
        _assets_url(admin),
        headers=headers,
        json={"type": "Workstation", "subtype": "laptop", "hostname": "pc-1", "details": {"owner": "finance"}},
    ).json()
    assert (body["type"], body["subtype"], body["details"]) == ("workstation", "laptop", {"owner": "finance"})


def test_manual_asset_create_rejects_unknown_types(client, admin):
    resp = client.post(_assets_url(admin), headers=admin[0], json={"type": "Hologram", "hostname": "h"})

    assert resp.status_code == 422
    assert resp.json()["detail"].startswith("type 'Hologram' must be one of")
    assert client.get(_assets_url(admin), headers=admin[0]).json() == []


def test_org_type_names_apply_to_manual_create_and_generic_import(client, admin):
    headers, org_id = admin
    settings_url = f"/api/v1/orgs/{org_id}/settings"

    body = client.get(settings_url, headers=headers).json()
    assert body["asset_type_aliases"]["laptop"] == "workstation"
    assert body["asset_type_aliases_override"] == {}

    body = client.patch(settings_url, headers=headers, json={"asset_type_aliases": {" Hologram ": "application"}}).json()
    assert body["asset_type_aliases_override"] == {"Hologram": "application"}
    assert body["asset_type_aliases"]["Hologram"] == "application"
    assert "asset_type_aliases" in body["overridden"]

    created = client.post(_assets_url(admin), headers=headers, json={"type": "hologram", "hostname": "h1"}).json()
    assert (created["type"], created["subtype"]) == ("application", "hologram")
    report = client.post(
        f"{_assets_url(admin)}/import", headers=headers, files={"file": ("a.csv", b"type,hostname\nHologram,h2\n")}
    ).json()["report"]
    assert (report["created"], report["failed"]) == (1, 0)

    body = client.patch(settings_url, headers=headers, json={"asset_type_aliases": None}).json()
    assert "Hologram" not in body["asset_type_aliases"]
    assert client.post(_assets_url(admin), headers=headers, json={"type": "hologram", "hostname": "h3"}).status_code == 422


@pytest.mark.parametrize("aliases", [{"pc": "desk"}, {"": "server"}])
def test_invalid_type_names_are_rejected(client, admin, aliases):
    headers, org_id = admin
    resp = client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"asset_type_aliases": aliases})
    assert resp.status_code == 422
