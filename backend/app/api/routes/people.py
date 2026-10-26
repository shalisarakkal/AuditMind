"""People: an org's members. Every member can see the list; admins add,
change and remove people (services/people.py has the rules)."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import (
    DateRange,
    PageParams,
    SortOrder,
    any_of,
    contains,
    date_range,
    labelled,
    one_of,
    ordered,
    page_params,
)
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.user import User
from app.schemas.paging import Page
from app.schemas.user import MemberAdd, MemberAdded, MemberFacets, MemberRead, MemberUpdate, PasswordReset
from app.services import people
from app.services.people import PeopleError

router = APIRouter(prefix="/orgs/{org_id}/members", tags=["people"])

admin_only = require_org_role(UserRole.admin)

# As People shows them (frontend/src/lib/people.ts), so the search box finds
# what's on screen.
_STATUS_LABELS = {
    "active": "Active",
    "locked": "Locked",
    "must_change_password": "Must change password",
    "deactivated": "Deactivated",
}
_ROLE_LABELS = {role: role.value.capitalize() for role in UserRole}

MemberSort = Literal["name", "email", "role", "status", "added"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _refused(error: PeopleError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"code": error.code, "message": error.message})


def _read(db: Session, membership: OrgMembership, *, in_other_orgs: bool | None = None) -> MemberRead:
    user = membership.user
    if in_other_orgs is None:
        in_other_orgs = people.in_other_orgs(db, user, membership.org_id)
    now = _now()
    return MemberRead(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider,
        created_at=user.created_at,
        role=membership.role,
        added_at=membership.created_at,
        status=people.status_of(user, now),
        locked_until=user.locked_until if user.is_locked(now) else None,
        temp_password_expires_at=user.temp_password_expires_at if user.must_change_password else None,
        in_other_orgs=in_other_orgs,
    )


def _no_store(response: Response) -> None:
    # A temporary password is in the answer: no copy kept by any cache.
    response.headers["Cache-Control"] = "no-store"


@router.get("", response_model=Page[MemberRead])
def list_members(
    org_id: uuid.UUID,
    q: str | None = Query(None, description="Search the shown columns: name, email, role or status contains this"),
    search_scope: Literal["all", "identity"] = Query(
        "all", description="identity searches name/email only; all also searches role/status"
    ),
    name: str | None = Query(None, description="The name contains this"),
    email: str | None = Query(None, description="The email contains this"),
    role: list[UserRole] | None = Query(None, description="Role is one of these"),
    status_: list[str] | None = Query(
        None, alias="status", description="Status is one of these: active, locked, must_change_password, deactivated"
    ),
    dates: DateRange = Depends(date_range),
    sort: MemberSort = Query("name", description="Column to sort by"),
    order: SortOrder = Query("asc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[MemberRead]:
    """The org's members, by name. Every member can read it."""
    now = _now()
    state = people.status_expression(now)
    others = people.in_other_orgs_expression(org_id)
    conditions = [OrgMembership.org_id == org_id]
    for match in (
        any_of(
            contains(q, User.name, User.email),
            labelled(q, OrgMembership.role, _ROLE_LABELS) if search_scope == "all" else None,
            labelled(q, state, _STATUS_LABELS) if search_scope == "all" else None,
        ),
        contains(name, User.name),
        contains(email, User.email),
        one_of(OrgMembership.role, [r.value for r in role] if role else None),
        one_of(state, status_),
    ):
        if match is not None:
            conditions.append(match)
    conditions += dates.conditions(OrgMembership.created_at)
    sort_columns = {
        "name": func.lower(func.coalesce(User.name, User.email)),
        "email": User.email,
        "role": OrgMembership.role,
        "status": state,
        "added": OrgMembership.created_at,
    }
    base = select(OrgMembership).join(User, User.id == OrgMembership.user_id).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(
        base.add_columns(others)
        .order_by(ordered(sort_columns[sort], order), User.email)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return Page(items=[_read(db, m, in_other_orgs=other) for m, other in rows], total=total)


@router.get("/facets", response_model=MemberFacets)
def member_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> MemberFacets:
    """The values the pick-lists can offer: roles and statuses present."""
    joined = select(OrgMembership).join(User, User.id == OrgMembership.user_id).where(OrgMembership.org_id == org_id)
    roles = db.scalars(joined.with_only_columns(OrgMembership.role).distinct()).all()
    statuses = db.scalars(joined.with_only_columns(people.status_expression(_now())).distinct()).all()
    return MemberFacets(role=sorted(r.value for r in roles), status=sorted(statuses))


@router.post("", response_model=MemberAdded, status_code=status.HTTP_201_CREATED)
def add_member(
    org_id: uuid.UUID,
    payload: MemberAdd,
    response: Response,
    db: Session = Depends(get_db),
    admin: OrgMembership = Depends(admin_only),
) -> MemberAdded:
    """Add someone by email. A new account gets a temporary password, shown
    once here, to be changed at their first sign-in; someone who already
    has an account signs in with their own password. Admins only."""
    try:
        membership, temporary = people.add_member(
            db, org_id, admin.user, email=payload.email, name=payload.name, role=payload.role
        )
        db.commit()
    except PeopleError as refused:
        raise _refused(refused)
    except IntegrityError:
        # The same new email added by another admin at the same moment.
        db.rollback()
        raise _refused(PeopleError(409, "conflict", f"{payload.email} was just added elsewhere. Try again."))
    db.refresh(membership)
    _no_store(response)
    return MemberAdded(**_read(db, membership).model_dump(), temporary_password=temporary)


@router.patch("/{user_id}", response_model=MemberRead)
def update_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    admin: OrgMembership = Depends(admin_only),
) -> MemberRead:
    """Change someone's role, or the name of someone who belongs to this org
    alone. A role change ends their sessions. Admins only."""
    try:
        membership = people.get_member(db, org_id, user_id)
        if payload.name is not None:
            people.rename_member(db, membership, admin.user, payload.name)
        if payload.role is not None:
            people.change_role(db, membership, admin.user, payload.role)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    db.refresh(membership)
    return _read(db, membership)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    org_id: uuid.UUID, user_id: uuid.UUID, db: Session = Depends(get_db), admin: OrgMembership = Depends(admin_only)
) -> None:
    """Take away someone's access to this org (their account stays) and end
    their sessions. Admins only."""
    try:
        people.remove_member(db, people.get_member(db, org_id, user_id), admin.user)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)


@router.post("/{user_id}/reset-password", response_model=PasswordReset)
def reset_password(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
    admin: OrgMembership = Depends(admin_only),
) -> PasswordReset:
    """A new temporary password for someone who belongs to this org alone,
    shown once here; their sessions end and a lock is cleared. Admins only."""
    try:
        password, expires_at = people.reset_password(db, people.get_member(db, org_id, user_id), admin.user)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    _no_store(response)
    return PasswordReset(temporary_password=password, expires_at=expires_at)


@router.post("/{user_id}/unlock", response_model=MemberRead)
def unlock_member(
    org_id: uuid.UUID, user_id: uuid.UUID, db: Session = Depends(get_db), admin: OrgMembership = Depends(admin_only)
) -> MemberRead:
    """Unlock someone locked after failed sign-ins. Admins only."""
    try:
        membership = people.get_member(db, org_id, user_id)
        people.unlock_member(db, membership, admin.user)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    db.refresh(membership)
    return _read(db, membership)
