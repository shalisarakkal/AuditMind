import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.enums import Domain, Severity


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        # The findings list (newest first) and an import's duplicate check,
        # which loads the org's findings once.
        Index("ix_findings_org_created", "org_id", "created_at"),
        # The dashboard's most severe findings, newest first.
        Index("ix_findings_org_severity_created", "org_id", "severity", "created_at"),
        # Deleting an asset or scan cascades to its findings.
        Index("ix_findings_asset", "asset_id"),
        Index("ix_findings_scan", "scan_id"),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    scan: Mapped["Scan"] = relationship(back_populates="findings")
    asset: Mapped["Asset"] = relationship(back_populates="findings")
