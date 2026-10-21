import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    # Emails are stored lower-cased (schemas lower-case them on the way in),
    # so one address can't become two accounts.
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
        UniqueConstraint("email", name="users_email_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(String(50), default="local", nullable=False)
    # A hash, the same length whatever the password (services/accounts.py).
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # False: deactivated by the Sysadmin; can't sign in, sessions ended.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # The platform's Sysadmin (Phase 2e part 3).
    is_sysadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_now)
    # Set with a temporary password, or when the password has expired: every
    # page but Change password is refused until it's changed.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # A temporary password can't be used to sign in after this.
    temp_password_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lockout: failed sign-ins counted since failed_window_started_at.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    failed_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Locked since locked_at, until locked_until; no locked_until: until an
    # admin unlocks it.
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["OrgMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def is_locked(self, now: datetime) -> bool:
        return self.locked_at is not None and (self.locked_until is None or self.locked_until > now)
