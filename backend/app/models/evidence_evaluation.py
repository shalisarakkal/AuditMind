"""Durable compute jobs; results authorize scores only at the captured revision."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class OrganizationEvidenceRevision(Base):
    __tablename__ = "organization_evidence_revisions"
    __table_args__ = (CheckConstraint("revision >= 0", name="ck_evidence_revision"),)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")


class EvidenceEvaluation(Base):
    __tablename__ = "evidence_evaluations"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','failed','cancelled','superseded')", name="ck_evidence_evaluation_status"),
        CheckConstraint("retry_count >= 0", name="ck_evidence_evaluation_retries"),
        Index("ix_evidence_evaluation_pending", "created_at", postgresql_where=text("status='pending'")),
        Index("uq_evidence_evaluation_active_org", "org_id", unique=True, postgresql_where=text("status IN ('pending','running')")),
        Index("ix_evidence_evaluation_org_created", "org_id", "created_at"),
        Index("ix_evidence_evaluation_cache", "org_id", "captured_revision", postgresql_where=text("status='completed'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    started_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    captured_revision: Mapped[int | None] = mapped_column(BigInteger)
    policy_identity: Mapped[str | None] = mapped_column(String(64))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
