"""Staged live-dashboard qualification registry; drafts grant no scoring authority."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.enums import Domain


class OrganizationScoringSettings(Base):
    __tablename__ = "organization_scoring_settings"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_scoring_settings_version"),)

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    evidence_qualified_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class DomainEvidenceQualification(Base):
    __tablename__ = "domain_evidence_qualifications"
    __table_args__ = (
        UniqueConstraint("org_id", "domain", name="uq_qualification_org_domain"),
        CheckConstraint("version >= 1", name="ck_qualification_version"),
        CheckConstraint("status IN ('draft','approved','revoked','conflicting')", name="ck_qualification_status"),
        CheckConstraint("expires_at IS NULL OR (reviewed_at IS NOT NULL AND expires_at > reviewed_at AND expires_at <= reviewed_at + interval '2160 hours')", name="ck_qualification_expiry"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[Domain] = mapped_column(str_enum(Domain, length=50), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", server_default="draft")
    scope: Mapped[str] = mapped_column(String(2000), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    observations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    inventory_sha256: Mapped[str | None] = mapped_column(String(64))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", name="fk_qualification_reviewer"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    review_attestation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
