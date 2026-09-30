"""The app's own daily auto-purge (ARCHIVE_AUTO_PURGE), started with the
app (main.py). With several server processes, turn it off and run
scripts/purge_expired.py from Task Scheduler or cron instead."""

import asyncio
import logging

from app.db.session import SessionLocal
from app.services import archive_service

logger = logging.getLogger(__name__)

FIRST_RUN_DELAY_SECONDS = 60
INTERVAL_SECONDS = 24 * 60 * 60


def fail_interrupted_jobs() -> None:
    """Archive jobs still marked running when the app starts were cut off by
    the restart; mark them failed so they can be started again."""
    try:
        with SessionLocal() as db:
            if count := archive_service.fail_interrupted_jobs(db):
                logger.warning("Marked %d interrupted archive job(s) failed", count)
    except Exception:
        logger.exception("Couldn't check for interrupted archive jobs")


def purge_expired() -> None:
    try:
        with SessionLocal() as db:
            purged = archive_service.purge_expired(db)
        logger.info("Auto-purge: %d archived item(s) past retention purged", purged)
    except Exception:
        logger.exception("Auto-purge failed; it runs again tomorrow")


async def auto_purge_loop() -> None:
    """Shortly after startup, then once a day."""
    await asyncio.sleep(FIRST_RUN_DELAY_SECONDS)
    while True:
        await asyncio.to_thread(purge_expired)
        await asyncio.sleep(INTERVAL_SECONDS)
