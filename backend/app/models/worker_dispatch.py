"""Small durable fair-scheduling state, independent of inventory size."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class WorkerDispatch(Base):
    __tablename__ = "worker_dispatch"
    scope_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    last_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
