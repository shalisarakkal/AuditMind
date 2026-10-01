import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
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


def require_org_member(
    org_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OrgMembership:
    """Gate for every /orgs/{org_id}/... route: the caller must belong to that org."""
    membership = db.get(OrgMembership, (user.id, org_id))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization access denied")
    return membership


def require_org_role(*roles: UserRole):
    """Like require_org_member, but also checks the caller's role in that org."""

    def checker(membership: OrgMembership = Depends(require_org_member)) -> OrgMembership:
        if membership.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return membership

    return checker
