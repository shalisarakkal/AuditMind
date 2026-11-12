"""Add retained consolidation ledgers, without visibility or source mutations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finding_consolidations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pair_key", sa.String(73), nullable=False),
        *[sa.Column(name, pg.UUID(as_uuid=True), nullable=False) for name in
          ("finding_a_id", "finding_b_id", "canonical_finding_id", "canonical_decision_id")],
        sa.Column("identity_version", sa.String(50), nullable=False),
        sa.Column("candidate_key", sa.String(100), nullable=False),
        sa.Column("tool_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_asset_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "id", name="uq_consolidation_owner"),
        sa.UniqueConstraint("org_id", "pair_key", name="uq_consolidation_pair"),
        sa.CheckConstraint("version > 0", name="ck_consolidation_version"),
        sa.CheckConstraint("state IN ('active','undone')", name="ck_consolidation_state"),
        sa.CheckConstraint("finding_a_id <> finding_b_id AND canonical_finding_id IN (finding_a_id,finding_b_id)", name="ck_consolidation_members"))
    op.create_index("uq_consolidation_active_identity", "finding_consolidations",
        ["org_id", "identity_version", "candidate_key"], unique=True, postgresql_where=sa.text("state = 'active'"))
    for name, columns in (
        ("ix_consolidation_page", ["org_id", "created_at", "id"]),
        ("ix_consolidation_a", ["org_id", "finding_a_id"]),
        ("ix_consolidation_b", ["org_id", "finding_b_id"]),
        ("ix_consolidation_tool", ["org_id", "tool_id"]),
        ("ix_consolidation_asset", ["org_id", "canonical_asset_id"]),
    ):
        op.create_index(name, "finding_consolidations", columns)
    op.create_table("finding_consolidation_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("consolidation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("context", pg.JSONB(), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "consolidation_id"], ["finding_consolidations.org_id", "finding_consolidations.id"],
            ondelete="CASCADE", name="fk_consolidation_decision_owner"),
        sa.UniqueConstraint("org_id", "request_id", name="uq_consolidation_request"),
        sa.UniqueConstraint("consolidation_id", "version", name="uq_consolidation_decision_version"),
        sa.CheckConstraint("version > 0", name="ck_consolidation_decision_version"),
        sa.CheckConstraint("state IN ('active','undone')", name="ck_consolidation_decision_state"),
        sa.CheckConstraint("length(btrim(rationale)) BETWEEN 1 AND 2000", name="ck_consolidation_rationale"))
    op.create_index("ix_consolidation_history", "finding_consolidation_decisions", ["org_id", "consolidation_id", "version"])
    op.create_index("ix_consolidation_actor", "finding_consolidation_decisions", ["actor_id"])


def downgrade():
    op.drop_table("finding_consolidation_decisions")
    op.drop_table("finding_consolidations")
