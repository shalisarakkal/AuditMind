"""Activity: recording what happened (models/event.py), and clearing old
events.

record_event adds the event to the caller's session without committing, so
it's saved in the same transaction as the change it describes: an import
that's rolled back leaves no "imported" event behind. Long actions (imports,
archive jobs) record one event when they end, with their start time.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import Criticality
from app.models.event import Event
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.services.org_settings import resolve_ingestion_settings

logger = logging.getLogger(__name__)

SYSTEM = "System"
# Who tried to sign in as someone and failed.
UNKNOWN = "Unknown"

# Event types (Event.type), and the criticality each has unless something
# about the event changes it (a failure, failed rows, duplicates purged).
TYPES: dict[str, Criticality] = {
    "import": Criticality.info,
    "repeat_upload": Criticality.warning,
    "upload_skipped": Criticality.info,
    "archive": Criticality.info,
    "restore": Criticality.info,
    "purge": Criticality.critical,
    "asset_added": Criticality.info,
    "finding_added": Criticality.info,
    "finding_workflow_changed": Criticality.info,
    "settings_changed": Criticality.info,
    "profile_created": Criticality.info,
    "profile_updated": Criticality.info,
    "profile_deleted": Criticality.info,
    "member_added": Criticality.info,
    "member_removed": Criticality.info,
    "role_changed": Criticality.info,
    "name_changed": Criticality.info,
    "password_reset": Criticality.info,
    "account_unlocked": Criticality.info,
    # Reports (Phase 3).
    "report_queued": Criticality.info,
    "report_generated": Criticality.info,
    "report_test_generated": Criticality.info,
    "report_failed": Criticality.warning,
    "report_cancelled": Criticality.info,
    "report_deleted": Criticality.warning,
    # Knowledge sources and report/embedding approvals (Phase 3).
    "document_uploaded": Criticality.info,
    "document_index_queued": Criticality.info,
    "document_reactivation_queued": Criticality.info,
    "document_retired": Criticality.warning,
    "document_removed": Criticality.critical,
    "knowledge_consent_changed": Criticality.warning,
    "shared_standards_queued": Criticality.info,
    "embedding_profile_changed": Criticality.info,
    # The Sysadmin's (Phase 2e part 3).

    "org_created": Criticality.info,
    "org_archived": Criticality.warning,
    "org_restored": Criticality.info,
    "org_purged": Criticality.critical,
    "user_deactivated": Criticality.warning,
    "user_reactivated": Criticality.info,
    "email_changed": Criticality.warning,
    "sysadmin_created": Criticality.warning,
    "registered": Criticality.info,
    "login": Criticality.info,
    "login_failed": Criticality.warning,
    "logout": Criticality.info,
    "password_changed": Criticality.info,
    "account_locked": Criticality.warning,
    "event_cleanup": Criticality.info,
    "worker_started": Criticality.info,
    "worker_stopped": Criticality.info,
}


# Events of the whole system (no org) that every org's Activity shows too:
# the background worker runs everyone's uploads. Other events with no org
# are the platform's (the Sysadmin's Platform activity), not shown to orgs.
SHARED_SYSTEM_TYPES = ("worker_started", "worker_stopped")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def actor_label(user: User | None) -> str:
    return (user.name or user.email) if user else SYSTEM


def record_event(
    db: Session,
    type: str,
    *,
    org_id: uuid.UUID | None,
    actor: User | None = None,
    item: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    outcome: str = "completed",
    criticality: Criticality | None = None,
    counts: dict | None = None,
    details: dict | None = None,
) -> Event:
    """Add an event to `db` (not committed: it's saved with the caller's
    change). `criticality` defaults to the type's (TYPES), raised to Warning
    if the action failed or stopped."""
    if type not in TYPES:
        raise ValueError(f"Unknown event type {type!r}")
    if criticality is None:
        criticality = TYPES[type]
        if outcome != "completed" and criticality == Criticality.info:
            criticality = Criticality.warning
    now = _now()
    event = Event(
        org_id=org_id,
        type=type,
        item=item[:255] if item else None,
        actor_id=actor.id if actor else None,
        actor_label=actor_label(actor)[:255],
        started_at=started_at or ended_at or now,
        ended_at=ended_at or now,
        outcome=outcome,
        criticality=criticality,
        counts=counts or None,
        details=details or None,
    )
    db.add(event)
    return event


def record_for_platform_and_user_orgs(db: Session, type: str, user: User, actor: User, **fields) -> None:
    """An action on an account (the Sysadmin's): in Platform activity, and
    in each of the account's orgs, so their admins see it."""
    record_event(db, type, org_id=None, actor=actor, item=user.email, **fields)
    org_ids = db.scalars(select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)).all()
    for org_id in org_ids:
        record_event(db, type, org_id=org_id, actor=actor, item=user.email, **fields)


