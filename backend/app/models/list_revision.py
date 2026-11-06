"""Transactional invalidation stamp; no cached records or permissions."""
import uuid
from sqlalchemy import BigInteger, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class OrganizationListRevision(Base):
    __tablename__ = "organization_list_revisions"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    epoch: Mapped[uuid.UUID] = mapped_column(nullable=False, server_default=text("gen_random_uuid()"))
    asset_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    finding_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class OrganizationWorkflowRevision(Base):
    __tablename__ = "organization_workflow_revisions"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
