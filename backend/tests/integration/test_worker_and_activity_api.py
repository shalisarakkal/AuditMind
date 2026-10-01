"""The background worker (queue, saved uploads, cut-off jobs, housekeeping)
and Activity (which events are recorded, how they're listed, retention):
Phase 2d part 3."""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.uploads import upload_path
from app.core.config import settings
from app.models.enums import Criticality, ScanStatus
from app.models.event import Event, WorkerStatus
from app.models.scan import Scan
from app.services import events
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import FIXTURES, PASSWORD, first_org_id, member, register, run_worker, upload

pytestmark = requires_db

ASSETS = b"type,hostname\nserver,web-01\nserver,web-02\n"
BAD_ROWS = b"type,hostname\nserver,web-01\nnot-a-type,web-02\n"


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _url(admin, path):
    return f"/api/v1/orgs/{admin[1]}{path}"


def _events(client, admin, headers=None, **params):
    resp = client.get(_url(admin, "/events"), headers=headers or admin[0], params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _large_upload(client, admin, monkeypatch, content=ASSETS, name="a.csv"):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    resp = upload(client, _url(admin, "/assets/import"), admin[0], name, content)
    assert resp.status_code == 202, resp.text
    return uuid.UUID(resp.json()["scan_id"])


# --- The worker ---------------------------------------------------------------


def test_a_large_upload_waits_on_disk_until_the_worker_imports_it(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    assert upload_path(scan_id).read_bytes() == ASSETS
    assert db_session.get(Scan, scan_id).status == ScanStatus.pending

    assert run_worker() == 1
    scan = db_session.get(Scan, scan_id)
    assert (scan.status, scan.summary["created"]) == (ScanStatus.completed, 2)
    assert not upload_path(scan_id).exists()
    assert list(settings.upload_dir.iterdir()) == []  # nothing half-received left either


def test_a_small_upload_is_never_the_workers(client, admin, db_session):
    resp = upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    assert resp.status_code == 201
    assert run_worker() == 0
    assert not settings.upload_dir.exists() or list(settings.upload_dir.iterdir()) == []


def test_the_app_can_tell_a_job_the_worker_runs(client, admin, monkeypatch, db_session):
    """heartbeat_at is shown: set only by the worker, so the app can say a job
    was interrupted when the worker stops in the middle of it."""
    scan_id = _large_upload(client, admin, monkeypatch)
    scan = db_session.get(Scan, scan_id)
    scan.status, scan.heartbeat_at = ScanStatus.running, datetime.now(timezone.utc)
    db_session.commit()
    shown = client.get(_url(admin, f"/scans/{scan_id}"), headers=admin[0]).json()
    assert shown["heartbeat_at"] is not None
    tracked = client.get(_url(admin, "/scans"), headers=admin[0], params={"tracked": True}).json()
    assert tracked[0]["heartbeat_at"] is not None

    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10 * 1024 * 1024)
    small = upload(client, _url(admin, "/assets/import"), admin[0], "b.csv", BAD_ROWS)
    assert small.status_code == 201, small.text
    assert client.get(_url(admin, f"/scans/{small.json()['scan_id']}"), headers=admin[0]).json()["heartbeat_at"] is None


def test_the_oldest_waiting_job_goes_first(client, admin, monkeypatch, db_session):
    first = _large_upload(client, admin, monkeypatch, name="first.csv")
    second = _large_upload(client, admin, monkeypatch, content=ASSETS + b"server,web-03\n", name="second.csv")
    assert runner.claim_next(db_session) == ("import", first)
    assert runner.claim_next(db_session) == ("import", second)
    assert runner.claim_next(db_session) is None


def test_two_workers_never_take_the_same_job(client, admin, monkeypatch, db_session):
    _large_upload(client, admin, monkeypatch)
    other = sessionmaker(bind=db_session.get_bind())()
    try:
        # One holds its claim open; the other skips it rather than waiting.
        db_session.connection()
        claimed = runner.claim_next(db_session)
        assert claimed is not None
        assert runner.claim_next(other) is None
    finally:
        other.close()


def test_an_import_cut_off_is_started_again_once(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    scan = db_session.get(Scan, scan_id)
    stale = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    scan.status, scan.heartbeat_at = ScanStatus.running, stale  # its worker stopped
    db_session.commit()

    runner.reap_stale(db_session)
    assert (scan.status, scan.retry_count) == (ScanStatus.pending, 1)
    assert run_worker() == 1
    assert scan.status == ScanStatus.completed
    [event] = _events(client, admin, type="import")
    assert event["details"]["retried"].startswith("Cut off")


def test_an_import_cut_off_twice_is_failed(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    scan = db_session.get(Scan, scan_id)
    stale = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    scan.status, scan.heartbeat_at, scan.retry_count = ScanStatus.running, stale, 1
    db_session.commit()

    runner.reap_stale(db_session)
    assert scan.status == ScanStatus.failed
    assert scan.summary == {"error": "Cut off twice (the background worker stopped)"}
    assert upload_path(scan_id).exists()  # kept for Retry
    [event] = _events(client, admin, type="import")
    assert (event["outcome"], event["criticality"]) == ("failed", "warning")


def test_an_import_a_request_never_finished_is_failed(client, admin, db_session):
    scan = Scan(
        org_id=uuid.UUID(admin[1]), scan_type="asset_import", source="upload", status=ScanStatus.running,
        started_at=datetime.now(timezone.utc) - timedelta(hours=1), filename="small.csv",
    )
    db_session.add(scan)
    db_session.commit()
    runner.reap_stale(db_session)
    assert scan.status == ScanStatus.failed
    assert scan.summary == {"error": "Stopped when the server restarted: import it again"}


def test_an_upload_whose_file_is_gone_is_failed(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    upload_path(scan_id).unlink()
    assert run_worker() == 1
    assert db_session.get(Scan, scan_id).summary["error"].startswith("The uploaded file wasn't found")


def test_housekeeping_deletes_uploads_nothing_waits_for(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    leftover = settings.upload_dir / f"receiving-{uuid.uuid4()}.part"
    leftover.write_bytes(b"half a file")
    hour_ago = time.time() - 7200
    for path in (leftover, upload_path(scan_id)):
        os.utime(path, (hour_ago, hour_ago))

    runner.housekeeping(db_session)
    assert not leftover.exists()
    assert upload_path(scan_id).exists()  # still waiting for the worker


def test_worker_status(client, admin, db_session):
    status = client.get("/api/v1/worker-status", headers=admin[0]).json()
    assert status == {"running": False, "last_seen": None}
    db_session.add(WorkerStatus(id=1, started_at=datetime.now(timezone.utc), heartbeat_at=datetime.now(timezone.utc)))
    db_session.commit()
    assert client.get("/api/v1/worker-status", headers=admin[0]).json()["running"] is True


# --- Activity: what's recorded ------------------------------------------------


def test_imports_are_recorded_with_their_counts(client, admin):
    upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    upload(client, _url(admin, "/assets/import"), admin[0], "b.csv", BAD_ROWS)
    bad, good = _events(client, admin, type="import")
    assert (good["item"], good["criticality"], good["outcome"], good["counts"]) == (
        "a.csv", "info", "completed", {"assets_created": 2}
    )
    assert good["actor_label"] == "owner@acmecorp.io" and good["ended_at"] >= good["started_at"]
    # Rows that failed: a warning, though the file imported.
    # (web-01 was already there: updated.)
    assert (bad["criticality"], bad["counts"]) == ("warning", {"assets_updated": 1, "rows_failed": 1})


def test_import_counts_say_what_they_count(client, admin):
    """A tool export makes assets and findings; a findings file, findings."""
    network = (FIXTURES / "network_scan.csv").read_bytes()
    client.post(
        _url(admin, "/imports"), headers=admin[0], files={"file": ("scan.csv", network)},
        data={"profile": "network_scan", "confirm": "true"},
    )
    findings = b"hostname,domain,severity,category\nweb-01,network_config,low,SMB\nweb-01,network_config,low,SMB\n"
    upload(client, _url(admin, "/findings/import"), admin[0], "f.csv", findings)
    by_item = {e["item"]: e["counts"] for e in _events(client, admin, type="import")}
    assert set(by_item["scan.csv"]) >= {"assets_created", "findings_created"}
    assert by_item["f.csv"] == {"findings_created": 1, "duplicate_findings": 1}


def test_a_repeat_upload_imported_anyway_is_a_warning(client, admin):
    upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    upload(client, _url(admin, "/assets/import"), admin[0], "again.csv", ASSETS, confirm=True)
    [event] = _events(client, admin, type="repeat_upload")
    assert (event["item"], event["criticality"]) == ("again.csv", "warning")
    assert event["details"]["previously_by"] == "owner@acmecorp.io"


def test_sign_in_events(client, admin):
    login = client.post("/api/v1/auth/login", json={"email": "owner@acmecorp.io", "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": "owner@acmecorp.io", "password": "wrong"})
    client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.io", "password": "wrong"})
    assert client.post("/api/v1/auth/logout", headers=admin[0]).status_code == 204
    # Signing out ends that session only; the other sign-in goes on.
    assert client.get(_url(admin, "/events"), headers=admin[0]).status_code == 401
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    types = [(e["type"], e["actor_label"], e["criticality"]) for e in _events(client, admin, headers=other)]
    assert types == [
        ("logout", "owner@acmecorp.io", "info"),
        # Someone tried this account's password: shown as unknown, not the owner.
        ("login_failed", "Unknown", "warning"),
        ("login", "owner@acmecorp.io", "info"),
        ("registered", "owner@acmecorp.io", "info"),
    ]


def test_sign_ins_show_in_every_org_of_the_account_only(client, admin):
    auditor = member(client, admin[0], admin[1], "auditor")
    auditor_email = f"auditor-{admin[1][:8]}@example.io"
    client.post("/api/v1/auth/login", json={"email": auditor_email, "password": "wrong"})
    [event] = _events(client, admin, type="login_failed")
    assert event["item"] == auditor_email
    # ...and in the auditor's own org too (registration made them one).
    own_org = client.get("/api/v1/orgs", headers=auditor).json()
    own = next(o for o in own_org if o["id"] != admin[1])["id"]
    assert [e["type"] for e in client.get(f"/api/v1/orgs/{own}/events", headers=auditor).json()["items"]][0] == "login_failed"
    # Another org entirely sees none of it.
    other = register(client, "else@else.io", org_name="Else")
    other_org = first_org_id(client, other)
    assert [e["type"] for e in client.get(f"/api/v1/orgs/{other_org}/events", headers=other).json()["items"]] == [
        "registered"
    ]


def test_changes_by_hand_are_recorded(client, admin):
    client.patch(_url(admin, "/settings"), headers=admin[0], json={"archive_retention_days": 30})
    client.patch(_url(admin, "/settings"), headers=admin[0], json={"archive_retention_days": 30})  # no change
    member(client, admin[0], admin[1], "viewer")
    client.post(_url(admin, "/assets"), headers=admin[0], json={"type": "server", "hostname": "db-01"})
    client.post(_url(admin, "/findings"), headers=admin[0], json={"domain": "incident_response", "severity": "high", "category": "IR"})
    copy = client.post(_url(admin, "/import-profiles"), headers=admin[0], json={"copy_from": "endpoint_agent", "name": "Ours"}).json()
    client.patch(_url(admin, f"/import-profiles/{copy['key']}"), headers=admin[0], json={"name": "Ours v2"})
    client.delete(_url(admin, f"/import-profiles/{copy['key']}"), headers=admin[0])

    by_type = {e["type"]: e for e in _events(client, admin)}
    assert by_type["settings_changed"]["details"] == {"archive_retention_days": {"from": None, "to": 30}}
    assert len(_events(client, admin, type="settings_changed")) == 1
    assert by_type["member_added"]["details"] == {"role": "viewer"}
    assert by_type["asset_added"]["item"] == "db-01"
    assert (by_type["finding_added"]["item"], by_type["finding_added"]["details"]["severity"]) == ("IR", "high")
    assert by_type["profile_created"]["item"] == "Ours"
    assert by_type["profile_updated"]["details"] == {"changed": ["name"]}
    assert by_type["profile_deleted"]["item"] == "Ours v2"


def test_an_import_rolled_back_leaves_no_event(client, admin, monkeypatch, db_session):
    from app.services import ingestion_service

    def boom(*args, **kwargs):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(ingestion_service, "_write_findings", boom)
    with pytest.raises(RuntimeError):
        upload(client, _url(admin, "/findings/import"), admin[0], "f.csv", b"hostname,domain,severity\nh,network_config,low\n")
    [event] = _events(client, admin, type="import")
    assert event["outcome"] == "failed"  # the failure is recorded; nothing claims it imported


# --- Activity: listing --------------------------------------------------------


def test_the_list_searches_filters_and_sorts(client, admin, db_session):
    upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    client.post("/api/v1/auth/login", json={"email": "owner@acmecorp.io", "password": "wrong"})
    db_session.add(Event(org_id=None, type="worker_started", actor_label="System", outcome="completed",
                         criticality=Criticality.info))
    db_session.commit()

    types = lambda **params: [e["type"] for e in _events(client, admin, **params)]  # noqa: E731
    assert types(criticality="warning") == ["login_failed"]
    assert set(types(type=["import", "worker_started"])) == {"import", "worker_started"}
    assert set(types(who="owner")) == {"import", "registered"}
    assert set(types(who="system")) == {"worker_started"}
    assert types(who="unknown") == ["login_failed"]
    assert types(item="a.csv") == ["import"]
    assert types(result="failed") == []
    # The search box: items, who, and the events' names as shown.
    assert types(q="signed up") == ["registered"]
    assert set(types(q="acmecorp")) == {"registered", "login_failed", "import"}
    today = datetime.now(timezone.utc).date()
    assert types(until=str(today - timedelta(days=1))) == []
    assert len(types(since=str(today))) == 4
    # Newest first by default; any column either way.
    assert types(sort="criticality", order="desc")[0] == "login_failed"
    assert types(sort="event", order="asc") == sorted(types())

    facets = client.get(_url(admin, "/events/facets"), headers=admin[0]).json()
    assert facets == {"type": ["import", "login_failed", "registered", "worker_started"], "result": ["completed"]}


def test_archived_and_imports_filter_and_sort(client, admin):
    # Names that sort the same whether the database compares characters one
    # by one (Windows dev) or ignores punctuation (Linux: CI, production).
    # The lists sort with the database's own collation, so sorting stays
    # indexed (hostname on 2M assets: instant, 0.63 s with COLLATE "C").
    for name, content in (("b.csv", ASSETS), ("a.csv", ASSETS + b"server,web-09\n")):
        upload(client, _url(admin, "/assets/import"), admin[0], name, content)
    bad = upload(client, _url(admin, "/assets/import"), admin[0], "c-bad.csv", b"type,hostname\nnot-a-type,x\n").json()

    uploads = lambda **params: [u["filename"] for u in client.get(_url(admin, "/uploads"), headers=admin[0], params=params).json()["items"]]  # noqa: E731
    assert uploads() == ["c-bad.csv", "a.csv", "b.csv"]  # newest first
    assert uploads(sort="filename", order="asc") == ["a.csv", "b.csv", "c-bad.csv"]
    assert uploads(status="failed") == ["c-bad.csv"]
    assert uploads(filename="b") == ["c-bad.csv", "b.csv"]
    assert uploads(uploaded_by="owner", type="asset_import") == ["c-bad.csv", "a.csv", "b.csv"]
    facets = client.get(_url(admin, "/uploads/facets"), headers=admin[0]).json()
    assert facets == {"type": ["asset_import"], "status": ["completed", "failed"]}

    for scan in client.get(_url(admin, "/uploads"), headers=admin[0]).json()["items"]:
        client.post(_url(admin, f"/scans/{scan['id']}/archive"), headers=admin[0])
    archived = lambda **params: [  # noqa: E731
        i["label"]
        for i in client.get(_url(admin, "/archive"), headers=admin[0], params={"type": "upload", **params}).json()["items"]
    ]
    assert archived()[0] == "b.csv"  # archived last: first
    assert archived(sort="name", order="asc") == ["a.csv", "b.csv", "c-bad.csv"]
    assert archived(name="bad") == ["c-bad.csv"]
    assert archived(archived_by="nobody") == []
    assert set(archived(q="owner")) == {"a.csv", "b.csv", "c-bad.csv"}
    assert bad["status"] == "failed"


def test_every_member_reads_it(client, admin):
    viewer = member(client, admin[0], admin[1], "viewer")
    assert _events(client, admin, headers=viewer)
    outsider = register(client, "else@else.io", org_name="Else")
    assert client.get(_url(admin, "/events"), headers=outsider).status_code == 403


# --- Activity: retention ------------------------------------------------------


def test_events_past_the_orgs_retention_are_deleted(client, admin, db_session):
    org_id = uuid.UUID(admin[1])
    old = datetime.now(timezone.utc) - timedelta(days=100)
    db_session.add(Event(org_id=org_id, type="login", actor_label="x", outcome="completed",
                         criticality=Criticality.critical, started_at=old, ended_at=old))
    db_session.commit()
    assert events.purge_expired_events(db_session) == 0  # 365 days by default

    client.patch(_url(admin, "/settings"), headers=admin[0], json={"event_retention_days": 90})
    assert events.purge_expired_events(db_session) == 1
    [cleanup] = _events(client, admin, type="event_cleanup")
    assert cleanup["counts"] == {"expired": 1} and cleanup["criticality"] == "info"


def test_the_safety_net_trims_the_oldest_info_events_only(client, admin, monkeypatch, db_session):
    org_id = uuid.UUID(admin[1])
    monkeypatch.setattr(settings, "EVENT_SAFETY_NET_ROWS", 1000)
    now = datetime.now(timezone.utc)
    for i in range(1005):
        when = now - timedelta(minutes=2000 - i)
        db_session.add(Event(org_id=org_id, type="login_failed" if i < 10 else "login", actor_label="x",
                             outcome="completed", criticality=Criticality.warning if i < 10 else Criticality.info,
                             started_at=when, ended_at=when))
    db_session.commit()

    assert events.purge_expired_events(db_session) == 6  # 1,006 events with registration
    kept = db_session.query(Event).filter(Event.org_id == org_id, Event.criticality == Criticality.warning).count()
    assert kept == 10 + 1  # every warning kept, plus the clean-up's own warning
    [cleanup] = _events(client, admin, type="event_cleanup")
    assert (cleanup["criticality"], cleanup["counts"]) == ("warning", {"trimmed": 6})