def record_for_user_orgs(db: Session, type: str, user: User, *, by_user: bool = True, **fields) -> None:
    """A sign-in event, which belongs to no one org: recorded in each org
    the user is a member of, so each one's admins see it. by_user=False
    (a failed login): the account is what it's about, not who did it."""
    org_ids = db.scalars(select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)).all()
    for org_id in org_ids:
        event = record_event(db, type, org_id=org_id, actor=user if by_user else None, **fields)
        if not by_user:
            event.actor_label = UNKNOWN


def purge_expired_events(db: Session, now: datetime | None = None) -> int:
    """Delete events past each org's retention (EVENT_RETENTION_DAYS or its
    own setting), then apply the safety net; returns how many were deleted.
    Each org that lost events gets an event saying how many. Run daily by
    the background worker."""
    now = now or _now()
    total = 0
    for org in db.scalars(select(Organization)).all():
        cutoff = now - timedelta(days=resolve_ingestion_settings(org).event_retention_days)
        expired = db.execute(delete(Event).where(Event.org_id == org.id, Event.started_at < cutoff)).rowcount
        trimmed = _safety_net(db, org.id)
        if expired or trimmed:
            record_event(
                db,
                "event_cleanup",
                org_id=org.id,
                # Trimming Info events early is what admins are warned about.
                criticality=Criticality.warning if trimmed else Criticality.info,
                counts={k: v for k, v in {"expired": expired, "trimmed": trimmed}.items() if v},
                details={"older_than": cutoff.isoformat()} if expired else None,
            )
        db.commit()
        total += expired + trimmed
    # Events of the whole system (no org), by the default retention.
    cutoff = now - timedelta(days=settings.EVENT_RETENTION_DAYS)
    total += db.execute(delete(Event).where(Event.org_id.is_(None), Event.started_at < cutoff)).rowcount
    db.commit()
    return total


def _safety_net(db: Session, org_id: uuid.UUID) -> int:
    """Over EVENT_SAFETY_NET_ROWS events: delete the oldest Info events, then
    the oldest failed sign-ins (the usual flood: thousands of password
    guesses, which add nothing after the first few thousand), down to the
    limit. Other Warning events and Critical ones are never deleted early,
    so a flood can't push real history out."""
    count = db.scalar(select(func.count()).select_from(Event).where(Event.org_id == org_id))
    excess = count - settings.EVENT_SAFETY_NET_ROWS
    trimmed = 0
    for which in (Event.criticality == Criticality.info, Event.type == "login_failed"):
        if excess - trimmed <= 0:
            break
        oldest = select(Event.id).where(Event.org_id == org_id, which).order_by(Event.started_at).limit(excess - trimmed)
        trimmed += db.execute(delete(Event).where(Event.id.in_(oldest))).rowcount
    if trimmed:
        logger.warning("Org %s had %d events; deleted the %d oldest Info events and failed sign-ins", org_id, count, trimmed)
    return trimmed
