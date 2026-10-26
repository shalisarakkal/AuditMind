from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_status_and_redaction():
    from app.services.readiness import readiness_checks
    try:
        for healthy, status in ((True, 200), (False, 503)):
            app.dependency_overrides[readiness_checks] = lambda: {"database": healthy, "uploads": True, "worker": True}
            response = client.get("/ready")
            assert response.status_code == status
            assert response.headers["cache-control"] == "no-store"
            assert set(response.json()) == {"status", "checks"}
    finally:
        app.dependency_overrides.pop(readiness_checks, None)
