"""People: an org's admins add, change and remove its members (PLAN.md,
Phase 2e part 2).

The rules:
- An org always keeps at least one admin, and admins don't change their own
  role or remove themselves (another admin does), so no one locks
  themselves out by mistake.
- A person's name and password belong to their account, shared by all their
  orgs: one org's admins rename or reset only people who belong to that org
  alone; anyone in several orgs is the Sysadmin's (Phase 2e part 3).
- A role change or a removal ends the person's sessions, so every page they
  have open starts again from what they may now do.

Each change is recorded in Activity. Functions here don't commit; the
routes do, once the change and its event are both added.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.services import accounts
from app.services.events import record_event, record_for_platform_and_user_orgs
from app.services.security_policy import effective_policy
from app.services.sessions import end_user_sessions


class PeopleError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- How People shows someone ------------------------------------------------


def status_expression(now: datetime):
    """A person's state, for filtering and sorting in SQL (status_of in Python)."""
    return case(
        (User.is_active.is_(False), "deactivated"),
        (and_(User.locked_at.is_not(None), or_(User.locked_until.is_(None), User.locked_until > now)), "locked"),
        (User.must_change_password.is_(True), "must_change_password"),
        else_="active",
    )


def status_of(user: User, now: datetime) -> str:
    if not user.is_active:
        return "deactivated"
    if user.is_locked(now):
        return "locked"
    if user.must_change_password:
        return "must_change_password"
    return "active"


def in_other_orgs_expression(org_id: uuid.UUID):
    other = aliased(OrgMembership)
    return exists().where(other.user_id == User.id, other.org_id != org_id)


def in_other_orgs(db: Session, user: User, org_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(func.count()).where(OrgMembership.user_id == user.id, OrgMembership.org_id != org_id)
        )
    )


# --- Changes -------------------------------------------------------------------


def _lock_org_members(db: Session, org_id: uuid.UUID) -> None:
    """Changes to one org's members wait for each other (the org's row,
    locked to the end of the transaction), so two admins demoting each
    other at once can't leave the org with none."""
    db.execute(select(Organization.id).where(Organization.id == org_id).with_for_update())


def _admins(db: Session, org_id: uuid.UUID) -> int:
    """Admins who can sign in (a deactivated one can't look after the org)."""
    return db.scalar(
        select(func.count())
        .select_from(OrgMembership)
        .join(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == org_id, OrgMembership.role == UserRole.admin, User.is_active.is_(True))
    )


def orgs_needing(db: Session, user: User) -> list[str]:
    """The orgs where `user` is the only admin who can sign in."""
    admin_of = db.scalars(
        select(OrgMembership).where(OrgMembership.user_id == user.id, OrgMembership.role == UserRole.admin)
    ).all()
    return [m.organization.name for m in admin_of if _admins(db, m.org_id) <= 1]


def _record_in_user_orgs(db: Session, type: str, user: User, actor: User, **fields) -> None:
    """An event about an account (its name, a lock), shown in each of its
    orgs, so each one's admins see it."""
    org_ids = db.scalars(select(OrgMembership.org_id).where(OrgMembership.user_id == user.id)).all()
    for org_id in org_ids:
        record_event(db, type, org_id=org_id, actor=actor, item=user.email, **fields)


