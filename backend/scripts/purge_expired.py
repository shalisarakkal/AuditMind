"""Purge every archived item past its organization's retention
(ARCHIVE_RETENTION_DAYS, or the org's own setting), and Activity events past
theirs (EVENT_RETENTION_DAYS), once. For Task Scheduler or cron when the
background worker's daily run is off (ARCHIVE_AUTO_PURGE=false).

    cd backend
    .venv\Scripts\python scripts\purge_expired.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.archive_service import purge_expired  # noqa: E402
from app.services.events import purge_expired_events  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with SessionLocal() as db:
        purged = purge_expired(db)
        deleted = purge_expired_events(db)
    print(f"Purged {purged} archived item(s) and {deleted} Activity event(s) past retention.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
