"""One lock per organization for everything that changes its assets and
findings in bulk: imports, and archiving, restoring or purging."""

import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _key(org_id: uuid.UUID) -> int:
    return int.from_bytes(org_id.bytes[:8], "big", signed=True)


def lock_org(db: Session, org_id: uuid.UUID, on_wait: Callable[[], object] | None = None) -> None:
    """Hold the org's lock until this transaction ends. Import matching is
    look-up-then-insert, so two overlapping imports (say, a background one
    and an upload) could otherwise both create the same host, and an import
    could match an asset that's being archived. A lock rather than a unique
    index, because the "duplicate" asset strategy allows repeats. `on_wait`
    is called first if someone else holds the lock."""
    key = _key(org_id)
    if db.execute(select(func.pg_try_advisory_xact_lock(key))).scalar():
        return
    if on_wait is not None:
        on_wait()
    db.execute(select(func.pg_advisory_xact_lock(key)))


def lock_org_jobs(db: Session, org_id: uuid.UUID) -> None:
    """Hold the org's job-start lock until this transaction ends: checking
    that no archive, restore or purge is running on an item and starting one
    happen one request at a time. A lock of its own (Postgres's two-number
    lock keys never clash with the one-number key of lock_org), so starting
    a job never waits for an import."""
    org_key = int.from_bytes(org_id.bytes[:4], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(1, org_key)))
