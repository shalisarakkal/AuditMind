"""Security settings: how long a sign-in lasts, lockout, and the password
rule (PLAN.md, Phase 2e "Security settings per organization").

Three layers, each storing only what it changes:
- the built-in values (SecuritySettings' defaults);
- the platform defaults, set by the Sysadmin (platform_settings "security");
- each org's changes (organizations.security_settings), set by its admins.

The password, sign-in and lockout belong to the account, not to one org, so
for someone in several orgs each setting takes its strictest value among
them (effective_policy), and remembers which org asked for it, so a message
can say "Acme requires passwords of at least 16 characters".

Every limit is read through effective_policy (or resolve_org_security for
one org).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.session import PlatformSetting
from app.models.user import User

PasswordRule = Literal["simple", "complex"]

# The Simple rule: length only.
SIMPLE_MIN_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
PLATFORM_KEY = "security"


class SecuritySettings(BaseModel):
    """One layer's settings, within the ranges admins may choose from. The
    defaults are the built-in values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Signed out after this long with nothing done (minutes).
    idle_minutes: int = Field(480, ge=10, le=600)
    # The longest a sign-in lasts, active or not (days).
    max_session_days: int = Field(7, ge=2, le=10)
    # Failed sign-ins before the account locks; 0: it never locks.
    lockout_threshold: int = 5
    # The failures are counted over this many minutes.
    lockout_window_minutes: int = Field(15, ge=10, le=20)
    # How long the lock lasts (minutes); 0: until an admin unlocks it.
    lock_minutes: int = 15
    password_rule: PasswordRule = "simple"
    # The Complex rule's own settings (Simple ignores them).
    min_length: int = Field(14, ge=SIMPLE_MIN_LENGTH, le=64)
    require_upper: bool = True
    require_lower: bool = True
    require_digit: bool = True
    require_symbol: bool = True
    # Not one of the last N passwords (0: only not the current one).
    history_count: int = Field(5, ge=0, le=24)
    # Days before a password must be changed; 0: never.
    expiry_days: int = 0

    @field_validator("lockout_threshold")
    @classmethod
    def _threshold(cls, value: int) -> int:
        if value != 0 and not 3 <= value <= 6:
            raise ValueError("must be 0 (never lock) or 3 to 6")
        return value

    @field_validator("lock_minutes")
    @classmethod
    def _lock(cls, value: int) -> int:
        if value != 0 and not 10 <= value <= 20:
            raise ValueError("must be 0 (until an admin unlocks) or 10 to 20")
        return value

    @field_validator("expiry_days")
    @classmethod
    def _expiry(cls, value: int) -> int:
        if value != 0 and not 30 <= value <= 365:
            raise ValueError("must be 0 (never) or 30 to 365")
        return value


@dataclass(frozen=True)
class PasswordRules:
    """What a new password must satisfy (services/password_policy.py)."""

    rule: PasswordRule = "simple"
    min_length: int = SIMPLE_MIN_LENGTH
    max_length: int = MAX_PASSWORD_LENGTH
    require_upper: bool = False
    require_lower: bool = False
    require_digit: bool = False
    require_symbol: bool = False
    history_count: int = 0
    expiry_days: int = 0


@dataclass(frozen=True)
class SecurityPolicy:
    """The settings that apply to one account."""

    idle_minutes: int
    max_session_days: int
    lockout_threshold: int
    lockout_window_minutes: int
    lock_minutes: int
    password: PasswordRules
    # Setting name -> the org whose stricter value applies (only when the
    # account's orgs differ on it).
    required_by: dict[str, str] = field(default_factory=dict)


def password_rules(settings: SecuritySettings) -> PasswordRules:
    if settings.password_rule == "simple":
        return PasswordRules()
    return PasswordRules(
        rule="complex",
        min_length=settings.min_length,
        require_upper=settings.require_upper,
        require_lower=settings.require_lower,
        require_digit=settings.require_digit,
        require_symbol=settings.require_symbol,
        history_count=settings.history_count,
        expiry_days=settings.expiry_days,
    )


