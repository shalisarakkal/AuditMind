"""The Sysadmin's Platform section: organizations, accounts and the
platform's security defaults (services/platform.py has the rules). The
Sysadmin only."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_sysadmin
from app.api.paging import PageParams, SortOrder, any_of, contains, labelled, one_of, ordered, page_params
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.session import PlatformSetting
from app.models.user import User
from app.schemas.paging import Page
from app.schemas.platform import (
    OrgFacets,
    OrgPurge,
    PlatformOrgCreate,
    PlatformOrgCreated,
    PlatformOrgRead,
    PlatformUserRead,
    PlatformUserUpdate,
    RoleUpdate,
    UserFacets,
    UserOrg,
)
from app.schemas.security import SecuritySettingsRead, SecuritySettingsUpdate
from app.schemas.product_branding import ProductBrandingRead, ProductBrandingUpdate
from app.services import people, platform
from app.services.events import record_event
from app.services.people import PeopleError
from app.services.security_policy import PLATFORM_KEY, SecuritySettings, change_layer, resolve_platform_security

router = APIRouter(prefix="/platform", tags=["platform"])

PRODUCT_BRANDING_KEY = "product_branding"


@router.get("/branding", response_model=ProductBrandingRead)
def read_product_branding(response: Response, db: Session = Depends(get_db),
                          _: User = Depends(get_current_user)):
    """Display-only preferences readable by signed-in users; not security defaults."""
    _no_store(response)
    row = db.get(PlatformSetting, PRODUCT_BRANDING_KEY)
    return ProductBrandingRead.model_validate(row.value if row else {})


@router.patch("/branding", response_model=ProductBrandingRead)
def update_product_branding(payload: ProductBrandingUpdate, response: Response,
                            db: Session = Depends(get_db), sysadmin: User = Depends(require_sysadmin)):
    # A row lock alone cannot fence two first saves when no row exists yet.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('auditmind:product-branding'))"))
    actor = db.scalar(select(User).where(User.id == sysadmin.id).with_for_update(read=True).execution_options(populate_existing=True))
    if actor is None or not actor.is_active or not actor.is_sysadmin:
        raise HTTPException(403, "Platform permissions changed; reload before retrying")
    row = db.get(PlatformSetting, PRODUCT_BRANDING_KEY, populate_existing=True)
    before = ProductBrandingRead.model_validate(row.value if row else {})
    if payload.expected_version != before.version:
        raise HTTPException(409, "Product branding changed; reload before retrying")
    after = before
    if payload.sidebar_logo_size != before.sidebar_logo_size:
        after = ProductBrandingRead(sidebar_logo_size=payload.sidebar_logo_size, version=str(uuid.uuid4()))
        if row is None:
            db.add(PlatformSetting(key=PRODUCT_BRANDING_KEY, value=after.model_dump()))
        else:
            row.value = after.model_dump()
        record_event(db, "settings_changed", org_id=None, actor=sysadmin, item="Product branding",
                     details={"sidebar_logo_size": {"from": before.sidebar_logo_size, "to": after.sidebar_logo_size}})
    db.commit()
    _no_store(response)
    return after


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _refused(error: PeopleError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"code": error.code, "message": error.message})


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


# --- Organizations -------------------------------------------------------------

_ORG_STATUS = case(
    (Organization.purge_requested_at.is_not(None), "purging"),
    (Organization.archived_at.is_not(None), "archived"),
    else_="active",
)
_ORG_STATUS_LABELS = {"active": "Active", "archived": "Archived", "purging": "Being purged"}
_members = (
    select(func.count()).where(OrgMembership.org_id == Organization.id).correlate(Organization).scalar_subquery()
)
OrgSort = Literal["name", "status", "members", "created"]


def _org_read(db: Session, org: Organization, members: int | None = None) -> PlatformOrgRead:
    admins = db.scalars(
        select(User.email)
        .join(OrgMembership, OrgMembership.user_id == User.id)
        .where(OrgMembership.org_id == org.id, OrgMembership.role == UserRole.admin)
        .order_by(User.email)
    ).all()
    if members is None:
        members = db.scalar(select(func.count()).where(OrgMembership.org_id == org.id))
    return PlatformOrgRead(
        id=org.id,
        name=org.name,
        industry=org.industry,
        size=org.size,
        created_at=org.created_at,
        status=org.status,
        archived_at=org.archived_at,
        members=members,
        admins=list(admins),
    )


def _org(db: Session, org_id: uuid.UUID) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("/orgs", response_model=Page[PlatformOrgRead])
def list_orgs(
    q: str | None = Query(None, description="Search: name, industry or status contains this"),
    status_: list[str] | None = Query(None, alias="status", description="active, archived or purging"),
    sort: OrgSort = Query("name"),
    order: SortOrder = Query("asc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: User = Depends(require_sysadmin),
) -> Page[PlatformOrgRead]:
    conditions = []
    for match in (
        any_of(contains(q, Organization.name, Organization.industry), labelled(q, _ORG_STATUS, _ORG_STATUS_LABELS)),
        one_of(_ORG_STATUS, status_),
    ):
        if match is not None:
            conditions.append(match)
    columns = {
        "name": func.lower(Organization.name),
        "status": _ORG_STATUS,
        "members": _members,
        "created": Organization.created_at,
    }
    total = db.scalar(select(func.count()).select_from(Organization).where(*conditions))
    rows = db.execute(
        select(Organization, _members)
        .where(*conditions)
        .order_by(ordered(columns[sort], order), Organization.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return Page(items=[_org_read(db, org, members) for org, members in rows], total=total)


@router.get("/orgs/facets", response_model=OrgFacets)
def org_facets(db: Session = Depends(get_db), _: User = Depends(require_sysadmin)) -> OrgFacets:
    return OrgFacets(status=sorted(db.scalars(select(_ORG_STATUS).select_from(Organization).distinct()).all()))


@router.post("/orgs", response_model=PlatformOrgCreated, status_code=status.HTTP_201_CREATED)
def create_org(
    payload: PlatformOrgCreate,
    response: Response,
    db: Session = Depends(get_db),
    sysadmin: User = Depends(require_sysadmin),
) -> PlatformOrgCreated:
    """A new organization with its first admin. Someone new gets a
    temporary password, shown once here."""
    try:
        org, membership, temporary = platform.create_org(
            db,
            sysadmin,
            name=payload.name.strip(),
            industry=payload.industry,
            size=payload.size,
            admin_email=payload.admin_email,
            admin_name=payload.admin_name,
        )
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    except IntegrityError:
        db.rollback()
        raise _refused(PeopleError(409, "conflict", f"{payload.admin_email} was just added elsewhere. Try again."))
    _no_store(response)
    return PlatformOrgCreated(
        **_org_read(db, org).model_dump(),
        temporary_password=temporary,
        temp_password_expires_at=membership.user.temp_password_expires_at if temporary else None,
    )


def _org_action(db: Session, org_id: uuid.UUID, act) -> PlatformOrgRead:
    org = _org(db, org_id)
    try:
        act(org)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    db.refresh(org)
    return _org_read(db, org)


@router.post("/orgs/{org_id}/archive", response_model=PlatformOrgRead)
def archive_org(
    org_id: uuid.UUID, db: Session = Depends(get_db), sysadmin: User = Depends(require_sysadmin)
) -> PlatformOrgRead:
    """Make the org read-only; refused while any org-owned background jobs are active."""
    return _org_action(db, org_id, lambda org: platform.archive_org(db, org, sysadmin))


@router.post("/orgs/{org_id}/restore", response_model=PlatformOrgRead)
def restore_org(
    org_id: uuid.UUID, db: Session = Depends(get_db), sysadmin: User = Depends(require_sysadmin)
) -> PlatformOrgRead:
    return _org_action(db, org_id, lambda org: platform.restore_org(db, org, sysadmin))


@router.post("/orgs/{org_id}/purge", response_model=PlatformOrgRead, status_code=status.HTTP_202_ACCEPTED)
def purge_org(
    org_id: uuid.UUID, payload: OrgPurge, db: Session = Depends(get_db), sysadmin: User = Depends(require_sysadmin)
) -> PlatformOrgRead:
    """Delete an archived org and everything in it, for good: it's gone at
    once for everyone, and the background worker deletes its data. The
    org's name must be typed again."""
    return _org_action(db, org_id, lambda org: platform.request_purge(db, org, sysadmin, payload.name))


