"""Transactional list revisions and covering default-page indexes."""
from alembic import op
import sqlalchemy as sa
from app.db.list_revision import install_v1, uninstall_v1
from app.db.list_sort import severity_rank_index

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_assets_active_created_page", "assets", ["org_id", "created_at", "id"]),
    ("ix_findings_active_created_page", "findings", ["org_id", "created_at", "id"]),
    ("ix_findings_active_severity_page", "findings", ["org_id", severity_rank_index(), sa.text("created_at DESC NULLS LAST"), "id"]),
)


def upgrade():
    # Concurrent index creation commits earlier DDL. A retry after an
    # interrupted build must retain the already-installed revision state.
    if not sa.inspect(op.get_bind()).has_table("organization_list_revisions"):
        op.create_table("organization_list_revisions",
            sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("epoch", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("asset_revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("finding_revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    install_v1(op.get_bind())
    with op.get_context().autocommit_block():
        for name, table, columns in INDEXES:
            invalid = op.get_bind().scalar(sa.text("""SELECT NOT i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname=:name"""), {"name": name})
            if invalid: raise RuntimeError(f"Interrupted index {name} is invalid; drop it concurrently before retrying")
            op.create_index(name, table, columns, postgresql_where=sa.text("archived_at IS NULL"),
                postgresql_concurrently=True, if_not_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        for name, table, _ in reversed(INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
    uninstall_v1(op.get_bind())
    op.drop_table("organization_list_revisions")
