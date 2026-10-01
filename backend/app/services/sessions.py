"""Sign-in sessions (models/session.py).

The app holds a short-lived access token naming its session (sid); every
request checks that session here, so ending one (sign-out, a password
change, an admin) takes effect at once. The session cookie, which page
scripts can't read, renews the access token until the session's idle or
longest-sign-in limit (security settings) ends it.

Time is passed in (`now`) so tests can move it.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_refresh_token, new_refresh_token
from app.models.session import UserSession
from app.models.user import User
from app.services.security_policy import SecurityPolicy, effective_policy

# How long ended sessions are kept (for "where am I signed in" later), then
# the worker's daily housekeeping deletes them.
KEEP_ENDED_DAYS = 30


class SessionEnded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(
    db: Session,
    user: User,
    policy: SecurityPolicy,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> tuple[UserSession, str]:
    """A new session; returns it and the cookie's value (not stored)."""
    now = now or _now()
    raw, hashed = new_refresh_token()
    session = UserSession(
        user_id=user.id,
        refresh_hash=hashed,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=policy.max_session_days),
        idle_minutes=policy.idle_minutes,
        ip=ip[:45] if ip else None,
        user_agent=user_agent[:255] if user_agent else None,
    )
    db.add(session)
    db.flush()
    return session, raw


def access_token(session: UserSession) -> str:
    return create_access_token(subject=str(session.user_id), session_id=session.id)


def _check(db: Session, session: UserSession | None, now: datetime) -> UserSession:
    """The session if it's still open; else ends it (if it isn't already)
    and raises SessionEnded."""
    if session is None:
        raise SessionEnded("unknown")
    if session.revoked_at is not None:
        raise SessionEnded(session.revoked_reason or "ended")
    if now >= session.expires_at:
        reason = "expired"
    elif now - session.last_seen_at > timedelta(minutes=session.idle_minutes):
        reason = "idle"
    elif not session.user.is_active:
        reason = "deactivated"
    else:
        return session
    end_session(session, reason, now=now)
    db.commit()
    raise SessionEnded(reason)


def _touch(session: UserSession, now: datetime, background: bool) -> bool:
    """Mark the person active, at most every SESSION_TOUCH_SECONDS; the
    app's own polling (background) isn't activity. True if it changed."""
    if background or now - session.last_seen_at < timedelta(seconds=settings.SESSION_TOUCH_SECONDS):
        return False
    session.last_seen_at = now
    return True


def check_session(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID, *, background: bool = False, now: datetime | None = None
) -> UserSession:
    """For each request: the open session the access token names."""
    now = now or _now()
    session = db.get(UserSession, session_id)
    if session is not None and session.user_id != user_id:
        session = None
    session = _check(db, session, now)
    if _touch(session, now, background):
        db.commit()
    return session


def renew(
    db: Session, raw_token: str | None, *, background: bool = False, now: datetime | None = None
) -> tuple[UserSession, SecurityPolicy]:
    """The cookie's session, still open, with its limits brought up to date
    (an admin may have changed the security settings): for a new access
    token. Also returns the user's settings."""
    now = now or _now()
    session = _check(db, session_from_cookie(db, raw_token), now)
    policy = effective_policy(db, session.user)
    session.idle_minutes = policy.idle_minutes
    session.expires_at = session.created_at + timedelta(days=policy.max_session_days)
    _touch(session, now, background)
    db.commit()
    return _check(db, session, now), policy


def session_from_cookie(db: Session, raw_token: str | None) -> UserSession | None:
    if not raw_token:
        return None
    return db.scalar(select(UserSession).where(UserSession.refresh_hash == hash_refresh_token(raw_token)))


def end_session(session: UserSession, reason: str, *, now: datetime | None = None) -> None:
    if session.revoked_at is None:
        session.revoked_at = now or _now()
        session.revoked_reason = reason


def end_user_sessions(
    db: Session,
    user_id: uuid.UUID,
    reason: str,
    *,
    except_session_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> int:
    """End every open session of a user (but `except_session_id`): after a
    password change or reset, deactivation, a role change or removal.
    Returns how many; the caller commits."""
    query = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id is not None:
        query = query.where(UserSession.id != except_session_id)
    result = db.execute(
        query.values(revoked_at=now or _now(), revoked_reason=reason).execution_options(synchronize_session="fetch")
    )
    return result.rowcount


def purge_old_sessions(db: Session, now: datetime | None = None) -> int:
    """Delete sessions ended, or past their longest sign-in, over
    KEEP_ENDED_DAYS ago. Run daily by the background worker."""
    cutoff = (now or _now()) - timedelta(days=KEEP_ENDED_DAYS)
    deleted = db.execute(
        delete(UserSession).where(or_(UserSession.revoked_at < cutoff, UserSession.expires_at < cutoff))
    ).rowcount
    db.commit()
    return deleted
