import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import str_enum
from app.models.enums import ScanStatus


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (Index("ix_scans_org_content_hash", "org_id", "content_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    scan_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ScanStatus] = mapped_column(str_enum(ScanStatus, length=50), default=ScanStatus.pending, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(100))
    # File imports: the uploaded filename and the per-row import report.
    filename: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[dict | None] = mapped_column(JSONB)
    # The import profile the file was read with (built-in key or custom id).
    profile: Mapped[str | None] = mapped_column(String(100))
    # Who uploaded the file (null for scans from before this was recorded).
    # Only they see its import report, until they dismiss it (dismissed_at).
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A running import's progress: {"phase": "reading"} while the file is
    # read, then {"phase": "writing", "rows_done": n, "rows_total": n}.
    # Written outside the import's transaction (see ingestion_background.py).
    progress: Mapped[dict | None] = mapped_column(JSONB)
    # SHA-256 of the uploaded file, to warn when the same file is uploaded again.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # Set by the background worker while it runs this job (every ~15 s): a
    # running job without a recent one was cut off (see app/worker).
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Times the worker has started it again after it was cut off.
    # When it actually started running (started_at is when it was asked for;
    # a large upload can wait its turn for the background worker).
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default=text("0"))
    # Archived (Phase 2d part 2): hidden everywhere until restored or purged;
    # archive_batch_id is the archive action that took it (see models/archive.py).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archive_batches.id", ondelete="SET NULL")
    )

    organization: Mapped["Organization"] = relationship(back_populates="scans")

    @property
    def retryable(self) -> bool:
        """A large upload that failed for a reason other than its content
        (summary "error": cut off too often, an unexpected error) and whose file
        is still kept (UPLOAD_KEEP_FAILED_DAYS): it can be run again from
        that file. One its content failed (row errors) can't: it would fail
        the same way."""
        from app.api.uploads import upload_path  # the api package imports the models

        return (
            self.status == ScanStatus.failed
            and self.source == "upload"
            and self.archived_at is None
            and bool(self.summary and self.summary.get("error"))
            and upload_path(self.id).exists()
        )
    findings: Mapped[list["Finding"]] = relationship(back_populates="scan", cascade="all, delete-orphan")
