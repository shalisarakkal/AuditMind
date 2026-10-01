"""Staged, resumable imports (Phase 2f part 1): the background worker reads
an upload in chunks into staging, carries on after a cut-off from its last
chunk, and publishes all of it at once."""

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.models.asset import Asset
from app.models.enums import Domain, ScanStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.services import import_staging, ingestion_service
from app.services.import_staging import StagedRow
from app.services.ingestion_service import FindingRow
from app.services.org_settings import apply_overrides
from app.worker import runner
from tests.conftest import requires_db
from tests.helpers import first_org_id, register, run_worker, upload

pytestmark = requires_db

# 9 rows: staged in chunks of 2 (WRITE_BATCH below).
ASSETS = b"type,hostname\n" + b"".join(f"server,web-{n:02}\n".encode() for n in range(1, 10))


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)  # every upload goes to the worker
    monkeypatch.setattr(ingestion_service, "WRITE_BATCH", 2)
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _upload(client, admin, content=ASSETS, name="a.csv") -> uuid.UUID:
    resp = upload(client, f"/api/v1/orgs/{admin[1]}/assets/import", admin[0], name, content)
    assert resp.status_code == 202, resp.text
    return uuid.UUID(resp.json()["scan_id"])


def _staged(db) -> tuple[int, int]:
    """(chunks, states) staged, for any import."""
    db.rollback()
    return (
        db.execute(text("SELECT count(*) FROM import_staging_chunks")).scalar(),
        db.execute(text("SELECT count(*) FROM import_staging_state")).scalar(),
    )


def _cut_off(db, scan_id):
    """What the worker finds after a crash: still running, no check-in."""
    db.rollback()
    scan = db.get(Scan, scan_id)
    scan.status = ScanStatus.running
    scan.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)
    db.commit()
    runner.reap_stale(db)
    db.refresh(scan)
    return scan


def _crash_after(monkeypatch, calls: int, target=import_staging.DbStaging, name="add"):
    """The worker dies (not an error it records) after `calls` calls."""
    original = getattr(target, name)
    seen = {"n": 0}

    def crashing(self, *args, **kwargs):
        seen["n"] += 1
        if seen["n"] > calls:
            raise KeyboardInterrupt  # like the process being killed
        return original(self, *args, **kwargs)

    monkeypatch.setattr(target, name, crashing)
    return lambda: monkeypatch.setattr(target, name, original)


def _record_reads(monkeypatch) -> list[int]:
    """The file rows checked from now on."""
    read: list[int] = []
    check = ingestion_service._RowChecker.check

    def recording(self, row, record, state):
        read.append(row)
        return check(self, row, record, state)

    monkeypatch.setattr(ingestion_service._RowChecker, "check", recording)
    return read


def test_an_import_cut_off_while_reading_carries_on_from_its_last_chunk(client, admin, monkeypatch, db_session):
    scan_id = _upload(client, admin)
    restore = _crash_after(monkeypatch, 2)  # two chunks (4 rows) staged
    with pytest.raises(KeyboardInterrupt):
        run_worker()
    restore()
    assert _staged(db_session) == (2, 1)
    assert db_session.query(Asset).count() == 0  # nothing published

    # Carries on: rows 1-4 aren't read again.
    read = _record_reads(monkeypatch)
    scan = _cut_off(db_session, scan_id)
    assert (scan.status, scan.retry_count) == (ScanStatus.pending, 1)
    assert run_worker() == 1
    assert read == [6, 7, 8, 9, 10]  # CSV line numbers: rows 5-9 of data

    db_session.refresh(scan)
    assert scan.status == ScanStatus.completed
    assert scan.summary["created"] == 9
    assert db_session.query(Asset).count() == 9
    assert _staged(db_session) == (0, 0)  # dropped once it ended


