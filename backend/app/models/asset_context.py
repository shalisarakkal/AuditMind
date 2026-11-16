"""Organization-managed context, independent of imported scanner attributes."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base

class AssetContext(Base):
    __tablename__ = "asset_contexts"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_asset_context_version"),
        CheckConstraint("business_criticality IS NULL OR business_criticality IN ('critical','high','medium','low')", name="ck_asset_context_criticality"),
        Index("ix_asset_context_owner_org", "owner_id", "org_id", postgresql_where=text("owner_id IS NOT NULL")),
        *[Index(f"ix_asset_context_org_{field}", "org_id", field, "asset_id") for field in ("owner_id","environment","business_criticality")],
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # Retain the reviewed identity/label after membership or account removal.
    # This reference never grants access; current assignment is validated separately.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner_label: Mapped[str | None] = mapped_column(String(255))
    environment: Mapped[str | None] = mapped_column(String(50))
    business_criticality: Mapped[str | None] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

class AssetContextHistory(Base):
    __tablename__ = "asset_context_history"
    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_asset_context_history_version"),
        Index("ix_asset_context_history_org_asset", "org_id", "asset_id", "version"),
        Index("ix_asset_context_history_actor", "actor_id", postgresql_where=text("actor_id IS NOT NULL")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    before: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class OrganizationAssetContextRevision(Base):
    __tablename__ = "organization_asset_context_revisions"
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
