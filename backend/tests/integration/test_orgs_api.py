import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from tests.conftest import requires_db


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register(client: TestClient, email: str, org_name: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={"org_name": org_name, "email": email, "password": "Sup3rSecret!"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@requires_db
def test_registration_org_is_listed_with_admin_role(client):
    headers = _register(client, "owner@acmecorp.io", "Acme Corp")

    resp = client.get("/api/v1/orgs", headers=headers)
    assert resp.status_code == 200
    orgs = resp.json()
    assert [(o["name"], o["role"]) for o in orgs] == [("Acme Corp", "admin")]


@requires_db
def test_created_org_appears_in_picker_and_is_accessible(client):
    headers = _register(client, "owner@acmecorp.io", "Acme Corp")

    created = client.post("/api/v1/orgs", json={"name": "Acme Labs", "industry": "R&D"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "admin"

    orgs = client.get("/api/v1/orgs", headers=headers).json()
    assert [o["name"] for o in orgs] == ["Acme Corp", "Acme Labs"]
    for org in orgs:
        assert client.get(f"/api/v1/orgs/{org['id']}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/orgs/{org['id']}/assets", headers=headers).status_code == 200


@requires_db
def test_non_member_is_denied(client):
    owner = _register(client, "owner@acmecorp.io", "Acme Corp")
    outsider = _register(client, "someone@globex.io", "Globex")
    acme_id = client.get("/api/v1/orgs", headers=owner).json()[0]["id"]

    assert client.get(f"/api/v1/orgs/{acme_id}", headers=outsider).status_code == 403
    assert client.get(f"/api/v1/orgs/{acme_id}/findings", headers=outsider).status_code == 403


@requires_db
def test_admin_adds_member_who_can_then_select_the_org(client):
    owner = _register(client, "owner@acmecorp.io", "Acme Corp")
    auditor = _register(client, "auditor@globex.io", "Globex")
    acme_id = client.get("/api/v1/orgs", headers=owner).json()[0]["id"]

    added = client.post(
        f"/api/v1/orgs/{acme_id}/members",
        json={"email": "auditor@globex.io", "role": "auditor"},
        headers=owner,
    )
    assert added.status_code == 201, added.text
    assert added.json()["role"] == "auditor"

    auditor_orgs = client.get("/api/v1/orgs", headers=auditor).json()
    assert {(o["name"], o["role"]) for o in auditor_orgs} == {("Globex", "admin"), ("Acme Corp", "auditor")}
    assert client.get(f"/api/v1/orgs/{acme_id}/assets", headers=auditor).status_code == 200

    members = client.get(f"/api/v1/orgs/{acme_id}/users", headers=owner).json()
    assert {(m["email"], m["role"]) for m in members} == {
        ("owner@acmecorp.io", "admin"),
        ("auditor@globex.io", "auditor"),
    }


@requires_db
def test_add_member_rules(client):
    owner = _register(client, "owner@acmecorp.io", "Acme Corp")
    viewer = _register(client, "viewer@globex.io", "Globex")
    acme_id = client.get("/api/v1/orgs", headers=owner).json()[0]["id"]
    url = f"/api/v1/orgs/{acme_id}/members"

    assert client.post(url, json={"email": "nobody@nowhere.io"}, headers=owner).status_code == 404

    first = client.post(url, json={"email": "viewer@globex.io"}, headers=owner)
    assert first.status_code == 201
    assert first.json()["role"] == "viewer"
    assert client.post(url, json={"email": "viewer@globex.io"}, headers=owner).status_code == 409

    # A viewer in Acme can't add members, even though they're admin of their own org.
    assert client.post(url, json={"email": "owner@acmecorp.io"}, headers=viewer).status_code == 403
