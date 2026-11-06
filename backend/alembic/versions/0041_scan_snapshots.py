"""Captured import configuration and versioned scan declarations; no backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("scans", sa.Column("ingestion_config_fingerprint", sa.String(64)))
    op.create_table("scan_snapshot_declarations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scan_id", pg.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("declaration", pg.JSONB(), nullable=False),
        sa.Column("scan_context", pg.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scan_id", "version", name="uq_scan_snapshot_version"),
        sa.CheckConstraint("state IN ('declared','revoked')", name="ck_scan_snapshot_state"),
        sa.CheckConstraint("version > 0", name="ck_scan_snapshot_version"))
    op.create_index("ix_scan_snapshot_org_scan", "scan_snapshot_declarations", ["org_id", "scan_id", "version"])


def downgrade():
    op.drop_table("scan_snapshot_declarations")
    op.drop_column("scans", "ingestion_config_fingerprint")
