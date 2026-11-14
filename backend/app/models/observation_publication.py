"""Reserved Stage B storage. These rows do not authorize field publication."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ObservationPublicationDecision(Base):
    """Minimal retained receipt; full scanner data belongs only in snapshots."""
    __tablename__ = "observation_publication_decisions"
    __table_args__ = (
        UniqueConstraint("org_id", "finding_id", "version", name="uq_observation_publication_version"),
        UniqueConstraint("org_id", "request_id", name="uq_observation_publication_request"),
        UniqueConstraint("org_id", "id", name="uq_observation_publication_owner"),
        UniqueConstraint("org_id", "finding_id", "id", name="uq_publication_snapshot_target"),
        UniqueConstraint("org_id", "finding_id", "id", "version", name="uq_publication_state_target"),
        CheckConstraint("version > 0", name="ck_observation_publication_version"),
        CheckConstraint("operation IN ('publish','undo')", name="ck_observation_publication_operation"),
        CheckConstraint("length(btrim(rationale)) BETWEEN 1 AND 2000", name="ck_observation_publication_rationale"),
        CheckConstraint("length(request_hash) = 64 AND length(before_hash) = 64 AND length(after_hash) = 64", name="ck_observation_publication_hashes"),
        CheckConstraint("source_context_hash IS NULL OR length(source_context_hash) = 64", name="ck_publication_source_hash"),
        # The unique finding/version index also serves ordered history reads.
        Index("ix_observation_publication_actor", "actor_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # Historical UUIDs intentionally survive finding/source purge.
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    before_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    after_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(80), nullable=False)
    admission_contract: Mapped[str] = mapped_column(String(80), nullable=False,
        default='reserved-storage-v1', server_default=text("'reserved-storage-v1'"))
    source_context_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ObservationPublicationSnapshot(Base):
    """Source-owned payload; either finding or supplying scan purge removes it."""
    __tablename__ = "observation_publication_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "finding_id", "decision_id"], ["observation_publication_decisions.org_id", "observation_publication_decisions.finding_id", "observation_publication_decisions.id"], ondelete="CASCADE", name="fk_publication_snapshot_decision"),
        UniqueConstraint("org_id", "decision_id", "side", name="uq_publication_snapshot_side"),
        CheckConstraint("side IN ('before','after')", name="ck_publication_snapshot_side"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_publication_snapshot_object"),
        Index("ix_publication_snapshot_finding", "finding_id"),
        Index("ix_publication_snapshot_scan", "source_scan_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False)
    source_scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    side: Mapped[str] = mapped_column(String(6), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ObservationPublicationState(Base):
    """One retained generation per target; no Finding pointer/index rebuild needed."""
    __tablename__ = "observation_publication_states"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "finding_id", "decision_id", "version"], ["observation_publication_decisions.org_id", "observation_publication_decisions.finding_id", "observation_publication_decisions.id", "observation_publication_decisions.version"], ondelete="CASCADE", name="fk_publication_state_decision"),
        CheckConstraint("version > 0", name="ck_publication_state_version"),
        CheckConstraint("state IN ('active','undone')", name="ck_publication_state"),
        Index("ix_publication_state_active", "org_id", "decision_id", postgresql_where=text("state = 'active'")),
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)


class ObservationPublicationDependency(Base):
    """Indexed historical IDs; future guards must join the active generation."""
    __tablename__ = "observation_publication_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "decision_id"], ["observation_publication_decisions.org_id", "observation_publication_decisions.id"], ondelete="CASCADE", name="fk_publication_dependency_decision"),
        UniqueConstraint("org_id", "decision_id", "resource_kind", "resource_id", name="uq_publication_dependency"),
        CheckConstraint("resource_kind IN ('finding','observation','scan','asset','tool','identity_binding')", name="ck_publication_dependency_kind"),
        Index("ix_publication_dependency_resource", "org_id", "resource_kind", "resource_id", "decision_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class OrganizationPublicationSettings(Base):
    """Separate default-off policy; enabling it alone never opens a writer."""
    __tablename__ = 'organization_publication_settings'
    __table_args__ = (CheckConstraint('version >= 0', name='ck_publication_settings_version'),)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('false'))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
