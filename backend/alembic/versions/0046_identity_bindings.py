"""Explicit tool namespaces and reviewed observation identity bindings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("identity_tools",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("org_id", pg.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_identity_tools_org", "identity_tools", ["org_id", "id"])
    op.create_table("observation_identity_bindings",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("org_id", pg.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observation_id", pg.UUID(), sa.ForeignKey("finding_observations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("tool_id", pg.UUID(), sa.ForeignKey("identity_tools.id", ondelete="SET NULL")),
        sa.Column("canonical_asset_id", pg.UUID(), sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("context", pg.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_id", pg.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("observation_id", "version", name="uq_observation_identity_version"),
        sa.CheckConstraint("version > 0", name="ck_observation_identity_version"),
        sa.CheckConstraint("state IN ('bound','revoked')", name="ck_observation_identity_state"))
    op.create_index("ix_observation_identity_org_page", "observation_identity_bindings", ["org_id", "observation_id", "version"])
    for name, column in (("tool", "tool_id"), ("asset", "canonical_asset_id"), ("actor", "actor_id")):
        op.create_index("ix_observation_identity_" + name, "observation_identity_bindings", [column])


def downgrade():
    op.drop_table("observation_identity_bindings")
    op.drop_table("identity_tools")
