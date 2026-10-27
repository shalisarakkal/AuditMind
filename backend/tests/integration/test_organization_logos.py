import base64
from io import BytesIO
from datetime import datetime, timezone

from PIL import Image, PngImagePlugin
import pytest
from sqlalchemy import delete, select

from app.models.organization import Organization
from app.models.organization_logo import OrganizationLogo
from app.models.event import Event
from app.services.organization_logos import normalize_logo, MAX_UPLOAD
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member


def image_bytes(kind="PNG", size=(16, 12), **options):
    image = Image.new("RGB", size, "red")
    output = BytesIO()
    image.save(output, format=kind, **options)
    return output.getvalue()


@pytest.mark.parametrize("kind,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_normalizes_supported_formats_and_removes_metadata(kind, mime):
    options = {}
    if kind == "PNG":
        info = PngImagePlugin.PngInfo(); info.add_text("private", "remove me")
        options["pnginfo"] = info
    normalized = normalize_logo(image_bytes(kind, (900, 600), **options), mime)
    with Image.open(BytesIO(normalized)) as image:
        assert image.format == "PNG" and image.size == (512, 341)
        assert not image.info


@pytest.mark.parametrize("content,mime,status", [
    (b"<svg><script>alert(1)</script></svg>", "image/svg+xml", 422),
    (b"not an image", "image/png", 422),
    (image_bytes("JPEG"), "image/png", 422),
    (image_bytes(size=(2049, 1)), "image/png", 422),
    (b"a" * (MAX_UPLOAD + 1), "image/png", 413),
], ids=["svg", "invalid", "mismatched-mime", "dimensions", "size"])
def test_rejects_invalid_or_oversize_images(content, mime, status):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        normalize_logo(content, mime)
    assert error.value.status_code == status


def test_rejects_animated_png():
    output = BytesIO()
    Image.new("RGB", (8, 8), "red").save(output, format="PNG", save_all=True,
        append_images=[Image.new("RGB", (8, 8), "blue")], duration=100, loop=0)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        normalize_logo(output.getvalue(), "image/png")


@requires_db
def test_logo_permissions_versions_atomicity_and_cleanup(client, db_session):
    admin = register(client, "logo-admin@example.io")
    org = first_org_id(client, admin)
    viewer = member(client, admin, org, "viewer")
    auditor = member(client, admin, org, "auditor")
    outsider = register(client, "logo-outsider@example.io")
    path = f"/api/v1/orgs/{org}/logo"
    def save(headers, version="none", content=None):
        return client.post(path, headers=headers, data={"expected_version": version},
            files={"file": ("untrusted-name.png", image_bytes() if content is None else content, "image/png")})
    assert client.get(path).status_code == 401
    assert client.get(path, headers=outsider).status_code == 403
    assert client.get(path, headers=viewer).json() == {"version": None, "image_data_url": None}
    for reader in (viewer, auditor, outsider):
        assert save(reader).status_code == 403
        assert client.delete(path + "?expected_version=none", headers=reader).status_code == 403
    first = save(admin)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    version = first.json()["version"]
    read = client.get(path, headers=viewer)
    assert read.headers["cache-control"] == "no-store"
    data = base64.b64decode(read.json()["image_data_url"].split(",", 1)[1])
    assert Image.open(BytesIO(data)).format == "PNG"
    assert save(admin).status_code == 409
    assert client.delete(path + "?expected_version=none", headers=admin).status_code == 409
    assert save(admin, version, b"invalid").status_code == 422
    assert client.get(path, headers=admin).json()["version"] == version
    replacement = save(admin, version)
    second = replacement.json()["version"]
    assert second != version
    assert client.delete(path + f"?expected_version={version}", headers=admin).status_code == 409
    assert client.delete(path + f"?expected_version={second}", headers=admin).status_code == 204
    assert save(admin, second).status_code == 409
    assert client.get(path, headers=admin).json()["image_data_url"] is None
    assert save(admin).status_code == 200
    events = db_session.scalars(select(Event).where(Event.org_id == org, Event.item == "Organization logo")).all()
    assert len(events) == 4  # only committed mutations, never rejected writes
    assert all("image" not in (event.details or {}) for event in events)
    db_session.execute(delete(Organization).where(Organization.id == org)); db_session.commit()
    assert db_session.get(OrganizationLogo, org) is None


@requires_db
def test_archived_org_logo_is_read_only(client, db_session):
    admin = register(client, "logo-archived@example.io")
    org = first_org_id(client, admin)
    organization = db_session.get(Organization, org)
    organization.archived_at = datetime.now(timezone.utc); db_session.commit()
    path = f"/api/v1/orgs/{org}/logo"
    assert client.get(path, headers=admin).status_code == 200
    assert client.post(path, headers=admin, data={"expected_version": "none"},
        files={"file": ("a.png", image_bytes(), "image/png")}).status_code == 409
    assert client.delete(path + "?expected_version=none", headers=admin).status_code == 409


@requires_db
def test_committed_save_response_survives_immediate_concurrent_removal(client, db_session, monkeypatch):
    admin = register(client, "logo-commit-race@example.io")
    org = first_org_id(client, admin)
    path = f"/api/v1/orgs/{org}/logo"
    commit = db_session.commit

    def commit_then_remove():
        commit()
        with db_session.get_bind().begin() as connection:
            connection.execute(delete(OrganizationLogo).where(OrganizationLogo.org_id == org))
        db_session.expire_all()

    monkeypatch.setattr(db_session, "commit", commit_then_remove)
    response = client.post(path, headers=admin, data={"expected_version": "none"},
        files={"file": ("logo.png", image_bytes(), "image/png")})
    assert response.status_code == 200, response.text
    assert response.json()["image_data_url"].startswith("data:image/png;base64,")
    assert client.get(path, headers=admin).json()["version"] is None
