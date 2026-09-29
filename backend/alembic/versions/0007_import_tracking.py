"""import tracking and findings indexes (Phase 2d part 1): scans.started_by
(who uploaded the file), scans.dismissed_at (their import report was
dismissed) and scans.progress (a running import's row count); indexes on
findings, which had none. Scans that had already finished are marked
dismissed, so old import reports don't reappear.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("started_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.add_column("scans", sa.Column("dismissed_at", sa.DateTime(timezone=True)))
    op.add_column("scans", sa.Column("progress", postgresql.JSONB()))
    op.execute(
        "UPDATE scans SET dismissed_at = COALESCE(completed_at, now()) WHERE status IN ('completed', 'failed')"
    )

    op.create_index("ix_findings_org_created", "findings", ["org_id", "created_at"])
    op.create_index("ix_findings_asset", "findings", ["asset_id"])
    op.create_index("ix_findings_scan", "findings", ["scan_id"])


def downgrade() -> None:
    op.drop_index("ix_findings_scan", table_name="findings")
    op.drop_index("ix_findings_asset", table_name="findings")
    op.drop_index("ix_findings_org_created", table_name="findings")
    op.drop_column("scans", "progress")
    op.drop_column("scans", "dismissed_at")
    op.drop_column("scans", "started_by")
