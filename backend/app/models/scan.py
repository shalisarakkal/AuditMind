import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.enums import ScanStatus


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    scan_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ScanStatus] = mapped_column(str_enum(ScanStatus), default=ScanStatus.pending, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(100))
    # File imports: the uploaded filename and the per-row import report.
    filename: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[dict | None] = mapped_column(JSONB)

    organization: Mapped["Organization"] = relationship(back_populates="scans")
    findings: Mapped[list["Finding"]] = relationship(back_populates="scan", cascade="all, delete-orphan")
