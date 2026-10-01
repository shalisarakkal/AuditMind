"""The background worker (Phase 2d part 3): runs large imports and archive,
restore and purge jobs outside the web server, so pages stay fast while they
run, plus the daily purge of archived items and old Activity events.

The queue is the database: uploads waiting for it (scans with status
pending) and archive jobs (archive_jobs, pending), oldest first, each taken
with FOR UPDATE SKIP LOCKED so it runs once. A request that runs a small job
itself takes it first the same way.

A thread checks in every HEARTBEAT_SECONDS (worker_status, and the running
job's heartbeat_at), even while the main loop is busy in a long import. A
job with no check-in for WORKER_STALE_SECONDS was cut off (the worker
stopped): an import is started again once from its saved file (imports are
all-or-nothing, so nothing of the first try was kept); an archive job
carries on from where it was, up to MAX_RESUMES times. A job only waiting
(for the org's lock) is never taken for dead: whoever runs a job holds its
job lock (org_lock.job_running) until it's done.

Ctrl+C stops it once the running job is done. A second Ctrl+C, or closing
its window, stops it at once: what it was running is picked up again at the
next start (an import from its saved file, an archive job where it was).
"""

import logging
import signal
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.uploads import upload_path
from app.core.config import check_secret_key, settings
from app.models.archive import ArchiveJob
from app.models.enums import ScanStatus
from app.models.event import WorkerStatus
from app.models.scan import Scan
from app.services import archive_service, ingestion_background, platform
from app.services.events import purge_expired_events, record_event
from app.services.import_profiles import resolve_profile
from app.services.org_lock import ARCHIVE_JOB, IMPORT_JOB, job_is_running
from app.services.ingestion_service import IngestionError, detect_format, fail_import, process_import
from app.services.sessions import purge_old_sessions

logger = logging.getLogger("app.worker")

