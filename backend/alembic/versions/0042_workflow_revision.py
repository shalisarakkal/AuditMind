"""Allow workflow invalidation to commit independently of import invalidation."""
from alembic import op
import sqlalchemy as sa
from app.db.workflow_revision import install_v2, uninstall_v2

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("organization_workflow_revisions",
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    install_v2(op.get_bind())
    op.execute("UPDATE organization_list_revisions SET epoch=gen_random_uuid()")


def downgrade():
    uninstall_v2(op.get_bind())
    op.drop_table("organization_workflow_revisions")
    op.execute("UPDATE organization_list_revisions SET epoch=gen_random_uuid()")
