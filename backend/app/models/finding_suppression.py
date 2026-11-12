"""Identity-scoped suppression ledger, independent of source-row retention.

Only the later disposition publisher may authorize mutations. These records
alone never change active lists, workflow or scoring.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class FindingSuppression(Base):
    __tablename__ = "finding_suppressions"
    __table_args__ = (
        UniqueConstraint("org_id", "identity_version", "candidate_key", name="uq_finding_suppression_identity"),
        UniqueConstraint("org_id", "id", name="uq_finding_suppression_owner"),
        CheckConstraint("version > 0", name="ck_finding_suppression_version"),
        CheckConstraint("state IN ('suppressed','cleared')", name="ck_finding_suppression_state"),
        Index("ix_finding_suppressions_source", "org_id", "source_fingerprint", "state"),
        Index("ix_finding_suppressions_org_state_page", "org_id", "state", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(50), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    reappearance_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    identity: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Historical identifiers intentionally have no live/source foreign keys.
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FindingSuppressionDecision(Base):
    __tablename__ = "finding_suppression_decisions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "suppression_id"], ["finding_suppressions.org_id", "finding_suppressions.id"], ondelete="CASCADE", name="fk_suppression_decision_owner"),
        UniqueConstraint("org_id", "request_id", name="uq_suppression_decision_request"),
        UniqueConstraint("suppression_id", "version", name="uq_suppression_decision_version"),
        CheckConstraint("version > 0", name="ck_suppression_decision_version"),
        CheckConstraint("state IN ('suppressed','cleared')", name="ck_suppression_decision_state"),
        CheckConstraint("length(btrim(rationale)) BETWEEN 1 AND 2000", name="ck_suppression_decision_rationale"),
        Index("ix_suppression_decisions_org_history", "org_id", "suppression_id", "version"),
        Index("ix_suppression_decisions_actor", "actor_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suppression_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class OrganizationSuppressionRevision(Base):
    __tablename__ = "organization_suppression_revisions"
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class FindingSuppressionReappearance(Base):
    __tablename__ = "finding_suppression_reappearances"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "suppression_id"], ["finding_suppressions.org_id", "finding_suppressions.id"], ondelete="CASCADE", name="fk_suppression_reappearance_owner"),
        UniqueConstraint("org_id", "suppression_id", "observation_id", name="uq_suppression_reappearance"),
        Index("ix_suppression_reappearance_history", "org_id", "suppression_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suppression_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    filename: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