def test_an_import_cut_off_while_publishing_publishes_again_without_reading(client, admin, monkeypatch, db_session):
    scan_id = _upload(client, admin)
    restore = _crash_after(monkeypatch, 5, ingestion_service._Publisher, "publish")
    with pytest.raises(KeyboardInterrupt):
        run_worker()
    restore()
    db_session.rollback()  # what the crash does to its transaction
    assert db_session.query(Asset).count() == 0  # nothing half-published

    read = _record_reads(monkeypatch)
    _cut_off(db_session, scan_id)
    assert run_worker() == 1
    assert read == []  # already read: straight to publishing
    assert db_session.get(Scan, scan_id).summary["created"] == 9
    assert db_session.query(Asset).count() == 9


def test_changed_settings_mean_reading_again(client, admin, monkeypatch, db_session):
    scan_id = _upload(client, admin)
    restore = _crash_after(monkeypatch, 2)
    with pytest.raises(KeyboardInterrupt):
        run_worker()
    restore()
    org = db_session.get(Organization, uuid.UUID(admin[1]))
    apply_overrides(org, {"asset_existing_strategy": "skip"})
    db_session.commit()

    read = _record_reads(monkeypatch)
    _cut_off(db_session, scan_id)
    run_worker()
    assert read == list(range(2, 11))  # from the start
    assert db_session.get(Scan, scan_id).summary["created"] == 9


def test_staging_that_cant_be_read_back_is_read_again(client, admin, monkeypatch, db_session):
    scan_id = _upload(client, admin)
    restore = _crash_after(monkeypatch, 2)
    with pytest.raises(KeyboardInterrupt):
        run_worker()
    restore()
    db_session.execute(text("UPDATE import_staging_state SET data = 'not a pickle'::bytea"))
    db_session.commit()
    _cut_off(db_session, scan_id)
    run_worker()
    assert db_session.get(Scan, scan_id).summary["created"] == 9


def test_cut_off_too_often_fails_and_drops_its_staging(client, admin, monkeypatch, db_session):
    scan_id = _upload(client, admin)
    restore = _crash_after(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        run_worker()
    restore()
    scan = db_session.get(Scan, scan_id)
    scan.retry_count = runner.MAX_RESUMES
    db_session.commit()
    scan = _cut_off(db_session, scan_id)
    assert scan.status == ScanStatus.failed
    assert _staged(db_session) == (0, 0)


def test_all_or_nothing_stages_nothing_after_a_bad_row_but_counts_every_error(client, admin, monkeypatch, db_session):
    org = db_session.get(Organization, uuid.UUID(admin[1]))
    apply_overrides(org, {"import_partial_success": False})
    db_session.commit()
    content = b"type,hostname\nserver,a\nnot-a-type,b\nserver,c\nalso-wrong,d\nserver,e\n"
    scan_id = _upload(client, admin, content)
    staged = []
    add = import_staging.DbStaging.add

    def recording(self, items, state):
        staged.extend(item.row for item in items)
        return add(self, items, state)

    monkeypatch.setattr(import_staging.DbStaging, "add", recording)
    run_worker()
    scan = db_session.get(Scan, scan_id)
    assert scan.status == ScanStatus.failed
    assert scan.summary["failed"] == 2
    assert [e["row"] for e in scan.summary["errors"]] == [3, 5]
    assert staged == [2]  # only the row before the first bad one
    assert db_session.query(Asset).count() == 0
    assert _staged(db_session) == (0, 0)


def test_the_daily_sweep_drops_staging_nothing_waits_for(client, admin, db_session):
    scan = Scan(org_id=uuid.UUID(admin[1]), scan_type="asset_import", status=ScanStatus.failed, source="upload")
    db_session.add(scan)
    db_session.commit()
    db_session.execute(
        text("INSERT INTO import_staging_chunks (scan_id, seq, data) VALUES (:s, 1, 'x'), (:s, 2, 'y')"), {"s": scan.id}
    )
    db_session.commit()
    assert import_staging.purge_orphans(db_session) == 2
    assert _staged(db_session) == (0, 0)


def test_the_report_is_the_same_whether_staged_in_memory_or_the_database(client, admin, monkeypatch, db_session):
    content = (
        b"type,hostname,ip\nserver,web-01,10.0.0.1\nserver,web-01,10.0.0.2\nlaptop,web-02,\n"
        b"bad,web-03,\nserver,,127.0.0.1\nserver,web-01,10.0.0.3\n"
    )
    # Run in the request (staged in memory)...
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10_000_000)
    in_memory = upload(client, f"/api/v1/orgs/{admin[1]}/assets/import", admin[0], "m.csv", content)
    assert in_memory.status_code == 201, in_memory.text
    first = in_memory.json()["report"]

    # ...and the same file into a fresh org through the worker (in the database).
    other = register(client, "other@globex.io", "Globex")
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    resp = upload(client, f"/api/v1/orgs/{first_org_id(client, other)}/assets/import", other, "m.csv", content)
    assert run_worker() == 1
    staged = db_session.get(Scan, uuid.UUID(resp.json()["scan_id"])).summary
    for key in ("created", "updated", "failed", "errors", "warnings", "warnings_total"):
        assert staged[key] == first[key], key
    assert staged["warnings_total"] >= 2  # loopback IP, web-01 repeated with different values


