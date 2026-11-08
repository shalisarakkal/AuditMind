"""Append-only canonical selections, independent of source-row retention."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class FindingCanonicalDecision(Base):
    __tablename__ = "finding_canonical_decisions"
    __table_args__ = (
        UniqueConstraint("org_id", "pair_key", "version", name="uq_finding_canonical_version"),
        CheckConstraint("version > 0", name="ck_finding_canonical_version"),
        CheckConstraint("state IN ('selected','revoked')", name="ck_finding_canonical_state"),
        CheckConstraint("finding_a_id <> finding_b_id AND canonical_finding_id IN (finding_a_id,finding_b_id)", name="ck_finding_canonical_members"),
        Index("ix_finding_canonical_a", "org_id", "finding_a_id", "created_at"),
        Index("ix_finding_canonical_b", "org_id", "finding_b_id", "created_at"),
        Index("ix_finding_canonical_actor", "actor_id"),
        Index("ix_finding_canonical_identity", "org_id", text("(context ->> 'candidate_key')"), "pair_key", "version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    pair_key: Mapped[str] = mapped_column(String(73), nullable=False)
    # Historical UUIDs deliberately survive finding/scan/observation purge.
    finding_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
