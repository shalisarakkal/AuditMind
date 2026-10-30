"""Saved Dashboard inventory and durable coalesced refresh jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("dashboard_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("captured_revision", sa.BigInteger()),
        sa.Column("payload", JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_dashboard_snapshot_status"))
    op.create_index("ix_dashboard_snapshot_queue", "dashboard_snapshots", ["status", "requested_at"])


def downgrade():
    # A rollback must not leave current API processes attempting to read a
    # removed cache table; fence forms that were opened before the downgrade.
    op.execute("""UPDATE platform_settings SET value = jsonb_set(
        jsonb_set(value, '{enabled}', 'false'::jsonb), '{version}',
        to_jsonb(COALESCE((value->>'version')::integer, 0) + 1))
        WHERE key='dashboard_snapshots'""")
    op.drop_table("dashboard_snapshots")