# Per setting: how strict a value is (higher wins). 0 means "never" for the
# lockout threshold and expiry (the least strict), and "until an admin
# unlocks" for the lock (the most strict).
_STRICTNESS: dict[str, Callable[[object], float]] = {
    "idle_minutes": lambda v: -v,
    "max_session_days": lambda v: -v,
    "lockout_threshold": lambda v: -v if v else -math.inf,
    "lockout_window_minutes": lambda v: v,
    "lock_minutes": lambda v: v if v else math.inf,
    "rule": lambda v: v == "complex",
    "min_length": lambda v: v,
    "require_upper": lambda v: v,
    "require_lower": lambda v: v,
    "require_digit": lambda v: v,
    "require_symbol": lambda v: v,
    "history_count": lambda v: v,
    "expiry_days": lambda v: -v if v else -math.inf,
}
# The password rule's settings (the rest are the session's and lockout's).
_PASSWORD_FIELDS = {f.name for f in fields(PasswordRules)} & set(_STRICTNESS)


def _flatten(settings: SecuritySettings) -> dict:
    rules = password_rules(settings)
    flat = {name: getattr(settings, name) for name in _STRICTNESS if name not in _PASSWORD_FIELDS}
    flat.update({name: getattr(rules, name) for name in _PASSWORD_FIELDS})
    return flat


def combine(layers: list[tuple[str | None, SecuritySettings]]) -> SecurityPolicy:
    """The strictest of each setting among `layers` (org name, its settings)."""
    flats = [(name, _flatten(settings)) for name, settings in layers]
    chosen: dict = {}
    required_by: dict[str, str] = {}
    for setting, strictness in _STRICTNESS.items():
        name, flat = max(flats, key=lambda entry: strictness(entry[1][setting]))
        chosen[setting] = flat[setting]
        if name and any(other[setting] != flat[setting] for _, other in flats):
            required_by[setting] = name
    return SecurityPolicy(
        **{name: value for name, value in chosen.items() if name not in _PASSWORD_FIELDS},
        password=PasswordRules(**{name: chosen[name] for name in _PASSWORD_FIELDS}),
        required_by=required_by,
    )


def apply_changes(base: SecuritySettings, changes: dict | None) -> SecuritySettings:
    """`base` with a layer's stored changes over it. (Clearing a change, back
    to the layer below, is removing its key: Part 3's settings screens.)"""
    return SecuritySettings.model_validate({**base.model_dump(), **(changes or {})})


def resolve_platform_security(db: Session) -> SecuritySettings:
    row = db.get(PlatformSetting, PLATFORM_KEY)
    return apply_changes(SecuritySettings(), row.value if row else None)


def resolve_org_security(
    db: Session, org: Organization, platform: SecuritySettings | None = None
) -> SecuritySettings:
    return apply_changes(platform or resolve_platform_security(db), org.security_settings)


def effective_policy(db: Session, user: User | None) -> SecurityPolicy:
    """The settings for `user`: the strictest among their orgs; the platform
    defaults for someone in none (the Sysadmin), or no one (an unknown email)."""
    platform = resolve_platform_security(db)
    orgs = []
    if user is not None:
        orgs = db.scalars(
            select(Organization)
            .join(OrgMembership, OrgMembership.org_id == Organization.id)
            .where(OrgMembership.user_id == user.id)
            .order_by(Organization.name)
        ).all()
    if not orgs:
        return combine([(None, platform)])
    return combine([(org.name, resolve_org_security(db, org, platform)) for org in orgs])


def change_layer(base: SecuritySettings, stored: dict | None, changes: dict) -> tuple[dict, SecuritySettings]:
    """A layer's stored changes after `changes` (a value sets a setting,
    None goes back to the layer below), and the settings that results.
    Raises ValueError for an unknown setting, and pydantic's
    ValidationError for a value out of range (the whole result is checked,
    so the Complex rule's settings are too)."""
    unknown = set(changes) - set(SecuritySettings.model_fields)
    if unknown:
        raise ValueError(f"Unknown setting: {', '.join(sorted(unknown))}")
    new = dict(stored or {})
    for key, value in changes.items():
        if value is None:
            new.pop(key, None)
        else:
            new[key] = value
    effective = apply_changes(base, new)
    # Kept as the validated values (e.g. "15" stored as 15).
    return {key: getattr(effective, key) for key in new}, effective
