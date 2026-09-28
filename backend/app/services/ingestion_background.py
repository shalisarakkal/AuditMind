"""Runs large file imports after the response has been sent (FastAPI
BackgroundTasks, in-process). The request's DB session is closed by then, so
the job opens its own.

If the server restarts mid-import, that scan stays "running": fine for the MVP;
a real task queue is a later hardening step.
"""

import logging
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.scan import Scan
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


def run_import_job(
    scan_id: uuid.UUID, kind: ImportKind, fmt: str, content: bytes, profile: RowReader | None = None
) -> None:
    with open_session() as db:
        scan = db.get(Scan, scan_id)
        if scan is None:
            logger.error("Background import: scan %s not found", scan_id)
            return
        try:
            process_import(db, scan, kind, fmt, content, profile)
        except Exception:
            # process_import has already marked the scan failed.
            logger.exception("Background import failed (scan %s)", scan_id)
