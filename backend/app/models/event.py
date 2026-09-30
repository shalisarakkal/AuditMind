"""Activity: AuditMind's own record of what happened in an organization (Phase
2d part 3). One row per action, written when it ends, in the same transaction
as the change it describes, and never changed afterwards. Kept
EVENT_RETENTION_DAYS (see services/events.py).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.enums import Criticality


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        # The Activity page (newest first) and each of its filters; the
        # retention clean-up (oldest first, Info first for the safety net).
        Index("ix_events_org_started", "org_id", "started_at"),
        Index("ix_events_org_type_started", "org_id", "type", "started_at"),
        Index("ix_events_org_actor_started", "org_id", "actor_id", "started_at"),
        Index("ix_events_org_criticality_started", "org_id", "criticality", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Null for events of the whole system (the worker starting or stopping),
    # which every org's Activity shows.
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    # What happened, e.g. "import", "archive", "login_failed" (services/events.py).
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # What it happened to (a file name, a hostname...), as it was called then.
    item: Mapped[str | None] = mapped_column(String(255))
    # Who: null for the system. actor_label keeps the name after the user is gone.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    # completed | failed | stopped
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    criticality: Mapped[Criticality] = mapped_column(str_enum(Criticality), nullable=False)
    # Rows created, archived, purged...: {"assets": n, "findings": n}.
    counts: Mapped[dict | None] = mapped_column(JSONB)
    # Anything else worth keeping: the error, the settings changed, a retry.
    details: Mapped[dict | None] = mapped_column(JSONB)


class WorkerStatus(Base):
    """The background worker's check-in (one row): the app warns when it's
    older than a minute."""

    __tablename__ = "worker_status"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
