"""Retained open-finding remediation proof review ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.db.remediation_proof import install_v1, uninstall_v1

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("remediation_proofs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.Uuid(), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("source_reference", sa.String(2048), nullable=False),
        sa.Column("source_sha256", sa.String(64)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitter_id", sa.Uuid(), nullable=False),
        sa.Column("submitter_label", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("org_id", "finding_id", "version", name="uq_remediation_proof_version"),
        sa.CheckConstraint("version >= 1 AND workflow_version >= 0", name="ck_remediation_proof_version"),
        sa.CheckConstraint("state IN ('pending','approved','rejected')", name="ck_remediation_proof_state"))
    op.create_index("ix_remediation_proofs_finding_id", "remediation_proofs", ["finding_id"])
    install_v1(op.get_bind())


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM remediation_proofs)")):
        raise RuntimeError("Export retained remediation proof before reviewed downgrade")
    uninstall_v1(op.get_bind())
    op.drop_table("remediation_proofs")
