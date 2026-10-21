"""Durable AI accounting and report request idempotency.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reports", sa.Column("idempotency_key", sa.String(128)))
    op.add_column("reports", sa.Column("request_hash", sa.String(64)))
    op.create_unique_constraint("uq_reports_org_idempotency", "reports", ["org_id", "idempotency_key"])
    op.create_table("ai_usage",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
        sa.Column("reserved_usd", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ai_usage_org_created", "ai_usage", ["org_id", "created_at"])


def downgrade():
    op.drop_table("ai_usage")
    op.drop_constraint("uq_reports_org_idempotency", "reports", type_="unique")
    op.drop_column("reports", "request_hash")
    op.drop_column("reports", "idempotency_key")
