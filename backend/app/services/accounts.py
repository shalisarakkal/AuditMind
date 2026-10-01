"""Accounts: signing in (with lockout), and setting passwords.

A locked or deactivated account is only revealed to someone who gives its
correct password; anyone else gets the same "Invalid email or password", so
guessing can't find out which accounts exist or are locked.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, needs_rehash, verify_password, waste_a_verify
from app.models.session import PasswordHistory
from app.models.user import User
from app.services.events import record_for_user_orgs
from app.services.password_policy import Problem, check_password
from app.services.security_policy import SecurityPolicy, effective_policy
from app.services.sessions import end_user_sessions

logger = logging.getLogger(__name__)

# Previous passwords kept for the Complex rule (its history_count is at most 24).
HISTORY_KEPT = 24

INVALID = "Invalid email or password"


class SignInRefused(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class PasswordRejected(Exception):
    """The new password breaks the rule: every way it does."""

    def __init__(self, problems: list[Problem]):
        super().__init__(problems[0].message)
        self.problems = problems


class WrongCurrentPassword(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sign_in(
    db: Session, email: str, password: str, *, client: dict | None = None, now: datetime | None = None
) -> tuple[User, SecurityPolicy]:
    """The account, if `password` is right and it may sign in; else raises
    SignInRefused. Records failed attempts and locks (committed), with
    `client` (where the attempt came from: client_info.client_details)."""
    now = now or _now()
    # Locked for update: two guesses at once can't both slip under the limit.
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        logger.warning("Failed login for an unknown email")
        waste_a_verify(password)
        raise SignInRefused(401, "invalid", INVALID)

    policy = effective_policy(db, user)
    if user.locked_at is not None and not user.is_locked(now):
        _clear_failures(user)  # a timed lock that has run out
    correct = bool(user.hashed_password) and verify_password(password, user.hashed_password)

    if not correct:
        # In each of the account's orgs, so its admins see attempts on their
        # people (not by whom: it's someone trying the password).
        record_for_user_orgs(db, "login_failed", user, by_user=False, item=user.email, details=client or None)
        if not user.is_locked(now):
            _record_failure(db, user, policy, now=now, client=client)
        db.commit()
        raise SignInRefused(401, "invalid", INVALID)

    if user.is_locked(now):
        db.commit()
        if user.locked_until is None:
            message = "Your account is locked. Ask your administrator to unlock it."
        else:
            minutes = max(1, -(-int((user.locked_until - now).total_seconds()) // 60))
            message = (
                f"Your account is locked after too many failed sign-ins. Try again in {minutes} "
                f"minute{'s' if minutes != 1 else ''}, or ask your administrator to unlock it."
            )
        raise SignInRefused(423, "account_locked", message)
    if not user.is_active:
        db.commit()
        raise SignInRefused(403, "account_deactivated", "This account has been deactivated. Ask your administrator.")
    if user.must_change_password and user.temp_password_expires_at and now > user.temp_password_expires_at:
        db.commit()
        raise SignInRefused(
            401, "temp_password_expired", "Your temporary password has expired. Ask your administrator for a new one."
        )

    _clear_failures(user)
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
    if password_expired(user, policy, now):
        user.must_change_password = True
    return user, policy


def _record_failure(
    db: Session, user: User, policy: SecurityPolicy, *, now: datetime | None = None, client: dict | None = None
) -> bool:
    """Count a wrong password; lock the account when the count reaches the
    threshold within the window. True if it's now locked."""
    now = now or _now()
    window = timedelta(minutes=policy.lockout_window_minutes)
    if user.failed_window_started_at is None or now - user.failed_window_started_at >= window:
        user.failed_login_count, user.failed_window_started_at = 1, now
    else:
        user.failed_login_count += 1
    if not policy.lockout_threshold or user.failed_login_count < policy.lockout_threshold:
        return False
    user.locked_at = now
    user.locked_until = now + timedelta(minutes=policy.lock_minutes) if policy.lock_minutes else None
    user.failed_login_count, user.failed_window_started_at = 0, None
    record_for_user_orgs(
        db,
        "account_locked",
        user,
        by_user=False,
        item=user.email,
        details={"until": user.locked_until.isoformat() if user.locked_until else "unlocked by an admin", **(client or {})},
    )
    return True


