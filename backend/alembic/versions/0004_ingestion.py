"""ingestion support (Phase 2a): scans.filename + scans.summary to track file
imports (the per-row report lives in summary, so background imports can be
polled); organizations.ingestion_overrides for per-org overrides of the .env
ingestion defaults (only overridden keys are stored); lookup indexes for
matching imported rows to existing assets by hostname (case-insensitive) or IP.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("filename", sa.String(255)))
    op.add_column("scans", sa.Column("summary", postgresql.JSONB()))

    op.add_column(
        "organizations",
        sa.Column(
            "ingestion_overrides",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_index("ix_assets_org_hostname", "assets", ["org_id", sa.text("lower(hostname)")])
    op.create_index("ix_assets_org_ip", "assets", ["org_id", "ip"])


def downgrade() -> None:
    op.drop_index("ix_assets_org_ip", table_name="assets")
    op.drop_index("ix_assets_org_hostname", table_name="assets")
    op.drop_column("organizations", "ingestion_overrides")
    op.drop_column("scans", "summary")
    op.drop_column("scans", "filename")
