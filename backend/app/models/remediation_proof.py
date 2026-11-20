"""Retained remediation proof decisions, independent of scoring authority."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class RemediationProof(Base):
    __tablename__ = "remediation_proofs"
    __table_args__ = (
        UniqueConstraint("org_id", "finding_id", "version", name="uq_remediation_proof_version"),
        CheckConstraint("version >= 1 AND workflow_version >= 0", name="ck_remediation_proof_version"),
        CheckConstraint("state IN ('pending','approved','rejected')", name="ck_remediation_proof_state"),
        Index("ix_remediation_proofs_finding_id", "finding_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitter_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    submitter_label: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
