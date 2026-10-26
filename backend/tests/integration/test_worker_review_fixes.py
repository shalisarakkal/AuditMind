"""Fixes from the review of Phase 2d part 3: the worker never takes a job
that's only waiting for dead; an interrupted import keeps its saved file;
the worker carries on after errors; findings-only profiles count findings;
the safety net trims a flood of failed sign-ins; the history migrations
(0013 safe to run again; 0014); every list filters by date."""

import importlib.util
import os
import pathlib
import signal
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.api.uploads import upload_path
from app.core.config import settings
from app.models.enums import Criticality, ScanStatus
from app.models.event import Event
from app.models.scan import Scan
from app.services import events, ingestion_service
from app.services.org_lock import lock_org
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import FIXTURES, first_org_id, register, upload

pytestmark = requires_db
ASSETS = b"type,hostname\nserver,web-01\nserver,web-02\n"


def test_queue_metrics_close_their_own_read_transaction(db_session, monkeypatch):
    from contextlib import contextmanager
    sessions = []
    values = {}
    factory = sessionmaker(bind=db_session.get_bind())
    @contextmanager
    def open_metrics():
        with factory() as session:
            sessions.append(session)
            yield session
    monkeypatch.setattr(runner.ingestion_background, "open_session", open_metrics)
    monkeypatch.setattr(runner, "set_metric", lambda key, value: values.update({key: value}))
    runner._update_queue_metrics()
    assert len(sessions) == 1
    assert sessions[0].in_transaction() is False
    assert values == {"queue_imports_pending": 0, "queue_archives_pending": 0,
        "queue_reports_pending": 0, "queue_total_pending": 0}


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _url(admin, path):
    return f"/api/v1/orgs/{admin[1]}{path}"


