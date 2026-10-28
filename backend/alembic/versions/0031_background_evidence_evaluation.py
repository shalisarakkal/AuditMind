"""Durable evidence jobs and database-wide transactional invalidation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("organization_evidence_revisions",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("revision >= 0", name="ck_evidence_revision"))
    op.create_table("evidence_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *[sa.Column(name, sa.DateTime(timezone=True)) for name in ("run_started_at", "heartbeat_at", "completed_at", "cancel_requested_at", "valid_until")],
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("captured_revision", sa.BigInteger()),
        sa.Column("policy_identity", sa.String(64)),
        sa.Column("progress", postgresql.JSONB()), sa.Column("result", postgresql.JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.CheckConstraint("status IN ('pending','running','completed','failed','cancelled','superseded')", name="ck_evidence_evaluation_status"),
        sa.CheckConstraint("retry_count >= 0", name="ck_evidence_evaluation_retries"))
    op.create_index("ix_evidence_evaluation_pending", "evidence_evaluations", ["created_at"], postgresql_where=sa.text("status='pending'"))
    op.create_index("uq_evidence_evaluation_active_org", "evidence_evaluations", ["org_id"], unique=True, postgresql_where=sa.text("status IN ('pending','running')"))
    op.create_index("ix_evidence_evaluation_org_created", "evidence_evaluations", ["org_id", "created_at"])
    op.create_index("ix_evidence_evaluation_cache", "evidence_evaluations", ["org_id", "captured_revision"], postgresql_where=sa.text("status='completed'"))
    # Frozen, versioned DDL shared with isolated create_all fixtures.
    from app.db.evidence_revision import install_v1
    install_v1(op.get_bind())


def downgrade():
    from app.db.evidence_revision import uninstall_v1
    uninstall_v1(op.get_bind())
    # The older API does not implement qualified scoring: fail safely on rollback.
    op.execute("UPDATE organization_scoring_settings SET evidence_qualified_enabled=false, version=version+1 WHERE evidence_qualified_enabled")
    op.drop_table("evidence_evaluations")
    op.drop_table("organization_evidence_revisions")
