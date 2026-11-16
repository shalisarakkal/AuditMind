"""Retained catalog releases and organization review decisions, separate from RAG."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ControlCatalog(Base):
    __tablename__ = "control_catalogs"
    __table_args__ = (UniqueConstraint("framework", "content_hash", name="uq_control_catalog_content"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    edition: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    rights: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_transaction: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("(pg_current_xact_id()::text::bigint)"))
    # Retained attribution, not an authorization reference.
    installed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    installed_by_label: Mapped[str] = mapped_column(String(255), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class CatalogControl(Base):
    __tablename__ = "catalog_controls"
    __table_args__ = (UniqueConstraint("catalog_id", "reference", name="uq_catalog_control_reference"),)
    catalog_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("control_catalogs.id", ondelete="RESTRICT"), primary_key=True)
    control_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class FindingControlRule(Base):
    __tablename__ = "finding_control_rules"
    __table_args__ = (
        UniqueConstraint("org_id", "source", "domain", "category", name="uq_finding_control_rule_key"),
        UniqueConstraint("org_id", "id", name="uq_finding_control_rule_org"),
        CheckConstraint("version >= 1 AND (effective_version IS NULL OR (effective_version >= 1 AND effective_version <= version))", name="ck_finding_control_rule_generation"),
        ForeignKeyConstraint(["id", "effective_version"], ["finding_control_decisions.rule_id", "finding_control_decisions.version"],
            name="fk_finding_control_effective", deferrable=True, initially="DEFERRED", use_alter=True),
        ForeignKeyConstraint(["id", "version"], ["finding_control_decisions.rule_id", "finding_control_decisions.version"],
            name="fk_finding_control_latest", deferrable=True, initially="DEFERRED", use_alter=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_version: Mapped[int | None] = mapped_column(Integer)


class FindingControlDecision(Base):
    __tablename__ = "finding_control_decisions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "rule_id"], ["finding_control_rules.org_id", "finding_control_rules.id"], ondelete="CASCADE", name="fk_control_decision_rule_org"),
        UniqueConstraint("rule_id", "version", name="uq_control_decision_version"),
        UniqueConstraint("id", "catalog_id", name="uq_control_decision_catalog"),
        CheckConstraint("version >= 1", name="ck_control_decision_version"),
        CheckConstraint("state IN ('proposed','approved','withdrawn')", name="ck_control_decision_state"),
        CheckConstraint("(state='approved' AND proposal_version=version-1 AND proposal_version IS NOT NULL) OR (state<>'approved' AND proposal_version IS NULL)", name="ck_control_decision_proposal"),
        ForeignKeyConstraint(["rule_id", "proposal_version"], ["finding_control_decisions.rule_id", "finding_control_decisions.version"], name="fk_control_decision_proposal", deferrable=True, initially="DEFERRED"),
        Index("ix_control_decision_org_rule", "org_id", "rule_id", "version"),
        Index("ix_control_decision_catalog", "catalog_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    catalog_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("control_catalogs.id", ondelete="RESTRICT"), nullable=False)
    proposal_version: Mapped[int | None] = mapped_column(Integer)
    created_transaction: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("(pg_current_xact_id()::text::bigint)"))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FindingControlTarget(Base):
    __tablename__ = "finding_control_targets"
    __table_args__ = (
        ForeignKeyConstraint(["decision_id", "catalog_id"], ["finding_control_decisions.id", "finding_control_decisions.catalog_id"], ondelete="CASCADE", name="fk_control_target_decision_catalog"),
        ForeignKeyConstraint(["catalog_id", "control_id"], ["catalog_controls.catalog_id", "catalog_controls.control_id"], ondelete="RESTRICT", name="fk_control_target_revision"),
        Index("ix_control_target_catalog_control", "catalog_id", "control_id"),
    )
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    catalog_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    control_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
