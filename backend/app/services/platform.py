"""The Sysadmin's work (PLAN.md, Phase 2e part 3): organizations (create,
archive, restore, purge) and, in an emergency, accounts (rename, change the
email, reset the password, unlock, deactivate, change a role).

The Sysadmin never changes an org's data: it reads every org, read-only
(api/deps.py). Each action is recorded in Platform activity (events with no
org), and in the orgs it concerns, so their admins see it. Functions here
don't commit, except the worker's purge, which works in chunks.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.archive import ArchiveJob
from app.models.enums import ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services import accounts, people
from app.services.events import record_event, record_for_platform_and_user_orgs
from app.services.people import PeopleError
from app.services.security_policy import effective_policy
from app.services.sessions import end_user_sessions

logger = logging.getLogger(__name__)

# Rows deleted per statement when purging an org.
PURGE_CHUNK = 10_000
# What purging an org deletes, in order (each table's rows of the org; what
# hangs off them goes with them: asset_scans with assets and scans). The
# archive records go after the rows that point at them, which would
# otherwise each be updated to point at nothing first.
PURGE_TABLES = (
    "findings",
    "risk_scores",
    "reports",
    "documents",
    "assets",
    "scans",
    "archive_jobs",
    "archive_batches",
    "import_profiles",
    "events",
    "org_memberships",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _org_event(db: Session, type: str, org: Organization, actor: User | None, **fields) -> None:
    """In the org's Activity and in Platform activity."""
    for org_id in (org.id, None):
        record_event(db, type, org_id=org_id, actor=actor, item=org.name, **fields)


def create_sysadmin(db: Session, email: str, name: str | None) -> str:
    """A Sysadmin account (scripts/create_sysadmin.py, never the website):
    one of its own, in no org. Returns its temporary password, to be
    changed at the first sign-in. Raises PeopleError if the email is taken."""
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise PeopleError(
            409, "email_taken", f"{email} already has an account. The Sysadmin needs an account of its own."
        )
    user = User(email=email, name=name, is_sysadmin=True)
    db.add(user)
    db.flush()
    password = accounts.generate_temporary_password(effective_policy(db, user))
    accounts.set_password(db, user, password, temporary=True)
    record_event(db, "sysadmin_created", org_id=None, item=email)
    return password


# --- Organizations -------------------------------------------------------------


def create_org(
    db: Session,
    actor: User,
    *,
    name: str,
    industry: str | None,
    size: str | None,
    admin_email: str,
    admin_name: str | None,
) -> tuple[Organization, OrgMembership, str | None]:
    """A new org with its first admin (a new account gets a temporary
    password, returned to show once; an existing one keeps its own)."""
    org = Organization(name=name, industry=industry, size=size)
    db.add(org)
    db.flush()
    _org_event(db, "org_created", org, actor, details={"admin": admin_email})
    membership, temporary = people.add_member(
        db, org.id, actor, email=admin_email, name=admin_name, role=UserRole.admin
    )
    return org, membership, temporary


def running_jobs(db: Session, org_id: uuid.UUID) -> int:
    active = (ScanStatus.pending, ScanStatus.running)
    scans = db.scalars(select(Scan.id).where(Scan.org_id == org_id, Scan.status.in_(active))).all()
    jobs = db.scalars(select(ArchiveJob.id).where(ArchiveJob.org_id == org_id, ArchiveJob.status.in_(active))).all()
    return len(scans) + len(jobs)


def _lock(db: Session, org: Organization) -> None:
    db.refresh(org, with_for_update=True)
    if org.purge_requested_at is not None:
        raise PeopleError(409, "purging", f"{org.name} is being purged.")


def archive_org(db: Session, org: Organization, actor: User) -> None:
    """Read-only for everyone until restored. Refused while uploads or
    archive jobs are waiting or running."""
    _lock(db, org)
    if org.archived_at is not None:
        raise PeopleError(409, "already_archived", f"{org.name} is already archived.")
    busy = running_jobs(db, org.id)
    if busy:
        raise PeopleError(
            409,
            "jobs_running",
            f"{org.name} has {busy} upload{'s' if busy != 1 else ''} or archive job{'s' if busy != 1 else ''} "
            "waiting or running. Archive it when they've finished.",
        )
    org.archived_at, org.archived_by = _now(), actor.id
    _org_event(db, "org_archived", org, actor)


