import json

import pytest

from app.core.config import settings
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.scan import Scan
from app.services import ingestion_service
from tests.conftest import requires_db
from tests.helpers import run_worker, FIXTURES, first_org_id, register, upload

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _scan(client, admin, scan_id):
    headers, org_id = admin
    return client.get(f"/api/v1/orgs/{org_id}/scans/{scan_id}", headers=headers)


def test_file_over_sync_limit_is_imported_in_background(client, admin, monkeypatch, db_session):
    headers, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)

    resp = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "assets_valid.csv")

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending"
    assert resp.json()["report"] is None

    assert run_worker() == 1
    scan = _scan(client, admin, resp.json()["scan_id"]).json()
    assert scan["status"] == "completed"
    assert scan["filename"] == "assets_valid.csv"
    assert scan["summary"]["created"] == 4
    assert scan["completed_at"] is not None
    assert db_session.query(Asset).count() == 4


def test_real_file_just_over_ten_megabytes_goes_to_background(client, admin, db_session):
    """Uses the real default threshold, to check the byte arithmetic itself."""
    headers, org_id = admin
    record = {"hostname": "big-01", "domain": "network_config", "severity": "low", "padding": ""}
    base = len(json.dumps([record]).encode())
    record["padding"] = "x" * (settings.IMPORT_SYNC_MAX_BYTES + 1 - base)
    content = json.dumps([record]).encode()
    assert len(content) == settings.IMPORT_SYNC_MAX_BYTES + 1

    resp = upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "big.json", content)

    assert resp.status_code == 202
    run_worker()
    scan = _scan(client, admin, resp.json()["scan_id"]).json()
    assert (scan["status"], scan["summary"]["created"]) == ("completed", 1)


def test_file_exactly_at_sync_limit_is_imported_immediately(client, admin, monkeypatch):
    headers, org_id = admin
    content = (FIXTURES / "assets_valid.csv").read_bytes()
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", len(content))

    resp = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "assets.csv", content)

    assert resp.status_code == 201
    assert resp.json()["report"]["created"] == 4


def test_org_overrides_apply_to_background_imports(client, admin, monkeypatch, db_session):
    headers, org_id = admin
    client.patch(f"/api/v1/orgs/{org_id}/settings", headers=headers, json={"nessus_info_severity": "low"})
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)

    resp = upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "sample.nessus")
    run_worker()

    scan = _scan(client, admin, resp.json()["scan_id"]).json()
    assert (scan["status"], scan["summary"]["created"], scan["summary"]["skipped"]) == ("completed", 8, 0)


def test_background_import_of_bad_file_fails_the_scan(client, admin, monkeypatch):
    headers, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 1)

    resp = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "bad.json", b"{not json at all")

    assert resp.status_code == 202
    run_worker()
    scan = _scan(client, admin, resp.json()["scan_id"]).json()
    assert scan["status"] == "failed"
    assert scan["summary"]["errors"][0]["row"] == 0
    assert scan["summary"]["errors"][0]["message"].startswith("Invalid JSON")


def test_unexpected_error_in_background_marks_scan_failed(client, admin, monkeypatch, db_session):
    headers, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)

    def boom(*args, **kwargs):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(ingestion_service._Publisher, "publish", boom)

    resp = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "assets_valid.csv")

    assert resp.status_code == 202
    run_worker()
    scan = _scan(client, admin, resp.json()["scan_id"]).json()
    assert scan["status"] == "failed"
    assert scan["summary"] == {"error": "Unexpected error during import"}
    assert db_session.query(Asset).count() == 0


def test_unexpected_error_during_request_marks_scan_failed_and_raises(client, admin, monkeypatch, db_session):
    headers, org_id = admin

    def boom(*args, **kwargs):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(ingestion_service._Publisher, "publish", boom)

    with pytest.raises(RuntimeError):
        upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "findings_generic.csv")

    [scan] = db_session.query(Scan).all()
    assert scan.status.value == "failed"
    assert db_session.query(Finding).count() == 0


def test_file_over_hard_cap_is_rejected_without_a_scan(client, admin, monkeypatch, db_session):
    headers, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", 100)

    resp = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "big.csv", b"type,hostname\n" + b"server,a\n" * 20)

    assert resp.status_code == 413
    assert "upload limit" in resp.json()["detail"]
    assert db_session.query(Scan).count() == 0


def test_scan_polling_is_scoped_to_members_of_the_scans_org(client, admin):
    headers, org_id = admin
    scan_id = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "assets_valid.csv").json()["scan_id"]
    other = register(client, "other@globex.io", "Globex")
    other_org = first_org_id(client, other)

    assert client.get(f"/api/v1/orgs/{org_id}/scans/{scan_id}", headers=other).status_code == 403
    # Asking through your own org for another org's scan: not found.
    assert client.get(f"/api/v1/orgs/{other_org}/scans/{scan_id}", headers=other).status_code == 404
    assert _scan(client, admin, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_scans_list_includes_import_details_newest_first(client, admin):
    headers, org_id = admin
    upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers, "assets_valid.csv")
    upload(client, f"/api/v1/orgs/{org_id}/findings/import", headers, "sample.nessus")

    scans = client.get(f"/api/v1/orgs/{org_id}/uploads", headers=headers).json()["items"]

    assert [(s["scan_type"], s["filename"]) for s in scans] == [
        ("nessus", "sample.nessus"),
        ("asset_import", "assets_valid.csv"),
    ]
    assert scans[0]["summary"]["created"] == 6


def _multipart_stream(total_bytes: int):
    """A streamed (chunked, no Content-Length) multipart upload."""
    yield b'--B\r\nContent-Disposition: form-data; name="file"; filename="big.csv"\r\nContent-Type: text/csv\r\n\r\n'
    sent = 0
    while sent < total_bytes:
        yield b"x" * 65536
        sent += 65536
    yield b"\r\n--B--\r\n"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-token"}])
def test_oversized_upload_is_rejected_before_authentication(client, admin, monkeypatch, db_session, headers):
    """The body is refused while it arrives, before auth runs, so nobody can
    make the server store a huge upload just to be told 401/403."""
    _, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", 100)
    content = b"type,hostname\n" + b"server,a\n" * 250_000  # ~2.3 MB, over limit + multipart allowance

    resp = client.post(f"/api/v1/orgs/{org_id}/assets/import", headers=headers, files={"file": ("big.csv", content)})

    assert resp.status_code == 413
    assert db_session.query(Scan).count() == 0


def test_streamed_upload_without_length_is_cut_off(client, admin, monkeypatch, db_session):
    _, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", 100)

    resp = client.post(
        f"/api/v1/orgs/{org_id}/findings/import",
        content=_multipart_stream(3 * 1024 * 1024),
        headers={"Content-Type": "multipart/form-data; boundary=B"},
    )

    assert resp.status_code == 413
    assert "upload limit" in resp.json()["detail"]
    assert db_session.query(Scan).count() == 0


def test_size_guard_leaves_other_endpoints_alone(client, admin, monkeypatch):
    headers, org_id = admin
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", 100)
    big_description = "x" * (2 * 1024 * 1024)

    resp = client.post(
        f"/api/v1/orgs/{org_id}/findings",
        headers=headers,
        json={"domain": "network_config", "severity": "low", "description": big_description},
    )

    assert resp.status_code == 201
