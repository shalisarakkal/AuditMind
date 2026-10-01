"""Phase 2d Part 4: fixes from the CoPilot review (placeholder endpoints answer
501, the scans list needs a filter, a weak signing key is refused, the Claude
smoke test is bounded) and Retry for a failed large upload."""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import anthropic
import httpx
import pytest
from sqlalchemy import text

from app.api.routes import ai
from app.api.uploads import upload_path
from app.core.config import DEFAULT_SECRET_KEY, check_secret_key, settings
from app.models.enums import ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.report import Report
from app.models.scan import Scan
from app.services.org_lock import _key
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register, run_worker, upload

pytestmark = requires_db

ASSETS = b"type,hostname\nserver,web-01\nserver,web-02\n"


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _url(admin, path):
    return f"/api/v1/orgs/{admin[1]}{path}"


# --- Placeholders and the scans list -------------------------------------------


def test_discovery_and_report_generation_say_not_available(client, admin, db_session):
    resp = client.post(_url(admin, "/assets/discover"), headers=admin[0])
    assert resp.status_code == 501 and "isn't available" in resp.json()["detail"]
    resp = client.post(_url(admin, "/reports/generate"), headers=admin[0], json={"title": "Q3"})
    assert resp.status_code == 501
    assert db_session.query(Report).count() == 0  # no report left pending for ever


def test_the_scans_list_needs_a_filter(client, admin):
    resp = client.get(_url(admin, "/scans"), headers=admin[0])
    assert resp.status_code == 400 and "/uploads" in resp.json()["detail"]
    assert client.get(_url(admin, "/scans"), headers=admin[0], params={"active": True}).json() == []


# --- The signing key -------------------------------------------------------------


@pytest.mark.parametrize("key", [DEFAULT_SECRET_KEY, "", "short-but-not-empty", "x" * 31])
def test_a_weak_signing_key_is_refused(key):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        check_secret_key(key)


def test_a_long_random_signing_key_is_accepted():
    check_secret_key("k" * 32)


# --- The Claude smoke test -------------------------------------------------------

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, code):
    return cls("failed", response=httpx.Response(code, request=_REQUEST), body=None)


def test_the_claude_smoke_test_is_for_admins(client, admin, monkeypatch, db_session):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(ai, "ask_claude", lambda prompt, system=None: "Hello")
    auditor = member(client, admin[0], admin[1], "auditor")
    # Signing up makes them admin of an org of their own (until Phase 2e
    # turns sign-up off): made auditor there too, they're admin nowhere.
    for membership in db_session.query(OrgMembership).all():
        if membership.role == UserRole.admin and str(membership.org_id) != admin[1]:
            membership.role = UserRole.auditor
    db_session.commit()
    assert client.post("/api/v1/ai/claude/test", headers=auditor, json={"prompt": "Hi"}).status_code == 403
    resp = client.post("/api/v1/ai/claude/test", headers=admin[0], json={"prompt": "Hi"})
    assert resp.status_code == 200 and resp.json()["response"] == "Hello"


