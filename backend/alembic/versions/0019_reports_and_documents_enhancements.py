"""Reports and documents enhancements (Phase 3: AI Audit & Reporting).

Adds structured JSON data snapshot, frameworks, started_by, worker heartbeats
and cancellation to `reports`.
Adds framework, control_id, version to `documents` for RAG knowledge base.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enhance reports table
    op.add_column("reports", sa.Column("frameworks", sa.String(length=100), nullable=True))
    op.add_column("reports", sa.Column("data", postgresql.JSONB(), nullable=True))
    op.add_column("reports", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "reports",
        sa.Column("started_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("reports", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "reports",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_reports_org_created", "reports", ["org_id", "created_at"])
    op.create_index("ix_reports_org_status", "reports", ["org_id", "status"])

    # 2. Enhance documents table
    op.add_column("documents", sa.Column("framework", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("control_id", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("version", sa.String(length=20), nullable=True))
    op.create_index("ix_documents_framework", "documents", ["framework"])
    op.create_index("ix_documents_control_id", "documents", ["control_id"])
    op.create_index("ix_documents_org_framework", "documents", ["org_id", "framework"])


def downgrade() -> None:
    op.drop_index("ix_documents_org_framework", table_name="documents")
    op.drop_index("ix_documents_control_id", table_name="documents")
    op.drop_index("ix_documents_framework", table_name="documents")
    op.drop_column("documents", "version")
    op.drop_column("documents", "control_id")
    op.drop_column("documents", "framework")

    op.drop_index("ix_reports_org_status", table_name="reports")
    op.drop_index("ix_reports_org_created", table_name="reports")
    op.drop_column("reports", "created_at")
    op.drop_column("reports", "retry_count")
    op.drop_column("reports", "cancel_requested_at")
    op.drop_column("reports", "run_started_at")
    op.drop_column("reports", "heartbeat_at")
    op.drop_column("reports", "started_by")
    op.drop_column("reports", "error_message")
    op.drop_column("reports", "data")
    op.drop_column("reports", "frameworks")
