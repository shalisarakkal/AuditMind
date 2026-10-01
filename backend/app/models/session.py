import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserSession(Base):
    """One sign-in: from login until sign-out, a limit, or being ended (a
    password change, an admin). Checked on every request, so ending it takes
    effect at once (services/sessions.py)."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_open", "user_id", postgresql_where=text("revoked_at IS NULL")),
    )

    # The access token's "sid".
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 of the cookie's random value; the value itself isn't stored.
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    # Last time the person did something (not the app's own polling).
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    # The longest sign-in, and the idle limit: from the security settings at
    # sign-in, brought up to date at each renewal.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # signout, idle, expired, password_changed, password_reset, deactivated...
    revoked_reason: Mapped[str | None] = mapped_column(String(30))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship()


class PasswordHistory(Base):
    """A user's previous password hashes, for the Complex rule's "not one of
    the last N"; the newest 24 are kept."""

    __tablename__ = "password_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class PlatformSetting(Base):
    """Platform-wide settings the Sysadmin sets in the app, by key (e.g.
    "security": the security settings' platform defaults, only the keys
    changed from the built-in values)."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
