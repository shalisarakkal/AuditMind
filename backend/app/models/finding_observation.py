"""Import occurrences, separate from remediation history; retained with the finding."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class FindingObservation(Base):
    __tablename__ = "finding_observations"
    __table_args__ = (
        UniqueConstraint("import_id", "occurrence", name="uq_finding_observation_occurrence"),
        Index("ix_finding_observations_page", "org_id", "finding_id", "recorded_at", "id"),
        Index("ix_finding_observations_finding", "finding_id"),
        Index("ix_finding_observations_scan", "scan_id"),
        Index("ix_finding_observations_org_scan_finding", "org_id", "scan_id", "finding_id"),
        Index("ix_finding_observations_source_asset", "org_id", text("(asset_identity->>'asset_id')"), "finding_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"))
    # Immutable import UUID survives deletion of the source scan; live link may be null.
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"))
    occurrence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(100), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(100))
    filename: Mapped[str | None] = mapped_column(String(255))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset_identity: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_identity: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reconciliation_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ineligibility_reasons: Mapped[list] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    @property
    def identity_assessment(self) -> dict:
        """Read-time diagnostics; never retrofit identity authority onto history."""
        from app.services.finding_identity import assess_identity
        return assess_identity(org_id=self.org_id, scan_type=self.scan_type,
            source=self.source, profile=self.profile,
            raw=self.source_identity or {}).snapshot()
