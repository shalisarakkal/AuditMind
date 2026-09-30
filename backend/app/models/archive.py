"""Archiving (Phase 2d part 2). Archived rows stay in their tables with
archived_at set (see Asset, Finding, Scan); these tables record the archive
actions, the jobs that carry them out, and what was purged.

An archive action is a batch: one upload, asset or manual finding, and
everything archived with it (archive_batch_id on each row). Restore and
purge act on a whole batch.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.enums import ArchiveAction, ArchiveItemType, ArchiveState, ScanStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AssetScan(Base):
    """An upload touched this asset (created, updated or matched it), so
    archiving another upload that touched it leaves it active. Written by
    every import from Phase 2d part 2 on; earlier imports are linked through
    their findings. `created`: this upload created the asset, so archiving
    the upload may archive it too (an asset it only matched never is)."""

    __tablename__ = "asset_scans"
    __table_args__ = (Index("ix_asset_scans_asset", "asset_id"),)

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class ArchiveBatch(Base):
    __tablename__ = "archive_batches"
    __table_args__ = (Index("ix_archive_batches_org_type_created", "org_id", "item_type", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[ArchiveItemType] = mapped_column(str_enum(ArchiveItemType), nullable=False)
    # The upload, asset or finding that was archived (not a foreign key: it
    # outlives the row once purged), and what the Archived page calls it.
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    # archiving -> archived -> (restoring -> restored) or (purging -> purged).
    # A batch left "archiving" (the server stopped mid-way) resumes when the
    # item is archived again.
    state: Mapped[ArchiveState] = mapped_column(str_enum(ArchiveState), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # When it was archived: auto-purge counts its retention from here.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    # Rows archived: {"uploads": n, "assets": n, "findings": n}.
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ArchiveJob(Base):
    """Archiving, restoring or purging a batch; shown in the import tracker
    like an import (same status, progress and dismiss fields as Scan)."""

    __tablename__ = "archive_jobs"
    __table_args__ = (Index("ix_archive_jobs_org_status", "org_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archive_batches.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[ArchiveAction] = mapped_column(str_enum(ArchiveAction), nullable=False)
    status: Mapped[ScanStatus] = mapped_column(str_enum(ScanStatus), default=ScanStatus.pending, nullable=False)
    # Null for auto-purge.
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {"phase": "findings", "rows_done": n, "rows_total": n}
    progress: Mapped[dict | None] = mapped_column(JSONB)
    # The outcome: rows per table, duplicates purged on restore, or "error".
    summary: Mapped[dict | None] = mapped_column(JSONB)


class PurgeLogEntry(Base):
    """What was permanently deleted, by whom (null: auto-purge) and when."""

    __tablename__ = "purge_log"
    __table_args__ = (Index("ix_purge_log_org_purged", "org_id", "purged_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[ArchiveItemType] = mapped_column(str_enum(ArchiveItemType), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    # "manual", "auto" (retention), or "duplicate" (findings purged on restore
    # because an active finding already covers them).
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
