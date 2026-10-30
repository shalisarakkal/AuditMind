"""Durable, coalesced Dashboard refreshes; qualification is never cached."""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, case, cast, Integer
from sqlalchemy.orm import Session
from app.models.dashboard_snapshot import DashboardSnapshot
from app.models.organization import Organization
from app.models.session import PlatformSetting
from app.schemas.dashboard import DashboardSettings, DashboardPending, SecuritySummary
from app.services import evidence_jobs

logger = logging.getLogger(__name__)
SETTINGS_KEY = "dashboard_snapshots"


def now():
    return datetime.now(timezone.utc)


def configuration(db):
    row = db.get(PlatformSetting, SETTINGS_KEY, populate_existing=True)
    return DashboardSettings.model_validate(row.value if row else {})


def effective_interval(org, config):
    return org.dashboard_refresh_interval_seconds or config.refresh_interval_seconds


def stagger_seconds(org_id, interval):
    # Stable across processes/restarts. Spread by up to 10%, capped at 5 minutes;
    # never schedule sooner than the configured minimum interval.
    return int.from_bytes(org_id.bytes[:2], "big") % (min(300, interval // 10) + 1)


def refresh_due_at(org_id, last, interval):
    return last + timedelta(seconds=interval + stagger_seconds(org_id, interval))


def enqueue(db, org_id, *, scheduled_at=None):
    # Fences absent rows as well as existing requests. No inventory scan/lock.
    db.execute(select(func.pg_advisory_xact_lock(12, int.from_bytes(org_id.bytes[:4], "big", signed=True))))
    org = db.scalar(select(Organization).where(Organization.id == org_id).with_for_update(read=True))
    if org is None or org.archived_at is not None or org.purge_requested_at is not None:
        db.rollback()
        return None
    row = db.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id == org_id).with_for_update())
    if scheduled_at is not None:
        config = configuration(db)
        if not config.enabled:
            db.commit()
            return row
    if row is not None and scheduled_at is not None:
        last = row.requested_at if row.status == "failed" else (row.generated_at or row.requested_at)
        if refresh_due_at(org_id, last, effective_interval(org, config)) > scheduled_at:
            db.commit()
            return row  # Another user already regenerated it after scheduling.
    if row is None:
        row = DashboardSnapshot(org_id=org_id, requested_at=now(), status="pending")
        db.add(row)
    elif row.status not in ("pending", "running"):
        row.status, row.requested_at, row.retry_count = "pending", now(), 0
        row.heartbeat_at = row.run_started_at = None
        row.error_message = None
    db.commit()
    return row


def read(db, org_id):
    row = db.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id == org_id))
    if row is None:
        if enqueue(db, org_id) is None:
            return DashboardPending(snapshot_refresh_status="failed", snapshot_error="Organization is archived or being deleted. Restore it before refreshing.")
    engine = db.get_bind()
    db.rollback()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            row = snapshot.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id == org_id))
            if not row.payload:
                return DashboardPending(snapshot_refresh_status=row.status, snapshot_error=row.error_message)
            from app.api.routes.dashboard import build_dashboard
            result = build_dashboard(org_id, snapshot, row.payload["inventory"], row.captured_revision)
            result.snapshot_generated_at = row.generated_at
            result.snapshot_refresh_status = row.status
            result.snapshot_error = row.error_message
            config = configuration(snapshot)
            org = snapshot.get(Organization, org_id)
            result.snapshot_stale = (row.captured_revision != result.evidence_revision
                or refresh_due_at(org_id, row.generated_at, effective_interval(org, config)) <= now())
            result.security_summary = SecuritySummary.model_validate(row.payload["security"]).model_copy(update={"snapshot_generated_at": row.generated_at})
            return result


def enqueue_due(db, instant=None):
    config = configuration(db)
    if not config.enabled:
        return 0
    instant = instant or now()
    missing = db.scalars(select(Organization.id).outerjoin(DashboardSnapshot, DashboardSnapshot.org_id == Organization.id)
        .where(DashboardSnapshot.id.is_(None), Organization.purge_requested_at.is_(None), Organization.archived_at.is_(None))
        .order_by(Organization.created_at, Organization.id).limit(100)).all()
    last = case((DashboardSnapshot.status == "failed", DashboardSnapshot.requested_at),
                else_=func.coalesce(DashboardSnapshot.generated_at, DashboardSnapshot.requested_at))
    interval = func.coalesce(Organization.dashboard_refresh_interval_seconds, config.refresh_interval_seconds)
    seed = func.get_byte(func.uuid_send(Organization.id), 0) * 256 + func.get_byte(func.uuid_send(Organization.id), 1)
    spread = seed % (func.least(300, cast(func.floor(interval / 10), Integer)) + 1)
    due = last + func.make_interval(0, 0, 0, 0, 0, 0, interval + spread)
    orgs = db.scalars(select(DashboardSnapshot.org_id).join(Organization, Organization.id == DashboardSnapshot.org_id)
        .where(DashboardSnapshot.status.in_(("completed", "failed")), Organization.purge_requested_at.is_(None), Organization.archived_at.is_(None),
               due <= instant)
        .order_by(due, DashboardSnapshot.id).limit(100)).all()
    db.rollback()
    queued = 0
    for org_id in missing:
        row = enqueue(db, org_id, scheduled_at=instant)
        queued += bool(row and row.status == "pending")
    for org_id in orgs:
        row = enqueue(db, org_id, scheduled_at=instant)
        queued += bool(row and row.status == "pending")
    return queued


def process(db, job_id):
    row = db.get(DashboardSnapshot, job_id)
    org_id = row.org_id
    engine = db.get_bind()
    db.rollback()
    try:
        # Counts, source cards, security window and captured revision agree.
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with Session(bind=connection) as snapshot:
                from app.api.routes.dashboard import capture_inventory, build_security_summary
                revision = evidence_jobs.revision(snapshot, org_id)
                payload = {"inventory": capture_inventory(org_id, snapshot),
                           "security": build_security_summary(org_id, snapshot).model_dump(mode="json")}
                generated = now()
        # Publish all cards atomically; retain old payload until this succeeds.
        row = db.get(DashboardSnapshot, job_id, populate_existing=True)
        row.payload, row.captured_revision, row.generated_at = payload, revision, generated
        row.status, row.error_message = "completed", None
        db.commit()
    except Exception:
        db.rollback()
        row = db.get(DashboardSnapshot, job_id, populate_existing=True)
        if row is not None:
            row.status = "failed"
            row.requested_at = now()  # Bound periodic retry pressure after failure.
            row.error_message = "Dashboard refresh failed. The previous snapshot is retained; retry after checking the worker."
            db.commit()
        logger.exception("Dashboard refresh failed")
        raise
