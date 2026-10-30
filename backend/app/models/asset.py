import uuid
from datetime import datetime, timezone

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

# The partial indexes' condition: queries over active rows must say
# `archived_at IS NULL` to use them.
ACTIVE = text("archived_at IS NULL")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        *[Index(f"ix_assets_{column}_trgm", column, postgresql_using="gin",
                postgresql_ops={column: "gin_trgm_ops"}) for column in ("hostname", "ip", "cloud_id")],
        # Import matching: by cloud ID, else hostname (case-insensitive) and
        # category, else IP (see import_matching.py). Active assets only.
        Index("ix_assets_org_hostname", "org_id", text("lower(hostname)"), postgresql_where=ACTIVE),
        Index("ix_assets_org_ip", "org_id", "ip", postgresql_where=ACTIVE),
        Index("ix_assets_org_cloud_id", "org_id", "cloud_id", postgresql_where=ACTIVE),
        # Exact active-row counts without traversing hostname/IP payload keys.
        Index("ix_assets_active_org_count", "org_id", postgresql_where=ACTIVE),
        # Restoring or purging an archive batch.
        Index("ix_assets_archive_batch", "archive_batch_id", postgresql_where=text("archive_batch_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # A category (see app/services/asset_types.py); subtype keeps the source's
    # own name for it, e.g. type "workstation", subtype "laptop".
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(100))
    # False when the type is a guess, not read from a file or given by a user:
    # a profile's default (endpoint agents -> workstation), an unrecognised OS,
    # or the placeholder for a finding's unknown host. Import matching treats
    # a guessed asset as any category, and a known type replaces the guess.
    type_known: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    hostname: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    cloud_id: Mapped[str | None] = mapped_column(String(255))
    environment: Mapped[str | None] = mapped_column(String(50))
    criticality: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    # Extra facts from profile imports (OS, open ports, agent version...),
    # merged on re-import. Always reassign, never mutate in place.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Archived (Phase 2d part 2): hidden everywhere until restored or purged;
    # archive_batch_id is the archive action that took it (see models/archive.py).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archive_batches.id", ondelete="SET NULL")
    )

    organization: Mapped["Organization"] = relationship(back_populates="assets")
    findings: Mapped[list["Finding"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