# --- Accounts ----------------------------------------------------------------

_STATUS_LABELS = {
    "active": "Active",
    "locked": "Locked",
    "must_change_password": "Must change password",
    "deactivated": "Deactivated",
}
UserSort = Literal["name", "email", "status", "created"]


def _user_read(db: Session, user: User, now: datetime) -> PlatformUserRead:
    memberships = db.execute(
        select(OrgMembership.org_id, Organization.name, OrgMembership.role)
        .join(Organization, Organization.id == OrgMembership.org_id)
        .where(OrgMembership.user_id == user.id)
        .order_by(func.lower(Organization.name))
    ).all()
    return PlatformUserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        created_at=user.created_at,
        status=people.status_of(user, now),
        is_sysadmin=user.is_sysadmin,
        locked_until=user.locked_until if user.is_locked(now) else None,
        temp_password_expires_at=user.temp_password_expires_at if user.must_change_password else None,
        orgs=[UserOrg(org_id=org_id, name=name, role=role) for org_id, name, role in memberships],
    )


def _user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such account")
    return user


@router.get("/users", response_model=Page[PlatformUserRead])
def list_users(
    q: str | None = Query(None, description="Search: name, email, status or one of their orgs contains this"),
    status_: list[str] | None = Query(None, alias="status", description="active, locked, must_change_password, deactivated"),
    sort: UserSort = Query("name"),
    order: SortOrder = Query("asc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: User = Depends(require_sysadmin),
) -> Page[PlatformUserRead]:
    now = _now()
    state = people.status_expression(now)
    in_org_named = None
    if q and q.strip():
        org_match = contains(q, Organization.name)
        in_org_named = User.id.in_(
            select(OrgMembership.user_id).join(Organization, Organization.id == OrgMembership.org_id).where(org_match)
        )
    conditions = []
    for match in (
        any_of(contains(q, User.name, User.email), labelled(q, state, _STATUS_LABELS), in_org_named),
        one_of(state, status_),
    ):
        if match is not None:
            conditions.append(match)
    columns = {
        "name": func.lower(func.coalesce(User.name, User.email)),
        "email": User.email,
        "status": state,
        "created": User.created_at,
    }
    total = db.scalar(select(func.count()).select_from(User).where(*conditions))
    users = db.scalars(
        select(User)
        .where(*conditions)
        .order_by(ordered(columns[sort], order), User.email)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return Page(items=[_user_read(db, user, now) for user in users], total=total)


@router.get("/users/facets", response_model=UserFacets)
def user_facets(db: Session = Depends(get_db), _: User = Depends(require_sysadmin)) -> UserFacets:
    state = people.status_expression(_now())
    return UserFacets(status=sorted(db.scalars(select(state).select_from(User).distinct()).all()))


@router.patch("/users/{user_id}", response_model=PlatformUserRead)
def update_user(
    user_id: uuid.UUID,
    payload: PlatformUserUpdate,
    db: Session = Depends(get_db),
    sysadmin: User = Depends(require_sysadmin),
) -> PlatformUserRead:
    """Rename, change the email (the sign-in), deactivate or reactivate an
    account. Deactivating ends its sessions."""
    user = _user(db, user_id)
    try:
        if payload.name is not None:
            people.rename(db, user, sysadmin, payload.name)
        if payload.email is not None:
            platform.change_email(db, user, sysadmin, payload.email)
        if payload.active is not None:
            platform.set_active(db, user, sysadmin, payload.active)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    db.refresh(user)
    return _user_read(db, user, _now())


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID, response: Response, db: Session = Depends(get_db), sysadmin: User = Depends(require_sysadmin)
) -> dict:
    """A temporary password for anyone (whatever their orgs), shown once
    here; their sessions end and a lock is cleared."""
    user = _user(db, user_id)
    try:
        password = platform.reset_password(db, user, sysadmin)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    _no_store(response)
    return {"temporary_password": password, "expires_at": user.temp_password_expires_at}


@router.post("/users/{user_id}/unlock", response_model=PlatformUserRead)
def unlock_user(
    user_id: uuid.UUID, db: Session = Depends(get_db), sysadmin: User = Depends(require_sysadmin)
) -> PlatformUserRead:
    user = _user(db, user_id)
    try:
        platform.unlock(db, user, sysadmin)
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    return _user_read(db, user, _now())


@router.patch("/users/{user_id}/orgs/{org_id}", response_model=PlatformUserRead)
def change_role(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    sysadmin: User = Depends(require_sysadmin),
) -> PlatformUserRead:
    """In an emergency (an org whose admins can't), change someone's role
    in an org; the org still keeps an admin. Ends their sessions."""
    user = _user(db, user_id)
    try:
        membership = people.get_member(db, org_id, user_id)
        before = membership.role
        people.change_role(db, membership, sysadmin, payload.role)
        if before != payload.role:
            record_event(
                db,
                "role_changed",
                org_id=None,
                actor=sysadmin,
                item=user.email,
                details={"from": before.value, "to": payload.role.value, "org": membership.organization.name},
            )
        db.commit()
    except PeopleError as refused:
        db.rollback()
        raise _refused(refused)
    db.refresh(user)
    return _user_read(db, user, _now())


# --- Security defaults ---------------------------------------------------------


@router.get("/security", response_model=SecuritySettingsRead)
def get_security(db: Session = Depends(get_db), _: User = Depends(require_sysadmin)) -> SecuritySettingsRead:
    """The platform's defaults: every org starts with them, and its admins
    may change them (Settings > Security)."""
    row = db.get(PlatformSetting, PLATFORM_KEY)
    return SecuritySettingsRead(
        values=resolve_platform_security(db), changed=sorted((row.value if row else {}).keys()), below=SecuritySettings()
    )


@router.patch("/security", response_model=SecuritySettingsRead)
def update_security(
    changes: SecuritySettingsUpdate = Body(...),
    db: Session = Depends(get_db),
    sysadmin: User = Depends(require_sysadmin),
) -> SecuritySettingsRead:
    """Send a value to change a default, null to go back to the built-in
    value; settings left out are unchanged. Recorded in Platform activity."""
    row = db.get(PlatformSetting, PLATFORM_KEY, with_for_update=True)
    before = resolve_platform_security(db)
    try:
        stored, after = change_layer(SecuritySettings(), row.value if row else None, changes)
    except (ValueError, ValidationError) as invalid:
        raise invalid_settings(invalid)
    if row is None:
        row = PlatformSetting(key=PLATFORM_KEY, value=stored)
        db.add(row)
    else:
        row.value = stored
    record_settings_change(db, None, sysadmin, before, after)
    db.commit()
    return SecuritySettingsRead(values=after, changed=sorted(stored), below=SecuritySettings())


def invalid_settings(error: Exception) -> HTTPException:
    if isinstance(error, ValidationError):
        # "lockout_threshold: must be 0 (never lock) or 3 to 6" (not pydantic's "Value error, ...").
        message = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg'].removeprefix('Value error, ')}"
            for e in error.errors()
        )
    else:
        message = str(error)
    return HTTPException(status_code=422, detail={"code": "invalid_settings", "message": message})


def record_settings_change(
    db: Session, org_id: uuid.UUID | None, actor: User, before: SecuritySettings, after: SecuritySettings
) -> None:
    """A "Settings changed" event with what changed (old and new values)."""
    changed = {
        key: {"from": getattr(before, key), "to": getattr(after, key)}
        for key in SecuritySettings.model_fields
        if getattr(before, key) != getattr(after, key)
    }
    if changed:
        record_event(
            db,
            "settings_changed",
            org_id=org_id,
            actor=actor,
            item="Security" + (" defaults" if org_id is None else ""),
            details=changed,
        )
