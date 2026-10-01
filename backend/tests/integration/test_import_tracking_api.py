"""Import tracking: who started each import, the progress of background
imports, the tracker's list (?tracked=true) and dismissing a report."""

import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.models.enums import ScanStatus
from app.models.scan import Scan
from app.models.user import User
from app.services import ingestion_background, ingestion_service
from tests.conftest import requires_db
from tests.helpers import run_worker, first_org_id, member, register, upload

pytestmark = requires_db

ASSETS = b"type,hostname\nserver,web-01\nserver,web-02\nserver,web-03\nserver,web-04\nserver,web-05\n"


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _import(client, admin, headers=None):
    _, org_id = admin
    resp = upload(client, f"/api/v1/orgs/{org_id}/assets/import", headers or admin[0], "a.csv", ASSETS)
    assert resp.status_code in (201, 202), resp.text
    if resp.status_code == 202:
        run_worker()
    return resp.json()["scan_id"]


def _scans(client, admin, headers=None, **params):
    """The tracker's list (tracked/active), or with neither every upload
    (GET /uploads: the scans list needs a filter)."""
    _, org_id = admin
    if not params:
        return client.get(f"/api/v1/orgs/{org_id}/uploads", headers=headers or admin[0]).json()["items"]
    return client.get(f"/api/v1/orgs/{org_id}/scans", headers=headers or admin[0], params=params).json()


def _dismiss(client, admin, scan_id, headers=None):
    _, org_id = admin
    return client.post(f"/api/v1/orgs/{org_id}/scans/{scan_id}/dismiss", headers=headers or admin[0])


def _user_id(db_session, email):
    return db_session.query(User.id).filter(User.email == email).scalar()


def test_an_import_records_who_started_it(client, admin, db_session):
    scan_id = _import(client, admin)

    [scan] = _scans(client, admin)
    assert scan["id"] == scan_id
    assert scan["started_by"] == str(_user_id(db_session, "owner@acmecorp.io"))
    assert scan["dismissed_at"] is None


def _record_progress(monkeypatch) -> list[tuple[str, int, int]]:
    """Background imports' progress reports, as (phase, done, total); written
    through as usual."""
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    monkeypatch.setattr(ingestion_service, "WRITE_BATCH", 2)
    reports: list[tuple[str, int, int]] = []
    write_progress = ingestion_background.write_progress

    def record(scan_id, phase, done, total):
        reports.append((phase, done, total))
        write_progress(scan_id, phase, done, total)

    monkeypatch.setattr(ingestion_background, "write_progress", record)
    return reports


def test_a_background_import_reports_each_stage(client, admin, monkeypatch):
    reports = _record_progress(monkeypatch)

    scan_id = _import(client, admin)

    assert reports == [
        # The reading total is an estimate from how far into the file it is;
        # a file this small is read in one go, so it's the rows so far.
        ("reading", 2, 2),
        ("reading", 4, 4),
        ("reading", 5, 5),
        ("writing", 2, 5),
        ("writing", 4, 5),
        ("writing", 5, 5),
        ("saving", 0, 0),
    ]
    [scan] = _scans(client, admin)
    assert scan["id"] == scan_id
    assert scan["status"] == "completed"
    assert scan["progress"] is None  # cleared once it's finished


def test_a_tool_exports_rows_are_counted_once_with_their_findings(client, admin, monkeypatch):
    reports = _record_progress(monkeypatch)
    headers, org_id = admin
    # Three rows: three assets, and a finding for each disabled account.
    content = b"AssetID,Hostname,Type,OS,Status\nAD-1,h1,Server,Ubuntu,Disabled\nAD-2,h2,Server,Ubuntu,Disabled\nAD-3,h3,Server,Ubuntu,Active\n"

    resp = client.post(
        f"/api/v1/orgs/{org_id}/imports", headers=headers, files={"file": ("ad.csv", content)}, data={"profile": "directory"}
    )

    assert resp.status_code == 202, resp.text
    run_worker()
    assert reports == [
        ("reading", 2, 2),  # the total is estimated from how far into the file it is
        ("reading", 3, 3),
        ("writing", 2, 3),  # each row with its asset and findings
        ("writing", 3, 3),
        ("saving", 0, 0),
    ]


def test_the_tracker_lists_running_imports_and_my_undismissed_reports(client, admin, db_session):
    headers, org_id = admin
    auditor = member(client, headers, org_id, "auditor")
    mine = _import(client, admin)
    theirs = _import(client, admin, headers=auditor)
    dismissed = _import(client, admin)
    assert _dismiss(client, admin, dismissed).status_code == 200
    running = Scan(
        org_id=uuid.UUID(org_id),
        scan_type="asset_import",
        source="upload",
        status=ScanStatus.running,
        started_at=datetime.now(timezone.utc),
        started_by=_user_id(db_session, f"auditor-{org_id[:8]}@example.io"),
    )
    db_session.add(running)
    db_session.commit()

    tracked = {s["id"] for s in _scans(client, admin, tracked="true")}

    # Someone else's running import shows; their finished one doesn't.
    assert tracked == {mine, str(running.id)}
    assert theirs not in tracked
    assert {s["id"] for s in _scans(client, admin, headers=auditor, tracked="true")} == {theirs, str(running.id)}
    assert len(_scans(client, admin)) == 4  # untracked: every upload


def test_only_the_uploader_can_dismiss_a_finished_report(client, admin, db_session):
    headers, org_id = admin
    auditor = member(client, headers, org_id, "auditor")
    scan_id = _import(client, admin)

    assert _dismiss(client, admin, scan_id, headers=auditor).status_code == 403
    first = _dismiss(client, admin, scan_id)
    assert first.status_code == 200
    assert first.json()["dismissed_at"] is not None
    # Dismissing again changes nothing.
    assert _dismiss(client, admin, scan_id).json()["dismissed_at"] == first.json()["dismissed_at"]

    running = Scan(
        org_id=uuid.UUID(org_id),
        scan_type="asset_import",
        status=ScanStatus.running,
        started_at=datetime.now(timezone.utc),
        started_by=_user_id(db_session, "owner@acmecorp.io"),
    )
    db_session.add(running)
    db_session.commit()
    assert _dismiss(client, admin, running.id).status_code == 409
    assert _dismiss(client, admin, uuid.uuid4()).status_code == 404


def test_an_import_carries_on_when_its_progress_cant_be_saved(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    monkeypatch.setattr(ingestion_service, "WRITE_BATCH", 2)

    def unavailable():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(ingestion_background, "open_progress_session", unavailable)

    _import(client, admin)

    [scan] = _scans(client, admin)
    assert scan["status"] == "completed"
    assert scan["summary"]["created"] == 5


def test_the_active_filter_lists_only_running_imports(client, admin, db_session):
    headers, org_id = admin
    _import(client, admin)
    running = Scan(org_id=uuid.UUID(org_id), scan_type="asset_import", status=ScanStatus.running, started_at=datetime.now(timezone.utc))
    db_session.add(running)
    db_session.commit()

    assert [s["id"] for s in _scans(client, admin, active="true")] == [str(running.id)]
