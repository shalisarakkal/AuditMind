import uuid

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class OrganizationLogo(Base):
    __tablename__ = "organization_logos"
    __table_args__ = (CheckConstraint("octet_length(image) BETWEEN 1 AND 1048576", name="organization_logo_size"),)

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[str] = mapped_column(String(36), nullable=False)
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
