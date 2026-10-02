import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.asset import ACTIVE
from app.models.enums import Domain, Severity


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        # The findings list (newest first) and an import's duplicate check,
        # which loads the org's findings once. Active findings only.
        Index("ix_findings_org_created", "org_id", "created_at", postgresql_where=ACTIVE),
        # The dashboard's most severe findings, newest first; the findings list.
        Index("ix_findings_org_severity_created", "org_id", "severity", "created_at", postgresql_where=ACTIVE),
        # Deleting an asset or scan cascades to its findings; archiving one
        # archives them.
        Index("ix_findings_asset", "asset_id"),
        Index("ix_findings_scan", "scan_id"),
        # Restoring or purging an archive batch.
        Index("ix_findings_archive_batch", "archive_batch_id", postgresql_where=text("archive_batch_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE")
    )
    category: Mapped[str | None] = mapped_column(String(100))
    domain: Mapped[Domain] = mapped_column(str_enum(Domain), nullable=False)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(String(100))
    # A finding that sums an event log's events up (Phase 2f part 2): how
    # many, first and last seen, and details (top actors and scopes,
    # examples). Empty for other findings.
    event_count: Mapped[int | None] = mapped_column(Integer)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Archived (Phase 2d part 2): hidden everywhere until restored or purged;
    # archive_batch_id is the archive action that took it (see models/archive.py).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archive_batches.id", ondelete="SET NULL")
    )

    scan: Mapped["Scan"] = relationship(back_populates="findings")
    asset: Mapped["Asset"] = relationship(back_populates="findings")
