"""Signing in and out, renewing the sign-in, and changing one's password.

The app keeps a short-lived access token in memory (never in storage, where
injected script could read it) and sends it as a Bearer header. The session
cookie renews it: HttpOnly, sent only to /auth (its Path) and only from this
site (SameSite=Strict). The two endpoints that act on the cookie alone,
refresh and logout, also need the app's own header and an Origin of ours,
so another site can't make a browser use it (CSRF).
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SignedIn, get_current_user, get_signed_in, is_background, parse_access_token
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, Me, PasswordRulesRead, RegisterRequest, Token
from app.schemas.user import NameUpdate
from app.services import accounts, people, sessions
from app.services.client_info import client_details, describe_browser
from app.services.events import record_event, record_for_user_orgs
from app.services.rate_limit import login_limiter
from app.services.security_policy import SecurityPolicy, effective_policy

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "auditmind_session"
# The app sends this with refresh and logout; a page on another site can't
# without the browser asking us first (CORS), which we refuse.
CSRF_HEADER, CSRF_VALUE = "X-Requested-With", "AuditMind"


def _cookie_path() -> str:
    return f"{settings.API_V1_STR}/auth"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_cookie(response: Response, raw: str, session: UserSession) -> None:
    max_age = int((session.expires_at - _now()).total_seconds())
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=max(max_age, 0),
        path=_cookie_path(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME, path=_cookie_path(), httponly=True, secure=settings.COOKIE_SECURE, samesite="strict"
    )


def _check_origin(request: Request, *, require_header: bool) -> None:
    """Refuse requests another site made a browser send (CSRF)."""
    origin = request.headers.get("origin")
    if (
        (require_header and request.headers.get(CSRF_HEADER) != CSRF_VALUE)
        or (origin and origin not in settings.cors_origins_list and origin != _own_origin(request))
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request refused (not from AuditMind)")


def _own_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _ip(request: Request) -> str | None:
    # Behind a proxy, uvicorn's --forwarded-allow-ips makes this the
    # visitor's own address (README).
    return request.client.host if request.client else None


def _client(request: Request) -> dict:
    """Where a sign-in comes from, for its Activity event."""
    return client_details(_ip(request), request.headers.get("user-agent"))


def _rate_limit(request: Request) -> None:
    retry_after = login_limiter.hit(request.client.host if request.client else "unknown")
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many sign-in attempts. Try again in a minute."},
            headers={"Retry-After": str(retry_after)},
        )


def _token(session: UserSession, user: User) -> Token:
    return Token(
        access_token=sessions.access_token(session),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        must_change_password=user.must_change_password,
    )


def _start_session(
    db: Session, request: Request, response: Response, user: User, policy: SecurityPolicy
) -> UserSession:
    session, raw = sessions.create_session(
        db,
        user,
        policy,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_cookie(response, raw, session)
    return session


def _password_rejected(problems) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "password_policy",
            "message": "; ".join(p.message for p in problems),
            "problems": [{"code": p.code, "message": p.message} for p in problems],
        },
    )


class AuthOptions(BaseModel):
    # Whether the sign-in page offers "Create an account" (PUBLIC_SIGNUP).
    public_signup: bool


@router.get("/options", response_model=AuthOptions)
def options() -> AuthOptions:
    """What the sign-in page offers, before anyone signs in."""
    return AuthOptions(public_signup=settings.PUBLIC_SIGNUP)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> Token:
    """Sign up with a new org, when PUBLIC_SIGNUP is on (it says whether the
    email has an account: the price of open sign-up)."""
    if not settings.PUBLIC_SIGNUP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "signup_closed", "message": "Sign-up is closed. Ask your administrator for an account."},
        )
    _check_origin(request, require_header=False)
    _rate_limit(request)
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    policy = effective_policy(db, None)
    problems = accounts.password_problems(db, payload.password, policy, email=payload.email)
    if problems:
        raise _password_rejected(problems)

    org = Organization(name=payload.org_name)
    db.add(org)
    db.flush()

    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(OrgMembership(user_id=user.id, org_id=org.id, role=UserRole.admin))
    record_event(db, "registered", org_id=org.id, actor=user, item=user.email)
    session = _start_session(db, request, response, user, policy)
    db.commit()
    return _token(session, user)


_LOGIN_BODY_DOCS = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": LoginRequest.model_json_schema()},
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "required": ["username", "password"],
                    "properties": {
                        "username": {"type": "string", "description": "Your email address"},
                        "password": {"type": "string", "format": "password"},
                    },
                }
            },
        },
    }
}


@router.post("/login", response_model=Token, openapi_extra=_LOGIN_BODY_DOCS)
async def login(request: Request, response: Response, db: Session = Depends(get_db)) -> Token:
    """JSON {email, password}, or an OAuth2 password form (username = email),
    which is what Swagger's Authorize button sends."""
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")
    else:
        form = await request.form()
        data = {"email": form.get("username"), "password": form.get("password")}
    try:
        payload = LoginRequest.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False))
    # Checking a password takes a while (on purpose): off the event loop, so
    # other requests aren't held up.
    return await run_in_threadpool(_login, request, response, payload, db)


def _login(request: Request, response: Response, payload: LoginRequest, db: Session) -> Token:
    _check_origin(request, require_header=False)
    _rate_limit(request)
    try:
        user, policy = accounts.sign_in(db, payload.email, payload.password, client=_client(request))
    except accounts.SignInRefused as refused:
        raise HTTPException(status_code=refused.status, detail={"code": refused.code, "message": refused.message})
    session = _start_session(db, request, response, user, policy)
    record_for_user_orgs(db, "login", user, item=user.email, details=_client(request) or None)
    db.commit()
    return _token(session, user)


