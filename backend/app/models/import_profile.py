import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ImportProfile(Base):
    """An org's own copy of a built-in import profile, with its column names
    and rule settings adjusted (see app/services/import_profiles.py). JSONB
    columns: always reassign, never mutate in place."""

    __tablename__ = "import_profiles"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_import_profiles_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Which built-in processor reads the file (endpoint_agent, network_scan...).
    family: Mapped[str] = mapped_column(String(50), nullable=False)
    # Field -> column header in the file.
    column_map: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    # The family's rule settings (thresholds, maps, default values...).
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    organization: Mapped["Organization"] = relationship(back_populates="import_profiles")