HEARTBEAT_SECONDS = 15
# An archive job cut off more often than this is failed, not carried on.
MAX_RESUMES = 3
HOUSEKEEPING_EVERY = timedelta(days=1)
FIRST_HOUSEKEEPING_AFTER = timedelta(minutes=1)
REAP_EVERY = timedelta(seconds=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- One job ------------------------------------------------------------------


class _Current:
    """What the worker is running, for the check-in thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.job: tuple[str, uuid.UUID] | None = None

    def set(self, job: tuple[str, uuid.UUID] | None) -> None:
        with self.lock:
            self.job = job

    def get(self) -> tuple[str, uuid.UUID] | None:
        with self.lock:
            return self.job


current = _Current()


def _oldest_job(db: Session, low_priority: bool):
    """The oldest waiting archive job: one someone started, or a System one
    (the auto-purge) that has waited AUTO_PURGE_MAX_WAIT_MINUTES; or, with
    `low_priority`, any System one."""
    by_system = ArchiveJob.started_by.is_(None)
    if not low_priority:
        overdue = ArchiveJob.started_at <= _now() - timedelta(minutes=settings.AUTO_PURGE_MAX_WAIT_MINUTES)
        by_system = ~by_system | overdue
    return db.execute(
        select(ArchiveJob.id, ArchiveJob.started_at)
        .where(ArchiveJob.status == ScanStatus.pending, by_system)
        .order_by(ArchiveJob.started_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()


def claim_next(db: Session) -> tuple[str, uuid.UUID] | None:
    """Take the oldest waiting job: ("import", scan id) or ("archive", job
    id). Committed as running, with a first check-in. Jobs the system started
    (the daily auto-purge) are low priority: taken only when no upload or
    job someone started waits, until they've waited
    AUTO_PURGE_MAX_WAIT_MINUTES; then they take their turn by age."""
    scan = db.execute(
        select(Scan.id, Scan.started_at)
        .where(Scan.status == ScanStatus.pending, Scan.source == "upload")
        .order_by(Scan.started_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    job = _oldest_job(db, low_priority=False)
    if scan is None and job is None:
        job = _oldest_job(db, low_priority=True)
    if scan is None and job is None:
        db.rollback()
        return None
    now = _now()
    if job is None or (scan is not None and scan.started_at <= job.started_at):
        db.execute(update(Scan).where(Scan.id == scan.id).values(status=ScanStatus.running, heartbeat_at=now))
        claimed = ("import", scan.id)
    else:
        db.execute(
            update(ArchiveJob).where(ArchiveJob.id == job.id).values(status=ScanStatus.running, heartbeat_at=now)
        )
        claimed = ("archive", job.id)
    db.commit()  # also lets go of the one not taken
    return claimed


def run_once(db: Session) -> bool:
    """Take and run one waiting job; else purge an org whose purge the
    Sysadmin asked for (it's already gone for everyone, so it waits its
    turn). False if there's nothing to do."""
    claimed = claim_next(db)
    if claimed is None:
        try:
            return platform.purge_next_org(db)
        except Exception:
            # Carries on from where it stopped next time.
            logger.exception("Purging an organization failed")
            db.rollback()
            return False
    kind, job_id = claimed
    current.set(claimed)
    try:
        if kind == "import":
            run_import(db, job_id)
        else:
            archive_service.run_job(db, job_id)
    except Exception:
        # Each runner has recorded its failure (and its event) already.
        logger.exception("%s job %s failed", kind, job_id)
        db.rollback()
    finally:
        current.set(None)
    return True


def drain(db: Session) -> int:
    """Run waiting jobs until there are none (tests; a one-off catch-up)."""
    count = 0
    while run_once(db):
        count += 1
    return count


def run_import(db: Session, scan_id: uuid.UUID) -> None:
    """Import an upload from its saved file, then delete the file once the
    outcome is saved, unless it failed for a reason other than its content
    (kept for Retry, see Scan.retryable). If the import was cut off (Ctrl+C,
    the database went away) the file stays, to start it again."""
    scan = db.get(Scan, scan_id)
    path = upload_path(scan.id)
    if not path.exists():
        fail_import(db, scan, "The uploaded file wasn't found (it was deleted before it could be imported)")
        return
    try:
        kind = "profile" if scan.profile else ("assets" if scan.scan_type == "asset_import" else "findings")
        profile = resolve_profile(db, scan.org_id, scan.profile) if scan.profile else None
        fmt = detect_format(scan.filename, kind)
    except IngestionError as exc:  # its import profile was deleted meanwhile, say
        fail_import(db, scan, str(exc))
        path.unlink(missing_ok=True)
        return
    content = path.read_bytes()
    try:
        process_import(
            db,
            scan,
            kind,
            fmt,
            content,
            profile,
            progress=lambda phase, done, total: ingestion_background.write_progress(scan_id, phase, done, total),
        )
    except Exception:
        _delete_if_finished(db, scan_id, path)
        raise
    _delete_if_finished(db, scan_id, path)


def _delete_if_finished(db: Session, scan_id: uuid.UUID, path) -> None:
    """Delete the saved file if the import's outcome is saved, except after a
    failure that wasn't its content's (kept for Retry); if that can't be
    checked (the database went away), keep it."""
    try:
        db.rollback()
        status, summary = db.execute(select(Scan.status, Scan.summary).where(Scan.id == scan_id)).one()
    except Exception:
        logger.warning("Couldn't check import %s; keeping its file", scan_id, exc_info=True)
        return
    if status == ScanStatus.completed or (status == ScanStatus.failed and not (summary or {}).get("error")):
        path.unlink(missing_ok=True)


# --- Cut-off jobs -------------------------------------------------------------


def reap_stale(db: Session, now: datetime | None = None) -> None:
    """Jobs still "running" that nothing runs any more (no process holds
    their job lock, org_lock.job_running, and none has checked in for
    WORKER_STALE_SECONDS): start again (an import, once), carry on (an
    archive job), or mark failed. A job that's only waiting (for the org's
    lock, say) holds its job lock, so it's left alone however long it
    waits."""
    now = now or _now()
    stale = now - timedelta(seconds=settings.WORKER_STALE_SECONDS)
    running_here = current.get()

    def quiet(model):
        # Not checked in lately (run by the worker), or started a while ago
        # (run by a request, which doesn't check in); either way no lock.
        last = func.coalesce(model.heartbeat_at, model.run_started_at, model.started_at)
        return select(model).where(model.status == ScanStatus.running, last < stale)

    for scan in db.scalars(quiet(Scan)).all():
        if running_here == ("import", scan.id) or job_is_running(db, IMPORT_JOB, scan.id):
            continue
        by_worker = scan.heartbeat_at is not None
        saved = upload_path(scan.id).exists()
        if by_worker and scan.retry_count == 0 and saved:
            logger.warning("Import %s (%s) was cut off: starting it again", scan.id, scan.filename)
            scan.status, scan.retry_count, scan.heartbeat_at, scan.progress = ScanStatus.pending, 1, None, None
            db.commit()
            continue
        if not (by_worker and saved):
            upload_path(scan.id).unlink(missing_ok=True)
        if not by_worker:
            message = "Stopped when the server restarted: import it again"
        elif scan.retry_count:
            # Its file is kept: Retry runs it again.
            message = "Cut off twice (the background worker stopped)"
        else:
            message = "Cut off, and its saved file is gone: import it again"
        logger.warning("Import %s (%s) failed: %s", scan.id, scan.filename, message)
        fail_import(db, scan, message)

    for job in db.scalars(quiet(ArchiveJob)).all():
        if running_here == ("archive", job.id) or job_is_running(db, ARCHIVE_JOB, job.id):
            continue
        if job.heartbeat_at is not None and job.retry_count < MAX_RESUMES:
            logger.warning("Archive job %s was cut off: carrying on", job.id)
            job.status, job.retry_count, job.heartbeat_at = ScanStatus.pending, job.retry_count + 1, None
            db.commit()
            continue
        archive_service.fail_job(db, job, "Stopped part-way: start it again to carry on from where it stopped")


# --- Daily housekeeping -------------------------------------------------------


def housekeeping(db: Session) -> None:
    """Purge archived items and Activity events past their retention (each
    recorded in Activity), delete old ended sign-in sessions, and delete
    uploaded files nothing is waiting for."""
    if settings.ARCHIVE_AUTO_PURGE:
        queued = archive_service.purge_expired(db, queue=True)
        logger.info("Auto-purge: %d archived item(s) queued (run when nothing else waits)", queued)
        logger.info("Activity clean-up: %d event(s) deleted", purge_expired_events(db))
    logger.info("Sign-in clean-up: %d old session(s) deleted", purge_old_sessions(db))
    _sweep_uploads(db)


def _sweep_uploads(db: Session) -> None:
    folder = settings.upload_dir
    if not folder.exists():
        return
    kept_since = _now() - timedelta(days=settings.UPLOAD_KEEP_FAILED_DAYS)
    waiting = {
        str(scan_id)
        for scan_id in db.scalars(
            select(Scan.id).where(
                Scan.status.in_((ScanStatus.pending, ScanStatus.running))
                # Failed but not for its content: kept for Retry a while.
                | (
                    (Scan.status == ScanStatus.failed)
                    & Scan.summary.has_key("error")
                    & Scan.archived_at.is_(None)
                    & (Scan.completed_at > kept_since)
                )
            )
        )
    }
    old = time.time() - 3600
    for path in folder.iterdir():
        # Files half-received when the web server stopped, and files whose
        # upload finished or went away: an hour's grace for ones arriving.
        # Anything else in the folder (a subfolder) isn't ours: left alone.
        try:
            if path.is_file() and path.stem not in waiting and path.stat().st_mtime < old:
                logger.info("Deleting leftover upload %s", path.name)
                path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Couldn't delete leftover upload %s", path.name, exc_info=True)


# --- The process --------------------------------------------------------------


def _check_in(stop: threading.Event, started_at: datetime) -> None:
    """Every HEARTBEAT_SECONDS: the worker's check-in, and the running job's."""
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with ingestion_background.open_progress_session() as db:
                now = _now()
                db.execute(
                    insert(WorkerStatus)
                    .values(id=1, started_at=started_at, heartbeat_at=now)
                    .on_conflict_do_update(index_elements=["id"], set_={"heartbeat_at": now})
                )
                job = current.get()
                if job is not None:
                    model = Scan if job[0] == "import" else ArchiveJob
                    db.execute(update(model).where(model.id == job[1]).values(heartbeat_at=now))
                db.commit()
        except Exception:
            logger.warning("Couldn't check in", exc_info=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    check_secret_key(settings.SECRET_KEY)
    stop = threading.Event()
    started_at = _now()

    def request_stop(signum, frame):
        if stop.is_set():
            raise KeyboardInterrupt  # second Ctrl+C: stop now
        logger.info("Stopping once the running job is done (Ctrl+C again to stop now)")
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)

    with ingestion_background.open_session() as db:
        db.execute(
            insert(WorkerStatus)
            .values(id=1, started_at=started_at, heartbeat_at=started_at)
            .on_conflict_do_update(index_elements=["id"], set_={"started_at": started_at, "heartbeat_at": started_at})
        )
        record_event(db, "worker_started", org_id=None)
        db.commit()
    threading.Thread(target=_check_in, args=(stop, started_at), daemon=True).start()
    logger.info("Background worker started; uploads wait in %s", settings.upload_dir)

    next_reap = _now()
    next_housekeeping = _now() + FIRST_HOUSEKEEPING_AFTER
    failures = 0
    try:
        while not stop.is_set():
            try:
                with ingestion_background.open_session() as db:
                    if _now() >= next_reap:
                        next_reap = _now() + REAP_EVERY
                        reap_stale(db)
                    if _now() >= next_housekeeping:
                        next_housekeeping = _now() + HOUSEKEEPING_EVERY
                        housekeeping(db)
                    ran = run_once(db)
                failures = 0
            except Exception:
                # The database restarting, say: wait, then carry on (longer
                # each time it fails again, up to a minute).
                failures += 1
                wait = min(60, 2**failures)
                logger.exception("Worker loop failed; trying again in %d s", wait)
                stop.wait(wait)
                continue
            if not ran:
                stop.wait(settings.WORKER_POLL_SECONDS)
    finally:
        stop.set()
        with ingestion_background.open_session() as db:
            record_event(db, "worker_stopped", org_id=None)
            db.commit()
        logger.info("Background worker stopped")