def test_the_claude_smoke_test_without_a_key(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    resp = client.post("/api/v1/ai/claude/test", headers=admin[0], json={"prompt": "Hi"})
    assert resp.status_code == 503 and "no API key" in resp.json()["detail"]


@pytest.mark.parametrize(
    "error, code",
    [
        (anthropic.APITimeoutError(request=_REQUEST), 504),
        (anthropic.APIConnectionError(request=_REQUEST), 503),
        (_status_error(anthropic.RateLimitError, 429), 503),
        (_status_error(anthropic.AuthenticationError, 401), 503),
        (_status_error(anthropic.InternalServerError, 500), 502),
    ],
)
def test_claude_problems_come_back_as_clear_errors(client, admin, monkeypatch, error, code):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")

    def fail(prompt, system=None):
        raise error

    monkeypatch.setattr(ai, "ask_claude", fail)
    resp = client.post("/api/v1/ai/claude/test", headers=admin[0], json={"prompt": "Hi"})
    assert resp.status_code == code, resp.text
    assert "Claude" in resp.json()["detail"]


# --- Retry a failed upload -------------------------------------------------------


def _large_upload(client, admin, monkeypatch, content=ASSETS, name="a.csv", headers=None):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    resp = upload(client, _url(admin, "/assets/import"), headers or admin[0], name, content)
    assert resp.status_code == 202, resp.text
    return uuid.UUID(resp.json()["scan_id"])


def _cut_off_twice(db_session, scan_id):
    """Cut off once more than it carries on after (runner.MAX_RESUMES)."""
    scan = db_session.get(Scan, scan_id)
    stale = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    scan.status, scan.heartbeat_at, scan.retry_count = ScanStatus.running, stale, runner.MAX_RESUMES
    db_session.commit()
    runner.reap_stale(db_session)
    assert scan.status == ScanStatus.failed
    return scan


def test_an_upload_cut_off_twice_can_be_retried(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    _cut_off_twice(db_session, scan_id)
    shown = client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).json()
    assert shown["retryable"] is True
    [listed] = client.get(_url(admin, "/uploads"), headers=admin[0]).json()["items"]
    assert listed["retryable"] is True

    resp = client.post(_url(admin, f"/scans/{scan_id}/retry"), headers=admin[0])
    assert resp.status_code == 202, resp.text
    new_id = uuid.UUID(resp.json()["scan_id"])
    assert resp.json()["status"] == "pending"
    assert upload_path(new_id).exists() and not upload_path(scan_id).exists()
    db_session.expire_all()
    old = db_session.get(Scan, scan_id)
    assert old.retryable is False and old.dismissed_at is not None  # its report gives way to the new one

    assert run_worker() == 1
    new = db_session.get(Scan, new_id)
    assert (new.status, new.summary["created"], new.filename) == (ScanStatus.completed, 2, "a.csv")
    assert not upload_path(new_id).exists()
    # Retrying the old one again: nothing left to run.
    assert client.post(_url(admin, f"/scans/{scan_id}/retry"), headers=admin[0]).status_code == 409


def test_an_upload_rejected_for_its_content_cant_be_retried(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch, content=b"type,hostname\nnot-a-type,web-01\n")
    assert run_worker() == 1
    scan = db_session.get(Scan, scan_id)
    assert scan.status == ScanStatus.failed and "error" not in scan.summary
    assert not upload_path(scan_id).exists()  # it would fail the same way
    assert client.post(_url(admin, f"/scans/{scan_id}/retry"), headers=admin[0]).status_code == 409


def test_who_can_retry(client, admin, monkeypatch, db_session):
    auditor = member(client, admin[0], admin[1], "auditor")
    viewer = member(client, admin[0], admin[1], "viewer")
    scan_id = _large_upload(client, admin, monkeypatch, headers=auditor)
    _cut_off_twice(db_session, scan_id)
    other_auditor = register(client, "second@acmecorp.io", org_name="Second home org")
    assert client.post(
        _url(admin, "/members"), headers=admin[0], json={"email": "second@acmecorp.io", "role": "auditor"}
    ).status_code == 201

    assert client.post(_url(admin, f"/scans/{scan_id}/retry"), headers=viewer).status_code == 403
    assert client.post(_url(admin, f"/scans/{scan_id}/retry"), headers=other_auditor).status_code == 403
    assert client.post(_url(admin, f"/scans/{scan_id}/retry"), headers=admin[0]).status_code == 202  # an admin


def test_a_kept_file_is_deleted_after_the_keep_period(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    scan = _cut_off_twice(db_session, scan_id)
    day_ago = time.time() - 86400
    os.utime(upload_path(scan_id), (day_ago, day_ago))

    runner.housekeeping(db_session)
    assert upload_path(scan_id).exists()  # within UPLOAD_KEEP_FAILED_DAYS

    scan.completed_at = datetime.now(timezone.utc) - timedelta(days=settings.UPLOAD_KEEP_FAILED_DAYS + 1)
    db_session.commit()
    runner.housekeeping(db_session)
    assert not upload_path(scan_id).exists()
    assert client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).json()["retryable"] is False


def test_importing_the_same_file_ends_the_failed_copys_retry(client, admin, monkeypatch, db_session):
    """Uploaded again by hand and imported: the failed copy's kept file goes
    (Retry would only import it again). A different file doesn't touch it."""
    scan_id = _large_upload(client, admin, monkeypatch)
    _cut_off_twice(db_session, scan_id)

    other = _large_upload(client, admin, monkeypatch, content=b"type,hostname\nserver,db-01\n", name="a.csv")
    assert run_worker() == 1 and db_session.get(Scan, other).status == ScanStatus.completed
    assert upload_path(scan_id).exists()  # same name, different content: still retryable

    again = _large_upload(client, admin, monkeypatch)  # the same file
    assert run_worker() == 1 and db_session.get(Scan, again).status == ScanStatus.completed
    assert not upload_path(scan_id).exists()
    shown = client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).json()
    assert (shown["status"], shown["retryable"]) == ("failed", False)


