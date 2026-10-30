import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("dashboard_refresh_interval_seconds IS NULL OR dashboard_refresh_interval_seconds BETWEEN 60 AND 86400", name="organization_dashboard_refresh_interval"),
        CheckConstraint("dashboard_refresh_settings_version >= 0", name="organization_dashboard_refresh_version"),
        CheckConstraint("header_logo_size IN ('small', 'medium', 'large')", name="organization_header_logo_size"),
        CheckConstraint("header_name_size IN ('small', 'medium', 'large')", name="organization_header_name_size"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dashboard_refresh_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    dashboard_refresh_settings_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    show_name_in_header: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    header_logo_size: Mapped[str] = mapped_column(String(6), nullable=False, default="medium", server_default=text("'medium'"))
    header_name_size: Mapped[str] = mapped_column(String(6), nullable=False, default="medium", server_default=text("'medium'"))
    industry: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Per-org overrides of the .env ingestion defaults; only overridden keys are
    # stored (see app/services/org_settings.py). Always reassign, never mutate
    # in place, so SQLAlchemy sees the change.
    ingestion_overrides: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # The org's changes to the platform's security settings (idle time,
    # lockout, password rule); only changed keys are stored, like
    # ingestion_overrides (see app/services/security_policy.py).
    security_settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    # Archived by the Sysadmin: read-only for everyone, until restored or
    # purged (Phase 2e part 3).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Being purged: gone for everyone; the background worker deletes its
    # data in chunks, then the org itself.
    purge_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    @property
    def status(self) -> str:
        if self.purge_requested_at is not None:
            return "purging"
        return "archived" if self.archived_at is not None else "active"

    memberships: Mapped[list["OrgMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    scans: Mapped[list["Scan"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    import_profiles: Mapped[list["ImportProfile"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
