"""The background worker (Phase 2d part 3): runs large imports and archive,
restore and purge jobs outside the web server, so pages stay fast while they
run, plus the daily purge of archived items and old Activity events.

The queue is the database. A bounded thread pool serves organization scopes
least recently dispatched (unserved first), oldest job within each scope.
Status + dispatch metadata are committed together under a short admission lock;
each organization has at most one active queued job. Small synchronous API jobs
retain their inventory locks. Each pool thread owns its own database Session.

A thread checks in every HEARTBEAT_SECONDS (worker_status, and the running
job's heartbeat_at), even while the main loop is busy in a long import. A
job with no check-in for WORKER_STALE_SECONDS was cut off (the worker
stopped): an import or an archive job carries on from where it got to (an
import from its last staged chunk, see import_staging), up to MAX_RESUMES
times. A job only waiting
(for the org's lock) is never taken for dead: whoever runs a job holds its
job lock (org_lock.job_running) until it's done.

Ctrl+C stops it once the running job is done. A second Ctrl+C, or closing
its window, stops it at once: what it was running is picked up again at the
next start (each from where it got to).
"""

import logging
import os
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects.postgresql import insert
from app.core.observability import increment_metric, set_metric, alert
from sqlalchemy.orm import Session

from app.api.uploads import upload_path
from app.core.config import check_secret_key, settings
from app.models.archive import ArchiveJob
from app.models.enums import ReportStatus, ScanStatus
from app.models.event import WorkerStatus
from app.models.report import Report
from app.models.evidence_evaluation import EvidenceEvaluation
from app.services import evidence_jobs
from app.models.knowledge import KnowledgeIndex
from app.services import knowledge_service
from app.models.scan import Scan
from app.models.organization import Organization
from app.models.dashboard_snapshot import DashboardSnapshot
from app.services import dashboard_snapshots
from app.services import archive_service, import_staging, ingestion_background, platform, report_service
from app.services.events import purge_expired_events, record_event
from app.services.import_profiles import resolve_profile
from app.services.org_lock import ARCHIVE_JOB, IMPORT_JOB, REPORT_JOB, DOCUMENT_JOB, EVIDENCE_JOB, DASHBOARD_JOB, job_is_running, job_running
from app.services.ingestion_service import IngestionError, detect_format, fail_import, process_import
from app.services.sessions import purge_old_sessions

logger = logging.getLogger("app.worker")

