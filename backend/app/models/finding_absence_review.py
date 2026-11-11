"""Durable snapshots of absence-review candidates, independent of source retention."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class FindingAbsenceReviewBatch(Base):
    __tablename__ = "finding_absence_review_batches"
    __table_args__ = (
        Index("ix_finding_absence_review_batches_actor", "actor_id"),
        UniqueConstraint("org_id", "batch_key", name="uq_finding_absence_review_batch_key"),
        Index("ix_finding_absence_review_batches_org_created", "org_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    current_scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    baseline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FindingAbsenceReviewItem(Base):
    __tablename__ = "finding_absence_review_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "finding_id", name="uq_finding_absence_review_candidate"),
        Index("ix_finding_absence_review_items_org_batch", "org_id", "batch_id", "id"),
        Index("ix_finding_absence_review_items_org_created", "org_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("finding_absence_review_batches.id", ondelete="CASCADE"), nullable=False)
    # Historical identifiers intentionally have no source-row foreign keys.
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    baseline_observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    candidate: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FindingAbsenceReviewDecision(Base):
    __tablename__ = "finding_absence_review_decisions"
    __table_args__ = (
        Index("ix_finding_absence_review_decisions_actor", "actor_id"),
        UniqueConstraint("item_id", "version", name="uq_finding_absence_review_decision_version"),
        CheckConstraint("version > 0", name="ck_finding_absence_review_decision_version"),
        CheckConstraint("state IN ('kept_active','reopened')", name="ck_finding_absence_review_decision_state"),
        Index("ix_finding_absence_review_decisions_org_item", "org_id", "item_id", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("finding_absence_review_items.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
