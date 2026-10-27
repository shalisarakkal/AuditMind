from sqlalchemy import select
from app.models.user import User
from app.models.event import Event
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member


@requires_db
def test_product_branding_permissions_versions_audit_and_organization_isolation(client, db_session):
    admin = register(client, "product-org-admin@example.io")
    viewer = member(client, admin, first_org_id(client, admin), "viewer")
    platform = register(client, "product-platform@example.io")
    user = db_session.scalar(select(User).where(User.email == "product-platform@example.io"))
    user.is_sysadmin = True
    db_session.commit()
    path = "/api/v1/platform/branding"
    assert client.get(path).status_code == 401
    assert client.patch(path, json={"sidebar_logo_size": "large", "expected_version": "none"}).status_code == 401
    for headers in (admin, viewer, platform):
        result = client.get(path, headers=headers)
        assert result.json() == {"sidebar_logo_size": "medium", "version": "none"}
        assert result.headers["cache-control"] == "no-store"
    payload = {"sidebar_logo_size": "large", "expected_version": "none"}
    for headers in (admin, viewer):
        assert client.patch(path, headers=headers, json=payload).status_code == 403
    assert client.patch(path, headers=platform, json={**payload, "sidebar_logo_size": "huge"}).status_code == 422
    saved = client.patch(path, headers=platform, json=payload)
    assert saved.status_code == 200
    assert saved.headers["cache-control"] == "no-store"
    version = saved.json()["version"]
    assert version != "none"
    assert client.get(path, headers=viewer).json()["sidebar_logo_size"] == "large"
    assert client.patch(path, headers=platform, json=payload).status_code == 409
    # A no-op neither rotates version nor records a misleading change.
    assert client.patch(path, headers=platform, json={**payload, "expected_version": version}).json()["version"] == version
    events = db_session.scalars(select(Event).where(Event.item == "Product branding")).all()
    assert len(events) == 1 and events[0].org_id is None
    assert client.patch(path, headers=platform, json={"sidebar_logo_size": "small", "expected_version": version}).status_code == 200
    # Organization-specific branding stays independent.
    org_path = f"/api/v1/orgs/{first_org_id(client, admin)}/branding"
    assert client.get(org_path, headers=admin).json()["header_logo_size"] == "medium"
