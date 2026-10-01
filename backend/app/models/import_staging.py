import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Staging for imports the background worker runs (services/import_staging.py).
# UNLOGGED: much cheaper to write, and after a database crash both tables
# come back empty together, so an import simply reads its file again.


class ImportStagingState(Base):
    """How far reading an upload has got, and its report so far."""

    __tablename__ = "import_staging_state"
    __table_args__ = {"prefixes": ["UNLOGGED"]}

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    # The settings and format it was read with: changed, it's read again.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class ImportStagingChunk(Base):
    """The checked rows of a stretch of the file, in file order."""

    __tablename__ = "import_staging_chunks"
    __table_args__ = {"prefixes": ["UNLOGGED"]}

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