def restore_org(db: Session, org: Organization, actor: User) -> None:
    _lock(db, org)
    if org.archived_at is None:
        raise PeopleError(409, "not_archived", f"{org.name} isn't archived.")
    org.archived_at = org.archived_by = None
    _org_event(db, "org_restored", org, actor)


def request_purge(db: Session, org: Organization, actor: User, confirm_name: str) -> None:
    """Delete the org and everything in it, for good (the background worker
    does it). Only an archived org, and only after typing its name."""
    _lock(db, org)
    if org.archived_at is None:
        raise PeopleError(409, "not_archived", "Archive the organization first; only an archived one can be purged.")
    if confirm_name.strip() != org.name:
        raise PeopleError(400, "name_mismatch", f"Type the organization's name exactly ({org.name}) to purge it.")
    org.purge_requested_at, org.purge_requested_by = _now(), actor.id


def purge_next_org(db: Session) -> bool:
    """For the background worker: purge one org whose purge was asked for,
    a chunk at a time (each committed, so a purge cut off carries on next
    time). Returns whether there was one."""
    org = db.scalar(
        select(Organization)
        .where(Organization.purge_requested_at.is_not(None))
        .order_by(Organization.purge_requested_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if org is None:
        db.rollback()
        return False
    org_id, name, asked_at = org.id, org.name, org.purge_requested_at
    actor = db.get(User, org.purge_requested_by) if org.purge_requested_by else None
    db.commit()
    counts: dict[str, int] = {}
    for table in PURGE_TABLES:
        sql = text(
            f"DELETE FROM {table} WHERE ctid IN (SELECT ctid FROM {table} WHERE org_id = :org LIMIT {PURGE_CHUNK})"
        )
        while True:
            deleted = db.execute(sql, {"org": org_id}).rowcount
            db.commit()
            if not deleted:
                break
            counts[table] = counts.get(table, 0) + deleted
    db.execute(text("DELETE FROM organizations WHERE id = :org"), {"org": org_id})
    record_event(
        db,
        "org_purged",
        org_id=None,
        actor=actor,
        item=name,
        started_at=asked_at,
        counts={k: v for k, v in counts.items() if k in ("assets", "findings", "scans", "events", "org_memberships")},
    )
    db.commit()
    logger.info("Purged organization %s (%s): %s", name, org_id, counts)
    return True


# --- Accounts ----------------------------------------------------------------


def _not_the_sysadmin(user: User, actor: User, what: str) -> None:
    if user.id == actor.id:
        raise PeopleError(400, "yourself", f"You can't {what} your own account here.")
    if user.is_sysadmin:
        raise PeopleError(400, "sysadmin", f"You can't {what} the Sysadmin's account.")


def set_active(db: Session, user: User, actor: User, active: bool) -> None:
    """Deactivate (can't sign in; sessions end) or reactivate an account. An
    org's only admin who can sign in can't be deactivated."""
    if user.is_active == active:
        return
    _not_the_sysadmin(user, actor, "deactivate" if not active else "reactivate")
    if not active:
        alone = people.orgs_needing(db, user)
        if alone:
            raise PeopleError(
                409,
                "last_admin",
                f"{user.email} is the only admin of {', '.join(alone)}. Make someone else admin there first.",
            )
        end_user_sessions(db, user.id, "deactivated")
    user.is_active = active
    record_for_platform_and_user_orgs(db, "user_reactivated" if active else "user_deactivated", user, actor)


def change_email(db: Session, user: User, actor: User, email: str) -> None:
    """Until email confirmation exists, only the Sysadmin changes an email
    (the sign-in), e.g. when someone's address changes."""
    if email == user.email:
        return
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise PeopleError(409, "email_taken", f"{email} already has an account.")
    before = user.email
    user.email = email
    record_for_platform_and_user_orgs(db, "email_changed", user, actor, details={"from": before, "to": email})


def reset_password(db: Session, user: User, actor: User) -> str:
    _not_the_sysadmin(user, actor, "reset the password of")
    db.refresh(user, with_for_update=True)
    password = accounts.set_temporary_password(db, user)
    record_for_platform_and_user_orgs(db, "password_reset", user, actor)
    return password


def unlock(db: Session, user: User, actor: User) -> None:
    db.refresh(user, with_for_update=True)
    if not user.is_locked(_now()):
        raise PeopleError(409, "not_locked", f"{user.email} isn't locked.")
    accounts.unlock(user)
    record_for_platform_and_user_orgs(db, "account_unlocked", user, actor)
