"""Append-only per-import finding observations (no historical inference)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finding_observations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", pg.UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("scan_id", pg.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL")),
        sa.Column("occurrence", sa.Integer(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("scan_type", sa.String(100), nullable=False),
        sa.Column("profile", sa.String(100)),
        sa.Column("filename", sa.String(255)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_identity", pg.JSONB(), nullable=False),
        sa.Column("source_identity", pg.JSONB(), nullable=False),
        sa.Column("reconciliation_eligible", sa.Boolean(), nullable=False),
        sa.Column("ineligibility_reasons", pg.JSONB(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.UniqueConstraint("import_id", "occurrence", name="uq_finding_observation_occurrence"))
    op.create_index("ix_finding_observations_page", "finding_observations", ["org_id", "finding_id", "recorded_at", "id"])
    op.create_index("ix_finding_observations_finding", "finding_observations", ["finding_id"])
    op.create_index("ix_finding_observations_scan", "finding_observations", ["scan_id"])


def downgrade():
    op.drop_table("finding_observations")
