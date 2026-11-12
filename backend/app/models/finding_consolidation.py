"""Retained consolidation ledger. Rows alone confer no visibility authority."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class FindingConsolidation(Base):
    __tablename__ = "finding_consolidations"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_consolidation_owner"),
        UniqueConstraint("org_id", "pair_key", name="uq_consolidation_pair"),
        CheckConstraint("version > 0", name="ck_consolidation_version"),
        CheckConstraint("state IN ('active','undone')", name="ck_consolidation_state"),
        CheckConstraint("finding_a_id <> finding_b_id AND canonical_finding_id IN (finding_a_id,finding_b_id)", name="ck_consolidation_members"),
        Index("uq_consolidation_active_identity", "org_id", "identity_version", "candidate_key", unique=True, postgresql_where=text("state = 'active'")),
        Index("ix_consolidation_page", "org_id", "created_at", "id"),
        Index("ix_consolidation_a", "org_id", "finding_a_id"),
        Index("ix_consolidation_b", "org_id", "finding_b_id"),
        Index("ix_consolidation_tool", "org_id", "tool_id"),
        Index("ix_consolidation_asset", "org_id", "canonical_asset_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    pair_key: Mapped[str] = mapped_column(String(73), nullable=False)
    # Historical source/identity UUIDs are not cascading ownership links.
    finding_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(50), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FindingConsolidationDecision(Base):
    __tablename__ = "finding_consolidation_decisions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "consolidation_id"], ["finding_consolidations.org_id", "finding_consolidations.id"], ondelete="CASCADE", name="fk_consolidation_decision_owner"),
        UniqueConstraint("org_id", "consolidation_id", "version", name="uq_consolidation_generation_owner"),
        UniqueConstraint("org_id", "request_id", name="uq_consolidation_request"),
        UniqueConstraint("consolidation_id", "version", name="uq_consolidation_decision_version"),
        CheckConstraint("version > 0", name="ck_consolidation_decision_version"),
        CheckConstraint("state IN ('active','undone')", name="ck_consolidation_decision_state"),
        CheckConstraint("length(btrim(rationale)) BETWEEN 1 AND 2000", name="ck_consolidation_rationale"),
        Index("ix_consolidation_history", "org_id", "consolidation_id", "version"),
        Index("ix_consolidation_actor", "actor_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consolidation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FindingConsolidationMember(Base):
    """Reserved current-generation membership. No production writer exists yet.

    Resource UUIDs are references, not cascading ownership links. Future writes
    must validate tenant ownership and exact pair/role agreement under locks.
    Rows alone do not hide findings or authorize any operation.
    """
    __tablename__ = "finding_consolidation_members"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "consolidation_id", "generation"],
            ["finding_consolidation_decisions.org_id", "finding_consolidation_decisions.consolidation_id",
             "finding_consolidation_decisions.version"], ondelete="CASCADE", name="fk_consolidation_member_generation"),
        UniqueConstraint("org_id", "finding_id", name="uq_consolidation_current_member"),
        UniqueConstraint("org_id", "consolidation_id", "role", name="uq_consolidation_member_role"),
        CheckConstraint("generation > 0", name="ck_consolidation_member_generation"),
        CheckConstraint("role IN ('canonical','alias')", name="ck_consolidation_member_role"),
        Index("ix_consolidation_members_group", "org_id", "consolidation_id", "generation"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consolidation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)


class FindingConsolidationDependency(Base):
    """Retained typed source references per decision generation, without payloads.

    Source deletion does not erase this audit manifest. Future lifecycle guards
    must consult the active generation before allowing source mutations.
    """
    __tablename__ = "finding_consolidation_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "consolidation_id", "generation"],
            ["finding_consolidation_decisions.org_id", "finding_consolidation_decisions.consolidation_id",
             "finding_consolidation_decisions.version"], ondelete="CASCADE", name="fk_consolidation_dependency_generation"),
        UniqueConstraint("org_id", "consolidation_id", "generation", "resource_kind", "resource_id",
            name="uq_consolidation_dependency"),
        CheckConstraint("generation > 0", name="ck_consolidation_dependency_generation"),
        CheckConstraint("resource_kind IN ('finding','observation','scan','asset','tool','identity_binding','canonical_decision')",
            name="ck_consolidation_dependency_kind"),
        CheckConstraint("resource_version IS NULL OR resource_version > 0", name="ck_consolidation_dependency_version"),
        Index("ix_consolidation_dependency_resource", "org_id", "resource_kind", "resource_id", "consolidation_id", "generation"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consolidation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource_version: Mapped[int | None] = mapped_column(Integer)
