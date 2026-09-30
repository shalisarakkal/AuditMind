"""Runs large file imports, and large archive, restore and purge jobs, after
the response has been sent (FastAPI BackgroundTasks, in-process). The
request's DB session is closed by then, so the job opens its own.

If the server restarts mid-import, that scan stays "running": fine for the MVP;
a real task queue is a later hardening step.
"""

import logging
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.scan import Scan
from app.services import archive_service
from app.services.ingestion_service import ImportKind, RowReader, process_import

logger = logging.getLogger(__name__)


@contextmanager
def _new_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Test seam, in the spirit of app.dependency_overrides[get_db]: tests point
# this at their own session so background imports land in the test database
# (SessionLocal is bound to the dev DATABASE_URL). See tests/conftest.py.
open_session: Callable[[], AbstractContextManager[Session]] = _new_session
# Progress goes through its own short sessions, committed at once, so it's
# visible while the import's own transaction is still open. Tests point this
# at a second session on their database.
open_progress_session: Callable[[], AbstractContextManager[Session]] = _new_session


def write_progress(scan_id: uuid.UUID, phase: str, rows_done: int, rows_total: int) -> None:
    """Record a running import's progress on its scan. Progress is only for
    display: if it can't be saved, the import carries on regardless."""
    try:
        with open_progress_session() as db:
            db.execute(
                update(Scan)
                .where(Scan.id == scan_id)
                .values(progress={"phase": phase, "rows_done": rows_done, "rows_total": rows_total})
            )
            db.commit()
    except Exception:
        logger.warning("Couldn't record progress for scan %s", scan_id, exc_info=True)


def run_import_job(
    scan_id: uuid.UUID, kind: ImportKind, fmt: str, content: bytes, profile: RowReader | None = None
) -> None:
    with open_session() as db:
        scan = db.get(Scan, scan_id)
        if scan is None:
            logger.error("Background import: scan %s not found", scan_id)
            return
        try:
            process_import(
                db, scan, kind, fmt, content, profile, progress=lambda phase, done, total: write_progress(scan_id, phase, done, total)
            )
        except Exception:
            # process_import has already marked the scan failed.
            logger.exception("Background import failed (scan %s)", scan_id)


def run_archive_job(job_id: uuid.UUID) -> None:
    """A large archive, restore or purge (see archive_service.run_job, which
    records its own failures)."""
    with open_session() as db:
        archive_service.run_job(db, job_id)
