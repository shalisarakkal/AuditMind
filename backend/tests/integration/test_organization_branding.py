from datetime import datetime, timezone
import uuid

from app.models.organization import Organization
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member


@requires_db
def test_branding_defaults_permissions_conflicts_and_lifecycle(client, db_session):
    admin = register(client, "branding-admin@example.io")
    org_id = first_org_id(client, admin)
    viewer = member(client, admin, org_id, "viewer")
    outsider = register(client, "branding-outsider@example.io")
    path = f"/api/v1/orgs/{org_id}/branding"
    payload = {"show_name_in_header": False, "expected_show_name_in_header": True}
    assert client.get(path).status_code == 401
    assert client.get(path, headers=outsider).status_code == 403
    initial = client.get(path, headers=viewer)
    assert initial.json() == {"show_name_in_header": True, "header_logo_size": "medium", "header_name_size": "medium"}
    assert initial.headers["cache-control"] == "no-store"
    for denied in (viewer, outsider):
        assert client.patch(path, headers=denied, json=payload).status_code == 403
    assert client.patch(path, headers=admin, json={**payload, "show_name_in_header": "false"}).status_code == 422
    assert client.patch(path, headers=admin, json=payload).json() == {"show_name_in_header": False, "header_logo_size": "medium", "header_name_size": "medium"}
    assert client.patch(path, headers=admin, json=payload).status_code == 409
    assert client.get(path, headers=viewer).json() == {"show_name_in_header": False, "header_logo_size": "medium", "header_name_size": "medium"}
    # A different tenant keeps the default, even without an uploaded logo.
    other = first_org_id(client, outsider)
    assert client.get(f"/api/v1/orgs/{other}/branding", headers=outsider).json() == {"show_name_in_header": True, "header_logo_size": "medium", "header_name_size": "medium"}
    assert client.patch(path, headers=admin, json={"show_name_in_header": True, "expected_show_name_in_header": False}).status_code == 200
    org = db_session.get(Organization, uuid.UUID(org_id))
    org.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.patch(path, headers=admin, json=payload).status_code == 409


@requires_db
def test_logo_size_validation_persistence_and_stale_edits(client):
    admin = register(client, "logo-size-admin@example.io")
    org_id = first_org_id(client, admin)
    viewer = member(client, admin, org_id, "viewer")
    path = f"/api/v1/orgs/{org_id}/branding"
    payload = {"show_name_in_header": True, "expected_show_name_in_header": True,
               "header_logo_size": "large", "expected_header_logo_size": "medium"}
    assert client.patch(path, headers=viewer, json=payload).status_code == 403
    assert client.patch(path, headers=admin, json={**payload, "header_logo_size": "huge"}).status_code == 422
    assert client.patch(path, headers=admin, json={**payload, "expected_header_logo_size": None}).status_code == 422
    assert client.patch(path, headers=admin, json=payload).json()["header_logo_size"] == "large"
    assert client.patch(path, headers=admin, json=payload).status_code == 409
    assert client.get(path, headers=viewer).json()["header_logo_size"] == "large"
    assert client.patch(path, headers=admin, json={**payload, "header_logo_size": "small", "expected_header_logo_size": "large"}).status_code == 200
    assert client.get(path, headers=admin).json()["header_logo_size"] == "small"


@requires_db
def test_header_name_size_permissions_validation_and_conflicts(client):
    admin = register(client, "name-size-admin@example.io")
    org_id = first_org_id(client, admin)
    viewer = member(client, admin, org_id, "viewer")
    path = f"/api/v1/orgs/{org_id}/branding"
    payload = {"show_name_in_header": True, "expected_show_name_in_header": True,
               "header_name_size": "large", "expected_header_name_size": "medium"}
    assert client.patch(path, headers=viewer, json=payload).status_code == 403
    assert client.patch(path, headers=admin, json={**payload, "header_name_size": "huge"}).status_code == 422
    assert client.patch(path, headers=admin, json={**payload, "expected_header_name_size": None}).status_code == 422
    assert client.patch(path, headers=admin, json=payload).json()["header_name_size"] == "large"
    assert client.patch(path, headers=admin, json=payload).status_code == 409
    assert client.get(path, headers=viewer).json()["header_name_size"] == "large"
    # A size conflict must not partially apply another field in the same request.
    assert client.patch(path, headers=admin, json={**payload, "show_name_in_header": False}).status_code == 409
    assert client.get(path, headers=admin).json()["show_name_in_header"] is True
    assert client.patch(path, headers=admin, json={**payload, "header_name_size": "small", "expected_header_name_size": "large"}).status_code == 200
