"""Independent, versioned canonical-selection receipts; no finding rewrite."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finding_canonical_decisions",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("org_id", pg.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pair_key", sa.String(73), nullable=False),
        *[sa.Column(name, pg.UUID(), nullable=False) for name in (
            "finding_a_id", "finding_b_id", "canonical_finding_id", "source_observation_id", "target_observation_id")],
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("context", pg.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_id", pg.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "pair_key", "version", name="uq_finding_canonical_version"),
        sa.CheckConstraint("version > 0", name="ck_finding_canonical_version"),
        sa.CheckConstraint("state IN ('selected','revoked')", name="ck_finding_canonical_state"),
        sa.CheckConstraint("finding_a_id <> finding_b_id AND canonical_finding_id IN (finding_a_id,finding_b_id)", name="ck_finding_canonical_members"))
    for suffix, columns in (
        ("a", ["org_id", "finding_a_id", "created_at"]),
        ("b", ["org_id", "finding_b_id", "created_at"]), ("actor", ["actor_id"])):
        op.create_index("ix_finding_canonical_" + suffix, "finding_canonical_decisions", columns)


def downgrade():
    op.drop_table("finding_canonical_decisions")
