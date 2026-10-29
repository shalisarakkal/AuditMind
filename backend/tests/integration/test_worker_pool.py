"""Bounded, real PostgreSQL concurrency; no large inventory/provider calls."""
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
from app.models.asset import Asset
from app.models.enums import ScanStatus
from app.models.scan import Scan
from app.models.worker_dispatch import WorkerDispatch
from app.services import ingestion_service
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, upload

pytestmark = requires_db


@pytest.fixture
def orgs(client, monkeypatch):
    monkeypatch.setattr(settings, "WORKER_CONCURRENCY", 2)
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 1)
    result = []
    for name in ("alpha", "beta", "gamma"):
        headers = register(client, f'{name}@pool.example', name)
        result.append((headers, uuid.UUID(first_org_id(client, headers))))
    return result


def enqueue(client, org, name, host=None, environment='production'):
    headers, org_id = org
    response = upload(client, f'/api/v1/orgs/{org_id}/assets/import', headers, name + '.csv',
        f'type,hostname,environment\nserver,{host or name},{environment}\n'.encode())
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()['scan_id'])


def finish(db, scan_id):
    db.expire_all()
    db.get(Scan, scan_id).status = ScanStatus.completed
    db.commit()


def test_fairness_skips_busy_backlogs_and_prioritizes_unserved_orgs(client, orgs, db_session):
    a, b, c = orgs
    a1 = enqueue(client, a, 'a1')
    a2 = enqueue(client, a, 'a2')
    enqueue(client, a, 'a3')
    b1 = enqueue(client, b, 'b1')
    c1 = enqueue(client, c, 'c1')
    assert runner.claim_next(db_session) == ('import', a1)
    assert runner.claim_next(db_session) == ('import', b1)  # not blocked by older a2/a3
    assert runner.claim_next(db_session) is None  # installation-wide two-job limit
    finish(db_session, a1)
    assert runner.claim_next(db_session) == ('import', c1)  # never served beats old a2
    finish(db_session, b1)
    finish(db_session, c1)
    assert runner.claim_next(db_session) == ('import', a2)
    assert db_session.query(WorkerDispatch).count() == 3


def test_real_workers_overlap_across_orgs_but_leave_same_org_queued(client, orgs, db_session, monkeypatch):
    a, b, _ = orgs
    a1 = enqueue(client, a, 'first-a', 'host-a')
    a2 = enqueue(client, a, 'second-a', 'host-a', 'staging')
    b1 = enqueue(client, b, 'first-b', 'host-b')
    barrier = threading.Barrier(3)
    release = threading.Event()
    errors, results, entered = [], [], []
    original = ingestion_service._Publisher.__init__

    def paused(self, db, org_id, *args, **kwargs):
        entered.append(org_id)
        barrier.wait(timeout=15)
        if not release.wait(15):
            raise RuntimeError('Test did not release the publishers')
        original(self, db, org_id, *args, **kwargs)

    monkeypatch.setattr(ingestion_service._Publisher, '__init__', paused)
    engine = db_session.get_bind()
    def work():
        try:
            with Session(engine) as db:
                results.append(runner.run_once(db))
        except BaseException as exc:
            errors.append(exc)
    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    heartbeat_stop = threading.Event()
    heartbeat = None
    try:
        barrier.wait(timeout=15)  # both publishers are actually executing at once
        assert set(entered) == {a[1], b[1]}
        assert len(runner.current.all()) == 2
        db_session.expire_all()
        assert db_session.get(Scan, a2).status == ScanStatus.pending
        assert runner.claim_next(db_session) is None
        initial = {s: db_session.get(Scan, s).heartbeat_at for s in (a1, b1)}
        monkeypatch.setattr(runner, 'HEARTBEAT_SECONDS', 0.02)
        heartbeat = threading.Thread(target=runner._check_in, args=(heartbeat_stop, runner._now()), daemon=True)
        heartbeat.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            db_session.expire_all()
            if all(db_session.get(Scan, s).heartbeat_at > initial[s] for s in initial):
                break
            time.sleep(0.02)
        else:
            pytest.fail('Both concurrently running jobs must receive heartbeats')
    finally:
        heartbeat_stop.set()
        if heartbeat:
            heartbeat.join(timeout=5)
        release.set()
        for thread in threads:
            thread.join(timeout=20)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors
    assert results == [True, True]
    assert runner.current.all() == []
    monkeypatch.setattr(ingestion_service._Publisher, '__init__', original)
    assert runner.run_once(db_session)  # a2 now updates a1's asset, not a duplicate
    db_session.expire_all()
    assert db_session.get(Scan, a2).summary['updated'] == 1
    assert db_session.query(Asset).filter(Asset.org_id == a[1]).count() == 1
    assert db_session.query(Asset).filter(Asset.org_id == b[1]).count() == 1
    assert db_session.query(Asset).filter(Asset.org_id == a[1]).one().environment == 'staging'


def test_a_lost_reservation_recovers_with_existing_resume_path(client, orgs, db_session):
    scan_id = enqueue(client, orgs[0], 'recover')
    assert runner.claim_next(db_session) == ('import', scan_id)
    scan = db_session.get(Scan, scan_id)
    scan.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    db_session.commit()
    runner.reap_stale(db_session)
    assert runner.run_once(db_session)
    db_session.expire_all()
    assert db_session.get(Scan, scan_id).status == ScanStatus.completed
    assert db_session.query(Asset).filter(Asset.org_id == orgs[0][1]).count() == 1


def test_duplicate_installation_pool_is_refused_and_lease_is_released(client, db_session):
    with runner._worker_lease():
        with pytest.raises(RuntimeError, match='already running'):
            with runner._worker_lease():
                pytest.fail('A second healthy installation pool must not start')
    with runner._worker_lease():
        pass  # graceful/exceptional context exit releases leadership


def test_unmigrated_pool_fails_before_publishing_healthy_heartbeat(client, db_session, monkeypatch):
    db_session.execute(text('DROP TABLE worker_dispatch'))
    db_session.commit()
    published = []
    monkeypatch.setattr(runner, '_serve', lambda lease: published.append(True))
    with pytest.raises(RuntimeError, match='alembic upgrade head'):
        runner.main()
    assert published == []