@router.post("/refresh", response_model=Token)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> Token:
    """A new access token, from the session cookie, while the session is open."""
    _check_origin(request, require_header=True)
    try:
        session, policy = sessions.renew(db, request.cookies.get(COOKIE_NAME), background=is_background(request))
    except sessions.SessionEnded:
        ended = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": {"code": "session_ended", "message": "Please sign in again."}},
        )
        _clear_cookie(ended)
        return ended
    user = session.user
    if not user.must_change_password and accounts.password_expired(user, policy, _now()):
        user.must_change_password = True
        db.commit()
    # Its expiry follows the longest sign-in, which an admin may have changed.
    _set_cookie(response, request.cookies[COOKIE_NAME], session)
    return _token(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    """End this session: the one the access token names, or else the
    cookie's (the access token may have run out). Fine to repeat."""
    session = _bearer_session(db, request)
    if session is None:
        _check_origin(request, require_header=True)
        session = sessions.session_from_cookie(db, request.cookies.get(COOKIE_NAME))
    if session is not None and session.revoked_at is None:
        sessions.end_session(session, "signout")
        record_for_user_orgs(
            db, "logout", session.user, item=session.user.email, details=_session_details(session) or None
        )
        db.commit()
    _clear_cookie(response)


def _bearer_session(db: Session, request: Request) -> UserSession | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    parsed = parse_access_token(token) if scheme.lower() == "bearer" else None
    if parsed is None:
        return None
    user_id, session_id = parsed
    session = db.get(UserSession, session_id)
    return session if session is not None and session.user_id == user_id else None


@router.get("/me", response_model=Me)
def me(signed_in: SignedIn = Depends(get_signed_in), db: Session = Depends(get_db)) -> Me:
    return _me(db, signed_in.user)


@router.patch("/me", response_model=Me)
def update_me(payload: NameUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Me:
    """Change one's own name (the email, the sign-in, can't be changed here).
    Recorded in each of their orgs' Activity."""
    people.rename(db, user, user, payload.name)
    db.commit()
    return _me(db, user)


def _me(db: Session, user: User) -> Me:
    days = effective_policy(db, user).password.expiry_days
    return Me(
        id=str(user.id),
        email=user.email,
        name=user.name,
        is_sysadmin=user.is_sysadmin,
        must_change_password=user.must_change_password,
        password_expires_at=user.password_changed_at + timedelta(days=days)
        if days and user.password_changed_at
        else None,
    )


@router.get("/password-rules", response_model=PasswordRulesRead)
def password_rules(signed_in: SignedIn = Depends(get_signed_in), db: Session = Depends(get_db)) -> PasswordRulesRead:
    """The rule the user's next password must meet (the strictest of their orgs')."""
    policy = effective_policy(db, signed_in.user)
    return PasswordRulesRead(**vars(policy.password), required_by=policy.required_by)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest, signed_in: SignedIn = Depends(get_signed_in), db: Session = Depends(get_db)
) -> None:
    """Change one's own password (also a temporary or expired one). Other
    sessions end; this one goes on."""
    try:
        accounts.change_password(
            db, signed_in.user, payload.current_password, payload.new_password, session_id=signed_in.session.id
        )
    except accounts.WrongCurrentPassword as wrong:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "wrong_current", "message": str(wrong)}
        )
    except accounts.PasswordRejected as rejected:
        raise _password_rejected(rejected.problems)


# --- Where you're signed in ---------------------------------------------------


def _session_details(session: UserSession) -> dict:
    return client_details(session.ip, session.user_agent)


class SessionRead(BaseModel):
    id: str
    signed_in_at: datetime
    # Last seen active (not the app's own polling), to within
    # SESSION_TOUCH_SECONDS.
    last_active_at: datetime
    ip: str | None
    browser: str | None
    # The sign-in this request comes from.
    current: bool


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(signed_in: SignedIn = Depends(get_signed_in), db: Session = Depends(get_db)) -> list[SessionRead]:
    """The caller's open sign-ins (each browser or device), newest first."""
    now = _now()
    open_sessions = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == signed_in.user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
    ).all()
    return [
        SessionRead(
            id=str(s.id),
            signed_in_at=s.created_at,
            last_active_at=s.last_seen_at,
            ip=s.ip,
            browser=describe_browser(s.user_agent),
            current=s.id == signed_in.session.id,
        )
        for s in open_sessions
        if now - s.last_seen_at <= timedelta(minutes=s.idle_minutes)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def end_session(
    session_id: uuid.UUID, signed_in: SignedIn = Depends(get_signed_in), db: Session = Depends(get_db)
) -> None:
    """Sign out one of the caller's other sign-ins (Sign out ends this one)."""
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != signed_in.user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such sign-in")
    if session.id == signed_in.session.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "current", "message": "That's this browser: use Sign out."},
        )
    if session.revoked_at is None:
        sessions.end_session(session, "signed_out_elsewhere")
        record_for_user_orgs(
            db, "logout", signed_in.user, item=signed_in.user.email, details={**_session_details(session), "from_elsewhere": True}
        )
        db.commit()


@router.post("/sessions/end-others", status_code=status.HTTP_204_NO_CONTENT)
def end_other_sessions(signed_in: SignedIn = Depends(get_signed_in), db: Session = Depends(get_db)) -> None:
    """Sign out every other sign-in of the caller's."""
    ended = sessions.end_user_sessions(
        db, signed_in.user.id, "signed_out_elsewhere", except_session_id=signed_in.session.id
    )
    if ended:
        record_for_user_orgs(
            db, "logout", signed_in.user, item=signed_in.user.email, details={"other_sign_ins": ended, "from_elsewhere": True}
        )
    db.commit()
