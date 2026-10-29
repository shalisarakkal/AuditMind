"""Real-session authorization and durable import-integrity boundaries."""
import pytest

from app.services import platform
from tests.conftest import requires_db
from tests.helpers import register

pytestmark = requires_db


def test_metrics_require_current_platform_admin_and_never_cache(client, db_session):
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer invalid"}).status_code == 401
    ordinary = register(client, "metrics-org-admin@example.com")
    assert client.get("/metrics", headers=ordinary).status_code == 403
    temporary = platform.create_sysadmin(db_session, "metrics-root@example.com", "Synthetic root")
    db_session.commit()
    login = client.post("/api/v1/auth/login", json={"email": "metrics-root@example.com", "password": temporary})
    assert login.status_code == 200, login.text
    root = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/metrics", headers=root).status_code == 403  # forced password change
    changed = client.post("/api/v1/auth/change-password", headers=root,
        json={"current_password": temporary, "new_password": "Synthetic-strong-password-2026!"})
    assert changed.status_code == 204, changed.text
    response = client.get("/metrics", headers=root)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert isinstance(response.json()["requests_total"], int)
    assert client.post("/api/v1/auth/logout", headers=root).status_code == 204
    assert client.get("/metrics", headers=root).status_code == 401
