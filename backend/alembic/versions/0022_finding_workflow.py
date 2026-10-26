"""Finding remediation workflow and append-only history.

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("findings", sa.Column("workflow_status", sa.String(20), nullable=False, server_default="open"))
    op.add_column("findings", sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("findings", sa.Column("assignee_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_findings_assignee", "findings", "users", ["assignee_id"], ["id"], ondelete="SET NULL")
    op.add_column("findings", sa.Column("due_date", sa.Date()))
    op.add_column("findings", sa.Column("risk_review_date", sa.Date()))
    op.add_column("findings", sa.Column("workflow_updated_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("ck_finding_workflow_status", "findings", "workflow_status IN ('open','accepted_risk','mitigated','resolved','false_positive')")
    op.create_check_constraint("ck_finding_workflow_version", "findings", "workflow_version >= 0")
    op.create_table("finding_history",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", pg.UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("before", pg.JSONB(), nullable=False),
        sa.Column("after", pg.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("verification", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("finding_id", "version", name="uq_finding_history_version"))
    op.create_index("ix_finding_history_org_finding", "finding_history", ["org_id", "finding_id", "version"])


def downgrade():
    # Explicit downgrade removes workflow/history; operators must export first.
    op.drop_table("finding_history")
    op.drop_constraint("ck_finding_workflow_status", "findings", type_="check")
    op.drop_constraint("ck_finding_workflow_version", "findings", type_="check")
    op.drop_constraint("fk_findings_assignee", "findings", type_="foreignkey")
    for name in ("workflow_updated_at", "risk_review_date", "due_date", "assignee_id", "workflow_version", "workflow_status"):
        op.drop_column("findings", name)
