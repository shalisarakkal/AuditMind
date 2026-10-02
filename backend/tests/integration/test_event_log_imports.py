"""Uploading event logs (Phase 2f part 2): a few findings that sum many
events up, on no asset; the same log again is a duplicate."""

import json

import pytest

from app.models.asset import Asset
from app.models.finding import Finding
from tests.conftest import requires_db
from tests.helpers import first_org_id, register, upload

pytestmark = requires_db

LOG = json.dumps(
    [
        {"time": f"2026-06-{day:02} 10:00:00", "operation_name": "Microsoft.Authorization/roleAssignments/write",
         "status": status, "caller": f"user{day}@acme.io", "subscription_id": "sub-1", "resource_group": "rg"}
        for day, status in ((1, "Succeeded"), (2, "Succeeded"), (3, "Failed"), (4, "Succeeded"))
    ]
).encode()


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _upload(client, admin, content=LOG, name="activity.json"):
    headers, org_id = admin
    resp = client.post(
        f"/api/v1/orgs/{org_id}/imports",
        headers=headers,
        files={"file": (name, content)},
        data={"profile": "azure_activity", "confirm": "true"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["report"]


def test_an_event_log_becomes_a_few_findings_on_no_asset(client, admin, db_session):
    report = _upload(client, admin)
    assert (report["created"], report["failed"], report["findings_created"]) == (2, 0, 0)
    assert db_session.query(Asset).count() == 0

    headers, org_id = admin
    items = client.get(f"/api/v1/orgs/{org_id}/findings", headers=headers).json()["items"]
    created = next(f for f in items if f["category"].startswith("Role assignment created"))
    assert created["category"] == "Role assignment created in sub-1 (2026-06-01 to 2026-06-04)"
    assert (created["event_count"], created["asset_id"], created["asset_hostname"]) == (3, None, None)
    assert created["first_seen"].startswith("2026-06-01") and created["last_seen"].startswith("2026-06-04")
    assert created["details"]["scopes"] == {"name": "subscriptions", "distinct": "1", "top": [{"value": "sub-1", "events": 3}]}
    assert len(created["details"]["examples"]) == 3
    assert created["source"] == "azure_activity"


def test_the_same_log_again_is_a_duplicate_and_a_later_period_is_new(client, admin):
    _upload(client, admin)
    again = _upload(client, admin)
    assert (again["created"], again["duplicates"]) == (0, 2)

    later = LOG.replace(b"2026-06-0", b"2026-07-0")
    assert _upload(client, admin, later, "july.json")["created"] == 2


def test_event_log_sources_are_listed_with_their_rules(client, admin):
    headers, org_id = admin
    profiles = client.get(f"/api/v1/orgs/{org_id}/import-profiles", headers=headers).json()
    azure = next(p for p in profiles if p["key"] == "azure_activity")
    assert (azure["events"], azure["creates_assets"]) == (True, False)
    assert [r["key"] for r in azure["rules"]] == ["role_assignment_created", "role_assignment_failed", "failed_operations"]
    endpoint = next(p for p in profiles if p["key"] == "endpoint_agent")
    assert (endpoint["events"], endpoint["rules"]) == (False, [])


def test_an_orgs_copy_can_turn_a_rule_off(client, admin, db_session):
    headers, org_id = admin
    resp = client.post(
        f"/api/v1/orgs/{org_id}/import-profiles",
        headers=headers,
        json={"name": "Our Azure", "copy_from": "azure_activity",
              "params": {"rules": {"role_assignment_failed": {"enabled": False}}}},
    )
    assert resp.status_code == 201, resp.text
    report = client.post(
        f"/api/v1/orgs/{org_id}/imports", headers=headers, files={"file": ("a.json", LOG)}, data={"profile": resp.json()["key"]}
    ).json()["report"]
    assert report["created"] == 1
    bad = client.post(
        f"/api/v1/orgs/{org_id}/import-profiles",
        headers=headers,
        json={"name": "Bad", "copy_from": "azure_activity", "params": {"rules": {"nope": {}}}},
    )
    assert bad.status_code == 422 and "not a rule" in bad.text
