from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from tests.conftest import requires_db


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
