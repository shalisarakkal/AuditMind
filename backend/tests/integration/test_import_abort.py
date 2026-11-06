"""Abort authorization, idempotence and atomic publication rollback."""
from datetime import datetime, timezone
from uuid import UUID
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.asset import Asset
from app.models.scan import Scan
from app.services import ingestion_service
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, upload, run_worker, member

pytestmark = requires_db


@pytest.fixture
def queued(client, monkeypatch):
    headers = register(client, "abort-owner@example.io")
    org = first_org_id(client, headers)
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 1)
    response = upload(client, f"/api/v1/orgs/{org}/assets/import", headers, "assets_valid.csv")
    assert response.status_code == 202
    identifier = response.json()["scan_id"]
    return headers, org, identifier


def test_abort_pending_is_atomic_idempotent_and_retryable(client, db_session, queued):
    headers, org, identifier = queued
    url = f"/api/v1/orgs/{org}/scans/{identifier}/abort"
    response = client.post(url, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "failed" and result["summary"]["aborted"]
    assert result["retryable"] and result["abort_requested_at"]
    assert client.post(url, headers=headers).status_code == 200
    assert run_worker() == 0
    assert db_session.query(Asset).count() == 0


def test_abort_permissions_and_finished_conflict(client, db_session, queued):
    headers, org, identifier = queued
    viewer = member(client, headers, org, "viewer")
    response = client.post(f"/api/v1/orgs/{org}/scans/{identifier}/abort", headers=viewer)
    assert response.status_code == 403
    outsider = register(client, "abort-other@example.io")
    assert client.post(f"/api/v1/orgs/{org}/scans/{identifier}/abort", headers=outsider).status_code in (403,404)
    run_worker()
    assert client.post(f"/api/v1/orgs/{org}/scans/{identifier}/abort", headers=headers).status_code == 409


def test_abort_before_commit_rolls_back_all_published_assets(client, db_session, queued, monkeypatch):
    _, _, identifier = queued
    original = ingestion_service._PendingWrites.flush
    requested = False
    def flush(writes):
        nonlocal requested
        original(writes)
        if not requested:
            requested = True
            with Session(db_session.get_bind()) as control:
                control.execute(update(Scan).where(Scan.id == UUID(identifier)).values(abort_requested_at=datetime.now(timezone.utc)))
                control.commit()
    monkeypatch.setattr(ingestion_service._PendingWrites, "flush", flush)
    run_worker()
    db_session.expire_all()
    scan = db_session.get(Scan, UUID(identifier))
    assert scan.status.value == "failed" and scan.summary["aborted"]
    assert scan.retryable and scan.publication_pid is None
    assert db_session.query(Asset).count() == 0


def test_abort_interrupts_owned_long_sql_and_confirms_rollback(client, db_session, queued):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import time
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.services.import_abort import register_publication, interrupt_publication
    headers, org, identifier = queued
    sid = UUID(identifier)
    scan = db_session.get(Scan, sid)
    scan.status = "running"
    db_session.commit()
    engine = db_session.get_bind()
    registered = Event()
    def publish():
        with Session(engine) as work:
            register_publication(work, sid)
            work.add(Asset(org_id=UUID(org), type="server", hostname="must-rollback.example"))
            work.flush()
            from app.models.archive import AssetScan
            asset_id = work.scalar(select(Asset.id))
            work.add(AssetScan(scan_id=sid, asset_id=asset_id, created=True))
            work.flush()  # Real imports retain a foreign-key KEY SHARE on Scan.
            registered.set()
            try:
                work.execute(text("select pg_sleep(15)"))
            except DBAPIError:
                work.rollback()
                ingestion_service.fail_import(work, work.get(Scan, sid), "Interrupted")
                return True
            return False
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(publish)
        assert registered.wait(5)
        with Session(engine) as control:
            control.execute(text("SET LOCAL lock_timeout='2s'"))
            # Wait until the owned backend is inside the deliberately long SQL.
            for _ in range(100):
                active = control.scalar(text("select count(*) from pg_stat_activity where pid=(select publication_pid from scans where id=:id) and query='select pg_sleep(15)' and state='active'"), {"id":sid})
                control.rollback()
                if active: break
                time.sleep(0.01)
            assert active
            db_session.execute(text("SET LOCAL lock_timeout='2s'"))
            response = client.post(f"/api/v1/orgs/{org}/scans/{sid}/abort", headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "running"
            control.execute(text("SET LOCAL lock_timeout='2s'"))
            assert interrupt_publication(control, sid)
            control.commit()
            assert control.scalar(text("select 1")) == 1
        assert result.result(timeout=5)
    db_session.expire_all()
    assert db_session.get(Scan, sid).summary["aborted"]
    assert db_session.query(Asset).count() == 0


def test_stale_publication_identity_cannot_cancel_reused_backend(client,db_session,queued):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import time
    from sqlalchemy import text
    from app.services.import_abort import register_publication,interrupt_publication
    headers,org,identifier=queued
    sid=UUID(identifier)
    db_session.get(Scan,sid).status="running"
    db_session.commit()
    engine=db_session.get_bind()
    ready=Event()
    def reuse():
        # Pin one physical backend to reproduce pool reuse deterministically.
        with engine.connect() as connection:
            with Session(bind=connection) as old_publication:
                register_publication(old_publication,sid)
                old_publication.rollback()
            with Session(bind=connection) as unrelated_job:
                unrelated_job.execute(text('select pg_current_xact_id()'))
                ready.set()
                unrelated_job.execute(text('select pg_sleep(2)'))
                return True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(reuse)
        assert ready.wait(5)
        with Session(engine) as control:
            for _ in range(100):
                active=control.scalar(text("select count(*) from pg_stat_activity where pid=(select publication_pid from scans where id=:id) and state='active' and query='select pg_sleep(2)'"),{'id':sid})
                control.rollback()
                if active:break
                time.sleep(0.01)
            assert active
            response=client.post(f"/api/v1/orgs/{org}/scans/{sid}/abort",headers=headers)
            assert response.status_code==200,response.text
            assert interrupt_publication(control,sid) is False
            control.commit()
        assert future.result(timeout=5)
