"""Default-off live scoring settings and tenant-bound qualification drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("organization_scoring_settings",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("evidence_qualified_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("version >= 1", name="ck_scoring_settings_version"))
    op.create_table("domain_evidence_qualifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("scope", sa.String(2000), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("observations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "domain", name="uq_qualification_org_domain"),
        sa.CheckConstraint("version >= 1", name="ck_qualification_version"),
        sa.CheckConstraint("status IN ('draft','approved','revoked')", name="ck_qualification_status"))


def downgrade():
    op.drop_table("domain_evidence_qualifications")
    op.drop_table("organization_scoring_settings")
