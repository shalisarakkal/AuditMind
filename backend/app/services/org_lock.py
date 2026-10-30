"""One lock per organization for everything that changes its assets and
findings in bulk: imports, and archiving, restoring or purging. Plus one per
running job, so the background worker can tell running from dead."""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

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


def org_is_busy(db: Session, org_id: uuid.UUID) -> bool:
    """Whether someone holds the org's lock right now (an import writing its
    rows, an archive job's chunk), checked without waiting: on a connection
    of its own, so the caller's transaction is left as it is."""
    with db.get_bind().connect() as conn:
        free = conn.execute(select(func.pg_try_advisory_lock(_key(org_id)))).scalar()
        if free:
            conn.execute(select(func.pg_advisory_unlock(_key(org_id))))
        conn.commit()
    return not free


def lock_org_jobs(db: Session, org_id: uuid.UUID) -> None:
    """Hold the org's job-start lock until this transaction ends: checking
    that no archive, restore or purge is running on an item and starting one
    happen one request at a time. A lock of its own (Postgres's two-number
    lock keys never clash with the one-number key of lock_org), so starting
    a job never waits for an import."""
    org_key = int.from_bytes(org_id.bytes[:4], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(1, org_key)))


def lock_org_configuration(db: Session, org_id: uuid.UUID) -> None:
    """Serialize configuration read/merge/create, including absent consent rows.

    Separate from import/job locks: configuration must not take them in reverse
    order. Colliding truncated keys only cause extra serialization, not data loss.
    """
    org_key = int.from_bytes(org_id.bytes[:4], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(7, org_key)))


# Job kinds for job_running (the first key of the lock).
IMPORT_JOB = 2
ARCHIVE_JOB = 3
REPORT_JOB = 4
DOCUMENT_JOB = 5
EVIDENCE_JOB = 6
DASHBOARD_JOB = 14


def _job_key(job_id: uuid.UUID) -> int:
    return int.from_bytes(job_id.bytes[:4], "big", signed=True)


@contextmanager
def job_running(db: Session, kind: int, job_id: uuid.UUID) -> Iterator[None]:
    """Say "this job is being run" for as long as it runs: a lock held on a
    connection of its own. If the process running it dies, the connection
    closes and the lock goes with it, so the background worker can tell a
    job that's only waiting (for the org's lock, say) from one nothing runs
    any more (job_is_running)."""
    conn = db.get_bind().connect()
    try:
        conn.execute(select(func.pg_advisory_lock(kind, _job_key(job_id))))
        conn.commit()
        yield
    finally:
        try:
            conn.execute(select(func.pg_advisory_unlock(kind, _job_key(job_id))))
            conn.commit()
        finally:
            conn.close()


def job_is_running(db: Session, kind: int, job_id: uuid.UUID) -> bool:
    """Whether some process holds the job's job_running lock."""
    return not db.execute(select(func.pg_try_advisory_xact_lock(kind, _job_key(job_id)))).scalar()