def _large_upload(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    resp = upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    assert resp.status_code == 202, resp.text
    return uuid.UUID(resp.json()["scan_id"])


def _import_events(db, org_id):
    db.expire_all()
    return db.query(Event).filter(Event.org_id == org_id, Event.type == "import").all()


def test_an_import_only_waiting_for_the_org_lock_is_left_alone(client, admin, db_session):
    """Run by a request, long before, and waiting for the org's lock (a long
    job holds it): not dead, however long it waits."""
    org_id = uuid.UUID(admin[1])
    scan = Scan(org_id=org_id, scan_type="asset_import", source="upload", status=ScanStatus.running,
                started_at=datetime.now(timezone.utc) - timedelta(minutes=31), filename="small.csv")
    db_session.add(scan)
    db_session.commit()
    sessions = sessionmaker(bind=db_session.get_bind())
    holder = sessions()
    lock_org(holder, org_id)
    done = {}

    def request():
        s = sessions()
        try:
            done["report"] = ingestion_service.process_import(s, s.get(Scan, scan.id), "assets", "csv", ASSETS)
        finally:
            s.close()

    thread = threading.Thread(target=request)
    thread.start()
    time.sleep(1.5)  # blocked on the org's lock, holding its job lock
    runner.reap_stale(db_session, now=datetime.now(timezone.utc) + timedelta(hours=1))
    db_session.expire_all()
    assert db_session.get(Scan, scan.id).status == ScanStatus.running
    holder.rollback()
    holder.close()
    thread.join(30)
    db_session.expire_all()
    assert db_session.get(Scan, scan.id).status == ScanStatus.completed
    assert [e.outcome for e in _import_events(db_session, org_id)] == ["completed"]


def test_an_import_cut_off_by_ctrl_c_keeps_its_file_and_is_started_again(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    assert runner.claim_next(db_session) == ("import", scan_id)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "process_import", interrupted)
    with pytest.raises(KeyboardInterrupt):
        runner.run_import(db_session, scan_id)
    assert upload_path(scan_id).exists()
    scan = db_session.get(Scan, scan_id)
    scan.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    db_session.commit()
    runner.reap_stale(db_session)
    assert (scan.status, scan.retry_count) == (ScanStatus.pending, 1)


def test_an_import_whose_outcome_cant_be_saved_keeps_its_file(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    runner.claim_next(db_session)

    def database_down(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))

    monkeypatch.setattr(runner, "process_import", database_down)
    with pytest.raises(OperationalError):
        runner.run_import(db_session, scan_id)
    db_session.rollback()
    assert db_session.get(Scan, scan_id).status == ScanStatus.running
    assert upload_path(scan_id).exists()


def test_a_missing_file_says_so(client, admin, monkeypatch, db_session):
    scan_id = _large_upload(client, admin, monkeypatch)
    scan = db_session.get(Scan, scan_id)
    scan.status = ScanStatus.running
    scan.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    db_session.commit()
    upload_path(scan_id).unlink()
    runner.reap_stale(db_session)
    assert scan.summary == {"error": "Cut off, and its saved file is gone: import it again"}


def test_the_worker_carries_on_after_an_error(client, admin, monkeypatch, db_session):
    calls = []

    def run_once(db):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("SELECT", {}, Exception("terminating connection due to administrator command"))
        raise KeyboardInterrupt  # stop the test's worker

    monkeypatch.setattr(runner, "run_once", run_once)
    monkeypatch.setattr(runner, "FIRST_HOUSEKEEPING_AFTER", timedelta(days=1))
    old_int = signal.getsignal(signal.SIGINT)
    old_break = signal.getsignal(signal.SIGBREAK) if hasattr(signal, "SIGBREAK") else None
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.main()
    finally:
        signal.signal(signal.SIGINT, old_int)
        if old_break is not None:
            signal.signal(signal.SIGBREAK, old_break)
    assert len(calls) == 2  # it tried again after the error


def test_housekeeping_leaves_folders_in_uploads_alone(client, admin, db_session):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    folder = settings.upload_dir / "somefolder"
    folder.mkdir()
    os.utime(folder, (time.time() - 7200, time.time() - 7200))
    runner.housekeeping(db_session)
    assert folder.exists()


def test_the_generic_findings_profile_counts_findings(client, admin):
    client.post(
        _url(admin, "/imports"), headers=admin[0],
        files={"file": ("f.csv", (FIXTURES / "findings_generic.csv").read_bytes())},
        data={"profile": "generic_findings", "confirm": "true"},
    )
    [event] = client.get(_url(admin, "/events"), headers=admin[0], params={"type": "import"}).json()["items"]
    assert event["counts"] == {"findings_created": 4, "rows_failed": 2}


def test_the_safety_net_trims_a_flood_of_failed_sign_ins(client, admin, monkeypatch, db_session):
    org_id = uuid.UUID(admin[1])
    monkeypatch.setattr(settings, "EVENT_SAFETY_NET_ROWS", 1000)
    now = datetime.now(timezone.utc)
    db_session.add_all(
        Event(org_id=org_id, type="login_failed", actor_label="Unknown", outcome="completed",
              criticality=Criticality.warning, started_at=now - timedelta(seconds=i), ended_at=now)
        for i in range(1500)
    )
    db_session.add(Event(org_id=org_id, type="archive", actor_label="x", outcome="failed",
                         criticality=Criticality.warning, started_at=now - timedelta(days=1), ended_at=now))
    db_session.commit()
    events.purge_expired_events(db_session)
    remaining = db_session.query(Event).filter(Event.org_id == org_id)
    # The oldest go: the registration (Info), then failed sign-ins; the
    # failed archive (another Warning) is kept, however old.
    assert remaining.count() == 1000 + 1  # plus the clean-up's own event
    assert remaining.filter(Event.type == "archive").count() == 1


# --- The history migrations, run against the test schema (their SQL only) ----


def _run_migration(db, name, fn="upgrade"):
    path = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"migration_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = SimpleNamespace(execute=lambda sql: db.execute(text(sql)))
    getattr(module, fn)()
    db.commit()


def _import(db, org_id, scan_type, counts, summary, outcome="completed"):
    started = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(Scan(org_id=org_id, scan_type=scan_type, source="upload", status=ScanStatus(outcome),
                started_at=started, filename=f"{scan_type}.csv", summary=summary))
    db.add(Event(org_id=org_id, type="import", item=f"{scan_type}.csv", actor_label="x", outcome=outcome,
                 criticality=Criticality.info, started_at=started, ended_at=started, counts=counts))
    db.commit()


def _counts(db, item):
    return db.execute(text("SELECT counts FROM events WHERE item = :i"), {"i": item}).scalar()


def test_0013_can_run_again_without_losing_counts(client, admin, db_session):
    org_id = uuid.UUID(admin[1])
    db_session.execute(text("DELETE FROM events"))
    _import(db_session, org_id, "asset_import", {"created": 5}, {"created": 5})
    _import(db_session, org_id, "generic_findings_import", {"created": 4}, {"created": 4})
    for _ in range(2):
        _run_migration(db_session, "0013_import_event_counts")
        assert _counts(db_session, "asset_import.csv") == {"assets_created": 5}
        assert _counts(db_session, "generic_findings_import.csv") == {"findings_created": 4}


def test_0014_fixes_the_history_carried_over(client, admin, db_session):
    org_id = uuid.UUID(admin[1])
    db_session.execute(text("DELETE FROM events"))
    _import(db_session, org_id, "generic_findings_import", {"assets_created": 4}, {"created": 4})
    _import(db_session, org_id, "findings_csv", None, {"error": "Unexpected error during import"}, outcome="failed")
    db_session.add(Event(org_id=org_id, type="purge", item="Duplicates", actor_label="x", outcome="completed",
                         criticality=Criticality.critical, details={"reason": "duplicate"}))
    db_session.commit()
    _run_migration(db_session, "0014_event_history_fixes")
    assert _counts(db_session, "generic_findings_import.csv") == {"findings_created": 4}
    details = db_session.execute(text("SELECT details FROM events WHERE item = 'findings_csv.csv'")).scalar()
    assert details == {"error": "Unexpected error during import"}
    assert db_session.execute(text("SELECT count(*) FROM events WHERE type = 'purge'")).scalar() == 0


# --- Dates -------------------------------------------------------------------


def test_every_list_filters_by_date(client, admin):
    upload(client, _url(admin, "/assets/import"), admin[0], "a.csv", ASSETS)
    upload(client, _url(admin, "/findings/import"), admin[0], "f.csv",
           b"hostname,domain,severity\nweb-01,network_config,low\n")
    today = datetime.now(timezone.utc).date()
    yesterday = str(today - timedelta(days=1))
    for path, extra in (("/uploads", {}), ("/findings", {}), ("/events", {}), ("/archive", {"type": "upload"})):
        items = lambda **p: client.get(_url(admin, path), headers=admin[0], params={**extra, **p}).json()["total"]  # noqa: E731
        assert items(until=yesterday) == 0, path
        assert items(since=str(today)) == items(), path
