"""Shared helpers for integration tests (use with the `client` fixture)."""

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "Sup3rSecret!"


def register(client: TestClient, email: str, org_name: str = "Acme Corp") -> dict[str, str]:
    """Register a user (admin of a new org); returns auth headers."""
    resp = client.post(
        "/api/v1/auth/register", json={"org_name": org_name, "email": email, "password": PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def first_org_id(client: TestClient, headers: dict[str, str]) -> str:
    return client.get("/api/v1/orgs", headers=headers).json()[0]["id"]


def member(client: TestClient, admin_headers: dict[str, str], org_id: str, role: str) -> dict[str, str]:
    """A new user added to org_id with the given role; returns their headers."""
    headers = register(client, f"{role}-{org_id[:8]}@example.io", org_name=f"{role} home org")
    resp = client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": f"{role}-{org_id[:8]}@example.io", "role": role},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return headers


def upload(client: TestClient, url: str, headers: dict[str, str], filename: str, content: bytes | None = None):
    """POST a file; content defaults to the fixture with that name."""
    if content is None:
        content = (FIXTURES / filename).read_bytes()
    return client.post(url, headers=headers, files={"file": (filename, content)})