def get_member(db: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> OrgMembership:
    membership = db.get(OrgMembership, (user_id, org_id))
    if membership is None:
        raise PeopleError(404, "not_member", "No such member in this organization")
    return membership


def _not_yourself(membership: OrgMembership, actor: User, what: str) -> None:
    if membership.user_id == actor.id:
        raise PeopleError(400, "yourself", f"You can't {what} yourself. Ask another admin of this organization.")


def _keeps_an_admin(db: Session, membership: OrgMembership) -> None:
    if membership.role == UserRole.admin and membership.user.is_active and _admins(db, membership.org_id) <= 1:
        raise PeopleError(409, "last_admin", "An organization must keep at least one admin.")


def _alone_in_org(db: Session, membership: OrgMembership, what: str) -> None:
    if in_other_orgs(db, membership.user, membership.org_id):
        raise PeopleError(
            403,
            "other_orgs",
            f"{membership.user.email} also belongs to other organizations, so only the Sysadmin can {what}.",
        )


def add_member(
    db: Session, org_id: uuid.UUID, actor: User, *, email: str, name: str | None, role: UserRole
) -> tuple[OrgMembership, str | None]:
    """Add `email` to the org. A new account gets a temporary password
    (returned, to show the admin once); an existing one keeps its own
    password and name. Raises PeopleError."""
    _lock_org_members(db, org_id)
    user = db.scalar(select(User).where(User.email == email))
    temporary = None
    created = user is None
    if not created:
        if user.is_sysadmin:
            raise PeopleError(409, "sysadmin", "That's the Sysadmin's account, which belongs to no organization.")
        if db.get(OrgMembership, (user.id, org_id)) is not None:
            raise PeopleError(409, "already_member", f"{email} is already a member of this organization.")
    else:
        user = User(email=email, name=name, hashed_password=None)
        db.add(user)
        db.flush()
    membership = OrgMembership(user_id=user.id, org_id=org_id, role=role)
    db.add(membership)
    db.flush()
    if created:
        # After the membership, so the password meets this org's rule.
        temporary = accounts.generate_temporary_password(effective_policy(db, user))
        accounts.set_password(db, user, temporary, temporary=True)
    record_event(
        db,
        "member_added",
        org_id=org_id,
        actor=actor,
        item=email,
        details={"role": role.value, **({"new_account": True} if temporary else {})},
    )
    return membership, temporary


def change_role(db: Session, membership: OrgMembership, actor: User, role: UserRole) -> None:
    if role == membership.role:
        return
    _not_yourself(membership, actor, "change the role of")
    _lock_org_members(db, membership.org_id)
    db.refresh(membership)
    if role != UserRole.admin:
        _keeps_an_admin(db, membership)
    before = membership.role
    membership.role = role
    end_user_sessions(db, membership.user_id, "role_changed")
    record_event(
        db,
        "role_changed",
        org_id=membership.org_id,
        actor=actor,
        item=membership.user.email,
        details={"from": before.value, "to": role.value},
    )


def rename(db: Session, user: User, actor: User, name: str) -> None:
    """Set `user`'s name (their own change, or an admin's or the Sysadmin's:
    the caller checks which may); recorded in each of their orgs with the
    old and new names (and in Platform activity, by the Sysadmin)."""
    if name == user.name:
        return
    before = user.name
    user.name = name
    record = record_for_platform_and_user_orgs if actor.is_sysadmin else _record_in_user_orgs
    record(db, "name_changed", user, actor, details={"from": before, "to": name})


def rename_member(db: Session, membership: OrgMembership, actor: User, name: str) -> None:
    if membership.user_id != actor.id:
        _alone_in_org(db, membership, "change their name")
    rename(db, membership.user, actor, name)


def remove_member(db: Session, membership: OrgMembership, actor: User) -> None:
    """Take away their access to this org; the account stays (they may be
    added again, or belong to other orgs)."""
    _not_yourself(membership, actor, "remove")
    _lock_org_members(db, membership.org_id)
    db.refresh(membership)
    _keeps_an_admin(db, membership)
    user, org_id, role = membership.user, membership.org_id, membership.role
    db.delete(membership)
    end_user_sessions(db, user.id, "removed")
    record_event(db, "member_removed", org_id=org_id, actor=actor, item=user.email, details={"role": role.value})


def reset_password(db: Session, membership: OrgMembership, actor: User) -> tuple[str, datetime]:
    """A new temporary password (returned to show the admin once); ends the
    person's sessions and clears a lock."""
    _not_yourself(membership, actor, "reset the password of")
    _alone_in_org(db, membership, "reset their password")
    user = membership.user
    db.refresh(user, with_for_update=True)
    password = accounts.set_temporary_password(db, user)
    record_event(db, "password_reset", org_id=membership.org_id, actor=actor, item=user.email)
    return password, user.temp_password_expires_at


def unlock_member(db: Session, membership: OrgMembership, actor: User) -> None:
    """Any admin of one of the person's orgs may unlock them (the lock is
    on the account)."""
    user = membership.user
    db.refresh(user, with_for_update=True)
    if not user.is_locked(_now()):
        raise PeopleError(409, "not_locked", f"{user.email} isn't locked.")
    accounts.unlock(user)
    _record_in_user_orgs(db, "account_unlocked", user, actor)