HEARTBEAT_SECONDS = 15
# An import or archive job cut off more often than this is failed, not
# carried on.
MAX_RESUMES = 3
HOUSEKEEPING_EVERY = timedelta(days=1)
FIRST_HOUSEKEEPING_AFTER = timedelta(minutes=1)
REAP_EVERY = timedelta(seconds=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- One job ------------------------------------------------------------------


class _Current:
    """Per-thread jobs, snapshotted together by the heartbeat thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[int, tuple[str, uuid.UUID]] = {}

    def set(self, job: tuple[str, uuid.UUID] | None) -> None:
        with self.lock:
            if job is None:
                self.jobs.pop(threading.get_ident(), None)
            else:
                self.jobs[threading.get_ident()] = job

    def get(self) -> tuple[str, uuid.UUID] | None:
        with self.lock:
            return self.jobs.get(threading.get_ident())

    def all(self) -> list[tuple[str, uuid.UUID]]:
        with self.lock:
            return list(self.jobs.values())


current = _Current()


@contextmanager
def _worker_lease():
    """One healthy pool per database/schema, including serial CLI launches."""
    with ingestion_background.open_session() as db:
        engine = db.get_bind().engine
    with engine.connect() as conn:
        key = conn.scalar(select(func.hashtext(func.current_schema())))
        acquired = conn.scalar(select(func.pg_try_advisory_lock(10, key)))
        conn.commit()
        if not acquired:
            raise RuntimeError("A worker pool is already running for this installation")
        pid = conn.scalar(select(func.pg_backend_pid()))
        conn.commit()
        try:
            from app.models.worker_dispatch import WorkerDispatch
            try:
                conn.execute(select(WorkerDispatch.scope_id).limit(0))
                conn.execute(select(DashboardSnapshot.id).limit(0))
                conn.execute(select(Organization.dashboard_refresh_interval_seconds).limit(0))
                conn.commit()
            except Exception as exc:
                raise RuntimeError("Worker schema is not ready; run alembic upgrade head before starting the pool") from exc
            yield conn, pid
        finally:
            released = False
            try:
                if not conn.invalidated:
                    conn.rollback()
                    conn.execute(select(func.pg_advisory_unlock(10, key)))
                    conn.commit()
                    released = True
            finally:
                if not released:
                    conn.invalidate()


@contextmanager
def _maintenance_guard(db):
    """Only one maintenance/purge runner, even during pool restart overlap."""
    with db.get_bind().engine.connect() as conn:
        key = conn.scalar(select(func.hashtext(func.current_schema())))
        acquired = conn.scalar(select(func.pg_try_advisory_lock(11, key)))
        conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(select(func.pg_advisory_unlock(11, key)))
                conn.commit()




def claim_next(db: Session) -> tuple[str, uuid.UUID] | None:
    """Atomically claim a runnable job, fairly across organization scopes."""
    from app.worker.scheduler import claim
    return claim(db, _now)


def run_once(db: Session, *, allow_org_purge: bool = True) -> bool:
    """Take and run one waiting job; else purge an org whose purge the
    Sysadmin asked for (it's already gone for everyone, so it waits its
    turn). False if there's nothing to do."""
    claimed = claim_next(db)
    if claimed is None:
        if not allow_org_purge:
            return False
        # Preserve serial worker's idle-only purge behavior: do not delete a
        # tenant while another pool slot is still processing any queued job.
        if current.all():
            return False
        try:
            if db.scalar(select(Organization.id).where(Organization.purge_requested_at.is_not(None)).limit(1)) is None:
                db.rollback()
                return False
            # Also cover jobs run by a synchronous API request or a draining
            # predecessor pool. A queued tenant purge waits rather than racing.
            for model in (Scan, ArchiveJob, Report, KnowledgeIndex, EvidenceEvaluation, DashboardSnapshot):
                if db.scalar(select(model.id).where(model.status == "running").limit(1)) is not None:
                    db.rollback()
                    return False
            with _maintenance_guard(db) as acquired:
                return platform.purge_next_org(db) if acquired else False
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
        elif kind == "report":
            with job_running(db, REPORT_JOB, job_id):
                report_service.process_report_job(db, job_id)
        elif kind == "document":
            with job_running(db, DOCUMENT_JOB, job_id):
                knowledge_service.process_index(db, job_id)
        elif kind == "evidence":
            with job_running(db, EVIDENCE_JOB, job_id):
                evidence_jobs.process_job(db, job_id)
        elif kind == "dashboard":
            with job_running(db, DASHBOARD_JOB, job_id):
                dashboard_snapshots.process(db, job_id)
        else:
            archive_service.run_job(db, job_id)
    except Exception:
        # Each runner has recorded its failure (and its event) already.
        if kind in {"report", "document", "evidence", "dashboard"}:
            logger.error("%s job %s failed; see its recorded status", kind, job_id)
        else:
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
    try:
        process_import(
            db,
            scan,
            kind,
            fmt,
            path,  # read a record at a time, never whole
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
    WORKER_STALE_SECONDS): carry on from where they got to (up to
    MAX_RESUMES times), or mark failed. A job that's only waiting (for the org's
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
        if by_worker and scan.retry_count < MAX_RESUMES and saved:
            logger.warning("Import %s (%s) was cut off: carrying on", scan.id, scan.filename)
            scan.status, scan.retry_count, scan.heartbeat_at, scan.progress = (
                ScanStatus.pending,
                scan.retry_count + 1,
                None,
                None,
            )
            db.commit()
            continue
        if not (by_worker and saved):
            upload_path(scan.id).unlink(missing_ok=True)
        if not by_worker:
            message = "Stopped when the server restarted: import it again"
        elif scan.retry_count:
            # Its file is kept: Retry runs it again.
            message = f"Cut off {scan.retry_count + 1} times (the background worker stopped)"
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


    stale_reports = select(Report).where(
        Report.status == ReportStatus.running,
        func.coalesce(Report.heartbeat_at, Report.run_started_at, Report.created_at) < stale,
    ).with_for_update(skip_locked=True)
    for report in db.scalars(stale_reports).all():
        if running_here == ("report", report.id) or job_is_running(db, REPORT_JOB, report.id):
            continue
        if report.cancel_requested_at:
            report.status = ReportStatus.failed
            report.error_message = "Generation cancelled by user"
        elif report.retry_count < MAX_RESUMES:
            report.status = ReportStatus.pending
            report.retry_count += 1
            report.heartbeat_at = None
            report.run_started_at = None
        else:
            report.status = ReportStatus.failed
            report.error_message = "Report generation interrupted too many times; generate a new report"
    for index in db.scalars(select(KnowledgeIndex).where(KnowledgeIndex.status == "running",
            func.coalesce(KnowledgeIndex.heartbeat_at, KnowledgeIndex.run_started_at, KnowledgeIndex.created_at) < stale)
            .with_for_update(skip_locked=True)).all():
        if running_here == ("document", index.id) or job_is_running(db, DOCUMENT_JOB, index.id):
            continue
        if index.retry_count < MAX_RESUMES:
            index.status = "pending"
            index.retry_count += 1
            index.heartbeat_at = None
        else:
            index.status = "failed"
            index.error_message = "Indexing interrupted too many times; retry after checking the worker"
    for evaluation in db.scalars(select(EvidenceEvaluation).where(EvidenceEvaluation.status == "running",
            func.coalesce(EvidenceEvaluation.heartbeat_at, EvidenceEvaluation.run_started_at, EvidenceEvaluation.created_at) < stale)
            .with_for_update(skip_locked=True)).all():
        if running_here == ("evidence", evaluation.id) or job_is_running(db, EVIDENCE_JOB, evaluation.id):
            continue
        evaluation.result = None
        if evaluation.cancel_requested_at is not None:
            evaluation.status, evaluation.completed_at = "cancelled", now
        elif evaluation.retry_count < MAX_RESUMES:
            evaluation.status, evaluation.retry_count = "pending", evaluation.retry_count + 1
            evaluation.heartbeat_at = evaluation.run_started_at = None
            evaluation.progress = None
        else:
            evaluation.status, evaluation.completed_at = "failed", now
            evaluation.error_message = "Evidence evaluation interrupted too many times; retry after checking the worker."
    for dashboard in db.scalars(select(DashboardSnapshot).where(DashboardSnapshot.status == "running",
            func.coalesce(DashboardSnapshot.heartbeat_at, DashboardSnapshot.run_started_at) < stale)
            .with_for_update(skip_locked=True)).all():
        if job_is_running(db, DASHBOARD_JOB, dashboard.id):
            continue
        if dashboard.retry_count < MAX_RESUMES:
            dashboard.status, dashboard.retry_count = "pending", dashboard.retry_count + 1
            dashboard.heartbeat_at = dashboard.run_started_at = None
        else:
            dashboard.status = "failed"
            dashboard.error_message = "Dashboard refresh interrupted too many times; retry after checking the worker."
    db.commit()


# --- Daily housekeeping -------------------------------------------------------


def housekeeping(db: Session) -> None:
    """Purge archived items and Activity events past their retention (each
    recorded in Activity), delete old ended sign-in sessions, and delete
    uploaded files and staging nothing is waiting for."""
    logger.info("Report retention: %d expired report(s) deleted", report_service.purge_expired_reports(db))
    if settings.ARCHIVE_AUTO_PURGE:
        queued = archive_service.purge_expired(db, queue=True)
        logger.info("Auto-purge: %d archived item(s) queued (run when nothing else waits)", queued)
        logger.info("Activity clean-up: %d event(s) deleted", purge_expired_events(db))
    logger.info("Sign-in clean-up: %d old session(s) deleted", purge_old_sessions(db))
    _sweep_uploads(db)
    logger.info("Import staging clean-up: %d leftover row(s) deleted", import_staging.purge_orphans(db))


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


def _check_in(stop: threading.Event, started_at: datetime, lease=None, stop_work=None) -> None:
    """Every HEARTBEAT_SECONDS: the worker's check-in, and the running job's."""
    while not stop.wait(HEARTBEAT_SECONDS):
        if lease is not None:
            try:
                conn, expected_pid = lease
                if conn.scalar(select(func.pg_backend_pid())) != expected_pid:
                    raise RuntimeError("Worker pool leadership connection changed")
                conn.commit()
            except Exception:
                logger.exception("Worker pool leadership lost; stopping new work")
                stop_work.set()
                return
        try:
            with ingestion_background.open_progress_session() as db:
                now = _now()
                db.execute(
                    insert(WorkerStatus)
                    .values(id=1, started_at=started_at, heartbeat_at=now)
                    .on_conflict_do_update(index_elements=["id"], set_={"heartbeat_at": now})
                )
                for job in current.all():
                    if job[0] == "import":
                        model = Scan
                    elif job[0] == "report":
                        model = Report
                    elif job[0] == "document":
                        model = KnowledgeIndex
                    elif job[0] == "evidence":
                        model = EvidenceEvaluation
                    elif job[0] == "dashboard":
                        model = DashboardSnapshot
                    else:
                        model = ArchiveJob
                    db.execute(update(model).where(model.id == job[1]).values(heartbeat_at=now))
                db.commit()

                # ADD THIS: Increment worker heartbeat metric
                increment_metric("worker_heartbeats")

        except Exception:
            logger.warning("Couldn't check in", exc_info=True)


def _update_queue_metrics() -> None:
    # Never reuse the loop's already-closed Session: SQLAlchemy would reopen it
    # and leave this SELECT transaction alive, blocking concurrent index builds.
    with ingestion_background.open_session() as metrics_db:
        pending_imports = metrics_db.scalar(select(func.count(Scan.id)).where(Scan.status == ScanStatus.pending)) or 0
        pending_archives = metrics_db.scalar(select(func.count(ArchiveJob.id)).where(ArchiveJob.status == "pending")) or 0
        pending_reports = metrics_db.scalar(select(func.count(Report.id)).where(Report.status == ReportStatus.pending)) or 0
        pending_evidence = metrics_db.scalar(select(func.count(EvidenceEvaluation.id)).where(EvidenceEvaluation.status == "pending")) or 0
        set_metric("queue_imports_pending", pending_imports)
        set_metric("queue_archives_pending", pending_archives)
        set_metric("queue_reports_pending", pending_reports)
        set_metric("queue_evidence_pending", pending_evidence)
        set_metric("queue_total_pending", pending_imports + pending_archives + pending_reports + pending_evidence)


def _run_loop(stop: threading.Event, *, maintenance: bool = True) -> None:
    next_reap = _now()
    next_housekeeping = _now() + FIRST_HOUSEKEEPING_AFTER
    next_dashboard_refresh = _now()
    last_queue_check = _now()
    failures = 0
    try:
        while not stop.is_set():
            try:
                with ingestion_background.open_session() as db:
                    if maintenance:
                        with _maintenance_guard(db) as acquired:
                            if acquired and _now() >= next_reap:
                                next_reap = _now() + REAP_EVERY
                                reap_stale(db)
                            if acquired and _now() >= next_housekeeping:
                                next_housekeeping = _now() + HOUSEKEEPING_EVERY
                                housekeeping(db)
                            if acquired and _now() >= next_dashboard_refresh:
                                next_dashboard_refresh = _now() + timedelta(seconds=30)
                                dashboard_snapshots.enqueue_due(db)
                    ran = run_once(db) if maintenance else run_once(db, allow_org_purge=False)
                failures = 0
            except Exception:
                # The database restarting, say: wait, then carry on (longer
                # each time it fails again, up to a minute).
                failures += 1
                wait = min(60, 2**failures)
                logger.exception("Worker loop failed; trying again in %d s", wait)
                stop.wait(wait)
                # ADD THIS: Track worker failures
                increment_metric("worker_failures")
                continue
            # ADD THIS: Check queue depth metrics periodically
            if maintenance and _now() >= last_queue_check + timedelta(minutes=1):
                try:
                    _update_queue_metrics()
                except Exception:
                    logger.warning("Failed to check queue depth", exc_info=True)
                last_queue_check = _now()
            if not ran:
                stop.wait(settings.WORKER_POLL_SECONDS)
    finally:
        current.set(None)


def _run_pool(stop: threading.Event) -> None:
    """Bound concurrent I/O jobs; each thread owns its own database Session."""
    with ThreadPoolExecutor(max_workers=settings.WORKER_CONCURRENCY, thread_name_prefix="import-worker") as pool:
        futures = [pool.submit(_run_loop, stop, maintenance=slot == 0) for slot in range(settings.WORKER_CONCURRENCY)]
        try:
            while not stop.wait(0.2):
                for future in futures:
                    if future.done():
                        future.result()
                        raise RuntimeError("Worker slot exited unexpectedly")
        finally:
            stop.set()


def _serve(lease) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    check_secret_key(settings.SECRET_KEY)
    stop = threading.Event()
    started_at = _now()

    def request_stop(signum, frame):
        if stop.is_set():
            if settings.WORKER_CONCURRENCY > 1:
                os._exit(130)  # Explicit second Ctrl+C: terminate all job threads.
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
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(target=_check_in, args=(heartbeat_stop, started_at, lease, stop), daemon=True)
    heartbeat.start()
    logger.info("Background worker pool started with %d slots; uploads wait in %s", settings.WORKER_CONCURRENCY, settings.upload_dir)

    try:
        if settings.WORKER_CONCURRENCY == 1:
            _run_loop(stop)
        else:
            _run_pool(stop)
    finally:
        stop.set()
        heartbeat_stop.set()
        heartbeat.join(timeout=HEARTBEAT_SECONDS + 2)
        with ingestion_background.open_session() as db:
            record_event(db, "worker_stopped", org_id=None)
            db.commit()
        logger.info("Background worker stopped")


def main() -> None:
    # Jobs hold a main transaction and a job lock; progress/checkpoints use short
    # extra sessions. Reserve headroom for heartbeats, leadership and maintenance.
    # Only CLI's default session factory is rebound; isolated fixtures retain theirs.
    worker_engine = None
    from app.db.session import SessionLocal
    previous_bind = SessionLocal.kw["bind"]
    if settings.WORKER_CONCURRENCY > 1 and ingestion_background.open_session is ingestion_background._new_session:
        worker_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, hide_parameters=True,
                                      pool_size=3 * settings.WORKER_CONCURRENCY + 4, max_overflow=0)
        SessionLocal.configure(bind=worker_engine)
    try:
        with _worker_lease() as lease:
            _serve(lease)
    finally:
        if worker_engine is not None:
            SessionLocal.configure(bind=previous_bind)
            worker_engine.dispose()