# --- The fingerprint ------------------------------------------------------------

_FINGERPRINT = """
import app.db.base
from app.services.ingestion_service import _fingerprint
from app.services.import_profiles import FAMILIES, builtin_profile
from app.services.org_settings import resolve_ingestion_settings
class Org:
    ingestion_overrides = {"import_partial_success": False, "asset_existing_strategy": "skip", "event_retention_days": 30}
settings = resolve_ingestion_settings(Org())
print(_fingerprint("profile", "csv", settings, builtin_profile(FAMILIES["endpoint_agent"])))
print(_fingerprint("assets", "csv", settings, None))
"""


def test_the_fingerprint_is_the_same_in_every_process():
    """A restarted worker must recognise its own staging: nothing in the
    fingerprint may depend on the process (memory addresses, set order)."""
    backend = Path(__file__).resolve().parents[2]
    runs = [
        subprocess.run(
            [sys.executable, "-c", _FINGERPRINT],
            cwd=backend,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2")
    ]
    assert runs[0] == runs[1] and len(runs[0].split()) == 2


# --- The seam for rows summed up (Phase 2f part 2) --------------------------------


class _CountingProfile:
    """A stand-in for an event log source: counts every row, and gives one
    finding with the count once all are read."""

    key = "counting"
    creates_assets = False
    json_list_key = "records"

    def __init__(self):
        self.rows = 0

    def read_row(self, row, record, ingestion, warnings):
        self.rows += 1
        return None, []

    def finish(self):
        finding = FindingRow(
            row=0, hostname="events", ip=None, domain=Domain.monitoring_detection, severity=Severity.low,
            category="Rows", description=f"{self.rows} rows", source="counting",
        )
        return [StagedRow(row=0, asset=None, findings=[finding])]

    def snapshot(self):
        return {"rows": self.rows}

    def restore(self, state):
        self.rows = state["rows"]


def test_what_a_source_gathers_across_rows_survives_a_resume(admin, monkeypatch, db_session, tmp_path):
    path = tmp_path / "events.csv"
    path.write_bytes(ASSETS)  # 9 rows
    scan = Scan(org_id=uuid.UUID(admin[1]), scan_type="counting_import", source="upload", status=ScanStatus.pending)
    db_session.add(scan)
    db_session.commit()

    restore = _crash_after(monkeypatch, 2)  # 4 rows read, then cut off
    with pytest.raises(KeyboardInterrupt):
        ingestion_service.process_import(db_session, scan, "profile", "csv", path, _CountingProfile())
    restore()
    db_session.rollback()

    # A new process: a fresh source, whose count comes back from staging.
    report = ingestion_service.process_import(db_session, db_session.get(Scan, scan.id), "profile", "csv", path, _CountingProfile())
    assert report.created == 1
    [finding] = db_session.query(Finding).all()
    assert finding.description == "9 rows"
