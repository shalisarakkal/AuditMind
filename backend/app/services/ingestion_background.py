"""Database sessions for work done outside a request (the background
worker, app/worker), and import progress, written in its own short sessions
so it shows while the import's transaction is still open.
"""

import logging
import uuid
from datetime import datetime, timezone
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.scan import Scan

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
                .values(progress={"phase": phase, "rows_done": rows_done, "rows_total": rows_total,
                                  "updated_at": datetime.now(timezone.utc).isoformat()})
            )
            db.commit()
    except Exception:
        logger.warning("Couldn't record progress for scan %s", scan_id, exc_info=True)
