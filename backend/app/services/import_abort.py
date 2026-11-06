"""Abort requests are durable; only the publisher can acknowledge rollback."""
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from app.models.scan import Scan


class ImportAborted(Exception):
    pass


def check_abort(db, scan_id):
    if db.scalar(select(Scan.abort_requested_at).where(Scan.id == scan_id)) is not None:
        raise ImportAborted("Import aborted at user request")


def register_publication(db, scan_id):
    pid, started, transaction_started, xid = db.execute(text("SELECT pid,backend_start,xact_start,pg_current_xact_id()::text FROM pg_stat_activity WHERE pid=pg_backend_pid()")).one()
    with Session(db.get_bind().engine) as control:
        check_abort(control, scan_id)
        control.execute(update(Scan).where(Scan.id == scan_id).values(
            publication_pid=pid, publication_backend_start=started,
            publication_xact_start=transaction_started, publication_xid=int(xid) % (1 << 32)))
        control.commit()


def interrupt_publication(db, scan_id):
    # Hold the scan lock through cancellation. The publisher takes this lock
    # before commit/releasing its connection. Fence PID reuse by backend_start.
    # SQLAlchemy key_share=True, read=False means FOR NO KEY UPDATE. Stronger
    # FOR UPDATE would wait on publication's foreign-key KEY SHARE locks.
    scan = db.scalar(select(Scan).where(Scan.id == scan_id).with_for_update(key_share=True).execution_options(populate_existing=True))
    if not scan or scan.status.value != "running" or not scan.abort_requested_at or not scan.publication_pid or scan.publication_xid is None:
        return False
    return bool(db.scalar(text("""SELECT pg_cancel_backend(pid) FROM pg_stat_activity
        WHERE pid=:pid AND backend_start=:started AND datname=current_database()
        AND xact_start=:transaction_started AND backend_xid::text=:xid
        AND pid<>pg_backend_pid() AND state='active'"""),
        {"pid":scan.publication_pid, "started":scan.publication_backend_start,
         "transaction_started":scan.publication_xact_start, "xid":str(scan.publication_xid)}))
