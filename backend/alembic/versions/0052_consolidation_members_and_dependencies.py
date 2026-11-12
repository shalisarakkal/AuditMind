"""Reserve consolidation membership and retained source manifests; no publication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_consolidation_generation_owner", "finding_consolidation_decisions",
        ["org_id", "consolidation_id", "version"])
    op.create_table("finding_consolidation_members",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("consolidation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("finding_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "consolidation_id", "generation"],
            ["finding_consolidation_decisions.org_id", "finding_consolidation_decisions.consolidation_id",
             "finding_consolidation_decisions.version"], ondelete="CASCADE", name="fk_consolidation_member_generation"),
        sa.UniqueConstraint("org_id", "finding_id", name="uq_consolidation_current_member"),
        sa.UniqueConstraint("org_id", "consolidation_id", "role", name="uq_consolidation_member_role"),
        sa.CheckConstraint("generation > 0", name="ck_consolidation_member_generation"),
        sa.CheckConstraint("role IN ('canonical','alias')", name="ck_consolidation_member_role"))
    op.create_index("ix_consolidation_members_group", "finding_consolidation_members",
        ["org_id", "consolidation_id", "generation"])
    op.create_table("finding_consolidation_dependencies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("consolidation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("resource_kind", sa.String(24), nullable=False),
        sa.Column("resource_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_version", sa.Integer()),
        sa.ForeignKeyConstraint(["org_id", "consolidation_id", "generation"],
            ["finding_consolidation_decisions.org_id", "finding_consolidation_decisions.consolidation_id",
             "finding_consolidation_decisions.version"], ondelete="CASCADE", name="fk_consolidation_dependency_generation"),
        sa.UniqueConstraint("org_id", "consolidation_id", "generation", "resource_kind", "resource_id",
            name="uq_consolidation_dependency"),
        sa.CheckConstraint("generation > 0", name="ck_consolidation_dependency_generation"),
        sa.CheckConstraint("resource_kind IN ('finding','observation','scan','asset','tool','identity_binding','canonical_decision')",
            name="ck_consolidation_dependency_kind"),
        sa.CheckConstraint("resource_version IS NULL OR resource_version > 0", name="ck_consolidation_dependency_version"))
    op.create_index("ix_consolidation_dependency_resource", "finding_consolidation_dependencies",
        ["org_id", "resource_kind", "resource_id", "consolidation_id", "generation"])


def downgrade():
    op.drop_table("finding_consolidation_dependencies")
    op.drop_table("finding_consolidation_members")
    op.drop_constraint("uq_consolidation_generation_owner", "finding_consolidation_decisions", type_="unique")
