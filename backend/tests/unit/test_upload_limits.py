"""Browser ceilings reflect config without exposing credentials or DB data."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.mark.parametrize("limit", [16, 256 * 1024**2, 1024**3])
def test_public_upload_limits_reflect_config_and_are_not_cached(limit, monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", limit)
    with TestClient(app) as client:
        response = client.get("/api/v1/upload-limits")
    assert response.status_code == 200
    assert response.json() == {
        "import_max_bytes": limit,
        "document_max_bytes": 10 * 1024**2,
        "logo_max_bytes": 2 * 1024**2,
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
