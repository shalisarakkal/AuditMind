import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from tests.conftest import requires_db
from tests.helpers import PASSWORD, register


@requires_db
def test_register_then_login(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    try:
        register_resp = client.post(
            "/api/v1/auth/register",
            json={
                "org_name": "Acme Corp",
                "email": "admin@acmecorp.io",
                "password": "Sup3rSecret!",
                "name": "Admin User",
            },
        )
        assert register_resp.status_code == 201, register_resp.text
        assert "access_token" in register_resp.json()

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@acmecorp.io", "password": "Sup3rSecret!"},
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()
    finally:
        app.dependency_overrides.clear()


@requires_db
def test_login_with_wrong_password_is_rejected(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    try:
        client.post(
            "/api/v1/auth/register",
            json={"org_name": "Acme Corp", "email": "user@acmecorp.io", "password": "Sup3rSecret!"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "user@acmecorp.io", "password": "wrong-password"},
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


@requires_db
def test_duplicate_registration_is_rejected(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    try:
        payload = {"org_name": "Acme Corp", "email": "dup@acmecorp.io", "password": "Sup3rSecret!"}
        first = client.post("/api/v1/auth/register", json=payload)
        assert first.status_code == 201
        second = client.post("/api/v1/auth/register", json=payload)
        assert second.status_code == 400
    finally:
        app.dependency_overrides.clear()


@requires_db
def test_swagger_style_form_login(client):
    """Swagger's Authorize button posts an OAuth2 password form (username = email)."""
    register(client, "form@acmecorp.io")

    resp = client.post("/api/v1/auth/login", data={"username": "form@acmecorp.io", "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    assert client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    wrong = client.post("/api/v1/auth/login", data={"username": "form@acmecorp.io", "password": "nope"})
    assert wrong.status_code == 401


# The tests below are rejected before any DB access, so they run without Postgres.


@pytest.mark.parametrize(
    "kwargs, status, field",
    [
        ({"json": {"email": "a@acmecorp.io"}}, 422, "password"),
        ({"json": {"email": "not-an-email", "password": "x"}}, 422, "email"),
        ({"data": {"password": "x"}}, 422, "email"),
        ({"data": {"username": "not-an-email", "password": "x"}}, 422, "email"),
    ],
)
def test_login_validation_errors_name_the_field(kwargs, status, field):
    resp = TestClient(app).post("/api/v1/auth/login", **kwargs)
    assert resp.status_code == status
    assert [error["loc"][-1] for error in resp.json()["detail"]] == [field]


def test_login_with_malformed_json_body():
    resp = TestClient(app).post(
        "/api/v1/auth/login", content=b"{oops", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid JSON body"


def test_login_docs_describe_both_body_types():
    body = TestClient(app).get("/openapi.json").json()["paths"]["/api/v1/auth/login"]["post"]["requestBody"]
    assert set(body["content"]) == {"application/json", "application/x-www-form-urlencoded"}
