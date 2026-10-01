"""Who can write what: admins everything, auditors everything but connector
and org administration, viewers nothing (UI_FLOWS.md section 4)."""

import pytest

from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register

pytestmark = requires_db

ASSET = {"type": "server", "hostname": "web-01"}
FINDING = {"hostname": "web-01", "domain": "network_config", "severity": "low"}
CSV_FILE = {"file": ("a.csv", b"type,hostname\nserver,web\n")}

# (method, path under /orgs/{org_id}, request kwargs, roles allowed)
WRITE_ROUTES = [
    ("post", "/assets", {"json": ASSET}, {"admin", "auditor"}),
    ("post", "/assets/import", {"files": CSV_FILE}, {"admin", "auditor"}),
    ("post", "/assets/discover", {}, {"admin"}),
    ("post", "/findings", {"json": {"domain": "network_config", "severity": "low"}}, {"admin", "auditor"}),
    ("post", "/findings/import", {"files": {"file": ("f.json", b'[{"hostname":"a","domain":"network_config","severity":"low"}]')}}, {"admin", "auditor"}),
    ("post", "/scans", {"json": {"scan_type": "manual"}}, {"admin", "auditor"}),
    ("post", "/risk/score", {}, {"admin", "auditor"}),
    ("post", "/reports/generate", {"json": {"title": "Q3"}}, {"admin", "auditor"}),
    ("patch", "/settings", {"json": {"asset_existing_strategy": "skip"}}, {"admin"}),
    ("post", "/imports", {"files": {"file": ("e.csv", b"DeviceName\nDEV-1\n")}, "data": {"profile": "endpoint_agent"}}, {"admin", "auditor"}),
    ("post", "/import-profiles", {"json": {"name": "Our EDR", "copy_from": "endpoint_agent"}}, {"admin"}),
    ("post", "/members", {"json": {"email": "nobody@example.io"}}, {"admin"}),
]

READ_ROUTES = ["", "/users", "/assets", "/findings", "/scans?tracked=true", "/uploads", "/reports", "/dashboard", "/settings", "/import-profiles"]


@pytest.fixture
def org(client):
    admin = register(client, "owner@acmecorp.io")
    org_id = first_org_id(client, admin)
    return org_id, {
        "admin": admin,
        "auditor": member(client, admin, org_id, "auditor"),
        "viewer": member(client, admin, org_id, "viewer"),
    }


@pytest.mark.parametrize("role", ["admin", "auditor", "viewer"])
@pytest.mark.parametrize("method, path, kwargs, allowed", WRITE_ROUTES, ids=[f"{m} {p}" for m, p, _, _ in WRITE_ROUTES])
def test_write_access_by_role(client, org, role, method, path, kwargs, allowed):
    org_id, headers = org

    resp = getattr(client, method)(f"/api/v1/orgs/{org_id}{path}", headers=headers[role], **kwargs)

    if role in allowed:
        # members/nobody@example.io -> 404 (no such user) still proves access.
        # Discovery and report generation aren't available yet: 501.
        assert resp.status_code in (200, 201, 202, 404, 501), resp.text
    else:
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Insufficient permissions"


@pytest.mark.parametrize("path", READ_ROUTES)
def test_viewers_can_read_everything(client, org, path):
    org_id, headers = org
    assert client.get(f"/api/v1/orgs/{org_id}{path}", headers=headers["viewer"]).status_code == 200


def test_viewer_write_attempt_changes_nothing(client, org):
    org_id, headers = org

    client.post(f"/api/v1/orgs/{org_id}/assets/import", headers=headers["viewer"], files=CSV_FILE)

    assert client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers["admin"]).json() == {"items": [], "total": 0}
    assert client.get(f"/api/v1/orgs/{org_id}/uploads", headers=headers["admin"]).json()["total"] == 0
