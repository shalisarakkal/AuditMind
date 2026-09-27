import pytest

from app.core.config import settings
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _get(client, admin, headers=None):
    admin_headers, org_id = admin
    return client.get(f"/api/v1/orgs/{org_id}/settings", headers=headers or admin_headers)


def _patch(client, admin, body, headers=None):
    admin_headers, org_id = admin
    return client.patch(f"/api/v1/orgs/{org_id}/settings", json=body, headers=headers or admin_headers)


def test_new_org_uses_global_defaults(client, admin):
    body = _get(client, admin).json()

    assert body["import_partial_success"] is True
    assert body["asset_existing_strategy"] == "update"
    assert body["nessus_info_severity"] == "skip"
    assert body["nessus_default_domain"] == "vulnerability_management"
    assert body["nessus_domain_map"]["Firewalls"] == "network_config"
    assert body["overridden"] == []
    assert body["nessus_domain_map_override"] == {}


def test_admin_overrides_and_clears_settings(client, admin):
    resp = _patch(client, admin, {"asset_existing_strategy": "skip", "import_partial_success": False})
    assert resp.status_code == 200
    assert resp.json()["asset_existing_strategy"] == "skip"
    assert resp.json()["overridden"] == ["asset_existing_strategy", "import_partial_success"]

    # Omitted fields stay; null clears back to the default.
    body = _patch(client, admin, {"asset_existing_strategy": None}).json()
    assert body["asset_existing_strategy"] == "update"
    assert body["import_partial_success"] is False
    assert body["overridden"] == ["import_partial_success"]
    assert _get(client, admin).json() == body


def test_domain_map_override_replaces_the_previous_one(client, admin):
    _patch(client, admin, {"nessus_domain_map": {"Web Servers": "network_config"}})
    body = _patch(client, admin, {"nessus_domain_map": {"Databases": "backup_recovery"}}).json()

    domain_map = body["nessus_domain_map"]
    assert domain_map["Databases"] == "backup_recovery"
    assert "Web Servers" not in domain_map  # earlier override replaced
    assert domain_map["Firewalls"] == "network_config"  # built-in map still underneath
    assert body["nessus_domain_map_override"] == {"Databases": "backup_recovery"}


def test_unoverridden_settings_follow_env_changes(client, admin, monkeypatch):
    _patch(client, admin, {"nessus_info_severity": "low"})
    monkeypatch.setattr(settings, "ASSET_EXISTING_STRATEGY", "duplicate")
    monkeypatch.setattr(settings, "NESSUS_INFO_SEVERITY", "skip")

    body = _get(client, admin).json()

    assert body["asset_existing_strategy"] == "duplicate"
    assert body["nessus_info_severity"] == "low"


@pytest.mark.parametrize(
    "body",
    [
        {"asset_existing_strategy": "merge"},
        {"nessus_info_severity": "medium"},
        {"nessus_default_domain": "physical_security"},
        {"nessus_domain_map": {"Firewalls": "not_a_domain"}},
        {"import_partial_success": "sometimes"},
    ],
)
def test_invalid_values_are_rejected(client, admin, body):
    assert _patch(client, admin, body).status_code == 422
    assert _get(client, admin).json()["overridden"] == []


def test_only_admins_can_change_settings(client, admin):
    admin_headers, org_id = admin
    auditor = member(client, admin_headers, org_id, "auditor")
    viewer = member(client, admin_headers, org_id, "viewer")
    outsider = register(client, "someone@globex.io", "Globex")

    for headers in (auditor, viewer):
        assert _get(client, admin, headers).status_code == 200
        assert _patch(client, admin, {"asset_existing_strategy": "skip"}, headers).status_code == 403
    assert _get(client, admin, outsider).status_code == 403
    assert _get(client, admin).json()["overridden"] == []


def test_overrides_are_per_org(client, admin):
    _patch(client, admin, {"asset_existing_strategy": "skip"})
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)

    body = client.get(f"/api/v1/orgs/{other_org}/settings", headers=other).json()

    assert body["asset_existing_strategy"] == "update"
    assert body["overridden"] == []