# --- Archiving while the org is busy ---------------------------------------------


def test_a_small_archive_queues_while_an_upload_holds_the_org(client, admin, monkeypatch, db_session):
    """An upload writing its rows holds the org's lock for minutes: a small
    archive started meanwhile is queued for the worker (202) instead of
    holding the request until then."""
    resp = upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    scan_id = resp.json()["scan_id"]
    holder = db_session.get_bind().connect()
    holder.execute(text("select pg_advisory_lock(:k)"), {"k": _key(uuid.UUID(admin[1]))})
    try:
        resp = client.post(_url(admin, f"/scans/{scan_id}/archive"), headers=admin[0])
        assert resp.status_code == 202 and resp.json()["status"] == "pending"
    finally:
        holder.execute(text("select pg_advisory_unlock(:k)"), {"k": _key(uuid.UUID(admin[1]))})
        holder.close()
    assert run_worker() == 1
    assert client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).status_code == 404  # archived

    # The org free again: a small one runs during the request, as before.
    other = upload(client, _url(admin, "/assets/import"), admin[0], "b.csv", b"type,hostname\nserver,db-01\n")
    resp = client.post(_url(admin, f"/scans/{other.json()['scan_id']}/archive"), headers=admin[0])
    assert resp.status_code == 200 and resp.json()["status"] == "completed"


# --- An archived upload's report -------------------------------------------------


def test_an_archived_uploads_report_is_read_from_archived_only(client, admin, db_session):
    scan_id = upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS).json()["scan_id"]
    client.post(_url(admin, f"/scans/{scan_id}/archive"), headers=admin[0])
    [item] = client.get(_url(admin, "/archive"), headers=admin[0]).json()["items"]
    viewer = member(client, admin[0], admin[1], "viewer")

    report = client.get(_url(admin, f"/archive/{item['id']}/report"), headers=viewer)
    assert report.status_code == 200, report.text
    assert (report.json()["id"], report.json()["summary"]["created"]) == (scan_id, 2)
    assert client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).status_code == 404

    outsider = register(client, "someone@else.io", org_name="Else")
    assert client.get(_url(admin, f"/archive/{item['id']}/report"), headers=outsider).status_code == 403
    other_org = first_org_id(client, outsider)
    assert client.get(f"/api/v1/orgs/{other_org}/archive/{item['id']}/report", headers=outsider).status_code == 404

    # Restored: back on the normal route, and no longer served here.
    client.post(_url(admin, f"/archive/{item['id']}/restore"), headers=admin[0])
    assert client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).status_code == 200
    assert client.get(_url(admin, f"/archive/{item['id']}/report"), headers=admin[0]).status_code == 404


def test_only_uploads_have_an_archived_report(client, admin):
    client.post(_url(admin, "/assets"), headers=admin[0], json={"type": "server", "hostname": "web-09"})
    asset = client.get(_url(admin, "/assets"), headers=admin[0]).json()["items"][0]
    client.post(_url(admin, f"/assets/{asset['id']}/archive"), headers=admin[0])
    [item] = client.get(_url(admin, "/archive"), headers=admin[0]).json()["items"]
    assert client.get(_url(admin, f"/archive/{item['id']}/report"), headers=admin[0]).status_code == 404
