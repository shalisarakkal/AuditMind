"""Durable fair organization scheduling; no inventory rewrite."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("worker_dispatch",
        sa.Column("scope_id", sa.String(64), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), unique=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("worker_dispatch")
