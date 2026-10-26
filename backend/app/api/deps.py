import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User
from app.services.sessions import SessionEnded, check_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Sent by the app with its own polling (import progress, the worker's
# status): checked like any request, but not counted as the person being
# active, so an open page still reaches the idle limit.
BACKGROUND_HEADER = "X-Activity"


def is_background(request: Request) -> bool:
    return request.headers.get(BACKGROUND_HEADER, "").lower() == "background"


@dataclass
class SignedIn:
    user: User
    session: UserSession


def _unauthorized(detail: str = "Could not validate credentials", code: str = "token_invalid") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


SESSION_ENDED = {
    "idle": "You were signed out after a period of inactivity. Please sign in again.",
    "expired": "Your sign-in has expired. Please sign in again.",
    "role_changed": "An administrator changed your role. Please sign in again.",
    "removed": "An administrator removed you from an organization. Please sign in again.",
    "password_reset": "An administrator reset your password. Sign in with the temporary password they give you.",
    "signed_out_elsewhere": "You were signed out from another browser. Please sign in again.",
}


def parse_access_token(token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """The user and session an access token names, if it's valid and unexpired."""
    try:
        payload = decode_access_token(token)
        return uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None


def get_signed_in(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> SignedIn:
    """The access token's user and session, the session still open
    (services/sessions.py). Doesn't refuse someone who must change their
    password: only for the pages that let them (get_current_user does)."""
    parsed = parse_access_token(token)
    if parsed is None:
        raise _unauthorized()
    user_id, session_id = parsed
    try:
        session = check_session(db, session_id, user_id, background=is_background(request))
    except SessionEnded as ended:
        raise _unauthorized(
            SESSION_ENDED.get(ended.reason, "Your session has ended. Please sign in again."), "session_ended"
        )
    return SignedIn(user=session.user, session=session)


def get_current_user(signed_in: SignedIn = Depends(get_signed_in)) -> User:
    if signed_in.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "Change your password to continue."},
        )
    return signed_in.user


@dataclass
class SysadminView:
    """The Sysadmin's access to an org it doesn't belong to: read-only, like
    a viewer's (not a membership row: nothing is saved)."""

    user: User
    organization: Organization
    role: UserRole = UserRole.viewer

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def org_id(self) -> uuid.UUID:
        return self.organization.id


def require_org_member(
    org_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OrgMembership | SysadminView:
    """Gate for every /orgs/{org_id}/... route: the caller must belong to
    that org (or be the Sysadmin, who reads every org). An org being purged
    is gone for everyone."""
    membership = db.get(OrgMembership, (user.id, org_id))
    if membership is None and user.is_sysadmin:
        org = db.get(Organization, org_id)
        if org is not None:
            membership = SysadminView(user=user, organization=org)
    if membership is None or membership.organization.purge_requested_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization access denied")
    return membership


def refuse_if_archived(membership: OrgMembership | SysadminView) -> None:
    if membership.organization.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "org_archived", "message": f"{membership.organization.name} is archived, so it's read-only."},
        )


def require_org_role(*roles: UserRole):
    """Like require_org_member, but also checks the caller's role in that
    org. Privileged organization mutations use this transactional admission
    fence; per-user notification dismissals and read-only routes do not."""

    def checker(membership: OrgMembership = Depends(require_org_member), db: Session = Depends(get_db)) -> OrgMembership:
        if membership.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return authorize_org_write(db, membership.org_id, membership.user_id, roles)

    return checker


def authorize_org_write(db: Session, org_id: uuid.UUID, user_id: uuid.UUID, roles: tuple[UserRole, ...]) -> OrgMembership:
    """Revalidate after waiting; fence lifecycle/role changes until commit.

    Job admission precedes the organization row, as in archive/workflow services.
    NO KEY UPDATE serializes writers/lifecycle changes without blocking inventory
    foreign-key KEY SHARE locks held by publishing background workers.
    """
    from app.services.org_lock import lock_org_jobs
    lock_org_jobs(db, org_id)
    org = db.scalar(select(Organization).where(Organization.id == org_id)
        .with_for_update(key_share=True).execution_options(populate_existing=True))
    current = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id,
        OrgMembership.user_id == user_id).execution_options(populate_existing=True))
    active = db.scalar(select(User.is_active).where(User.id == user_id))
    if org is None or org.purge_requested_at is not None or current is None or not active or current.role not in roles:
        raise HTTPException(status_code=403, detail="Organization access or permissions changed; reload before retrying")
    refuse_if_archived(current)
    return current


def require_sysadmin(user: User = Depends(get_current_user)) -> User:
    """Gate for /platform/...: the Sysadmin only."""
    if not user.is_sysadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sysadmin only")
    return user