def _clear_failures(user: User) -> None:
    user.failed_login_count, user.failed_window_started_at = 0, None
    user.locked_at = user.locked_until = None


def password_expired(user: User, policy: SecurityPolicy, now: datetime) -> bool:
    days = policy.password.expiry_days
    return bool(days and user.password_changed_at and now - user.password_changed_at > timedelta(days=days))


def password_problems(
    db: Session, password: str, policy: SecurityPolicy, *, email: str, user: User | None = None
) -> list[Problem]:
    """How `password` breaks the rule for `user` (or for a new account with
    `email`): length and kinds, and not their current or a recent one."""
    history: list[str] = []
    if user is not None and policy.password.history_count:
        history = db.scalars(
            select(PasswordHistory.hashed_password)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(policy.password.history_count)
        ).all()
    return check_password(
        password,
        policy.password,
        email=email,
        current_hash=user.hashed_password if user else None,
        history_hashes=history,
        required_by=policy.required_by,
    )


def set_password(
    db: Session, user: User, password: str, *, temporary: bool = False, now: datetime | None = None
) -> None:
    """Store a new password (the old one goes to the history). A temporary
    one must be changed at the next sign-in, within TEMP_PASSWORD_DAYS.
    The caller checks it (password_problems) and commits."""
    now = now or _now()
    if user.hashed_password:
        db.add(PasswordHistory(user_id=user.id, hashed_password=user.hashed_password, created_at=now))
        db.flush()
        keep = (
            select(PasswordHistory.id)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(HISTORY_KEPT)
        )
        db.execute(delete(PasswordHistory).where(PasswordHistory.user_id == user.id, PasswordHistory.id.not_in(keep)))
    user.hashed_password = hash_password(password)
    user.password_changed_at = now
    user.must_change_password = temporary
    user.temp_password_expires_at = now + timedelta(days=settings.TEMP_PASSWORD_DAYS) if temporary else None


def change_password(
    db: Session, user: User, current: str, new: str, *, session_id, now: datetime | None = None
) -> None:
    """The user's own change: the current password, then the new one by the
    rule. Ends their other sessions. A wrong current password counts
    towards lockout (and if it locks, ends every session). Commits."""
    now = now or _now()
    # Locked for update, as at sign-in: guesses sent together each count.
    db.refresh(user, with_for_update=True)
    policy = effective_policy(db, user)
    if not (user.hashed_password and verify_password(current, user.hashed_password)):
        if _record_failure(db, user, policy, now=now):
            end_user_sessions(db, user.id, "locked", now=now)
        db.commit()
        raise WrongCurrentPassword("Your current password is not correct")
    problems = password_problems(db, new, policy, email=user.email, user=user)
    if problems:
        raise PasswordRejected(problems)
    set_password(db, user, new, now=now)
    end_user_sessions(db, user.id, "password_changed", except_session_id=session_id, now=now)
    record_for_user_orgs(db, "password_changed", user, item=user.email)
    db.commit()


# No look-alikes (O/0, l/1/I), so it can be read out or copied by hand.
_TEMP_SETS = ("ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!#%+=?@")


def generate_temporary_password(policy: SecurityPolicy) -> str:
    """A random password that satisfies any rule: every kind of character,
    at least 16 long (more if the rule asks)."""
    length = max(16, policy.password.min_length)
    chars = [secrets.choice(s) for s in _TEMP_SETS]
    every = "".join(_TEMP_SETS)
    chars += [secrets.choice(every) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def set_temporary_password(db: Session, user: User, *, now: datetime | None = None) -> str:
    """For an admin's reset (Phase 2e part 2): a new temporary password,
    returned once to show the admin, never stored as typed or logged. Ends
    the user's sessions; the caller records the event and commits."""
    now = now or _now()
    password = generate_temporary_password(effective_policy(db, user))
    set_password(db, user, password, temporary=True, now=now)
    _clear_failures(user)
    end_user_sessions(db, user.id, "password_reset", now=now)
    return password


def unlock(user: User) -> None:
    """An admin's unlock (Phase 2e part 2): the caller records it and commits."""
    _clear_failures(user)

