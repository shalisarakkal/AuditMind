"""Immutable text-only combined Assets search candidate index."""
from alembic import op
import sqlalchemy as sa
from app.db.asset_search import install_v1, uninstall_v1

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None
INDEX = "ix_assets_active_search_trgm"


def upgrade():
    install_v1(op.get_bind())
    with op.get_context().autocommit_block():
        invalid = op.get_bind().scalar(sa.text("""SELECT NOT i.indisvalid
            FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relname=:name"""), {"name": INDEX})
        if invalid:
            raise RuntimeError(f"Interrupted index {INDEX} is invalid; drop it concurrently before retrying")
        op.create_index(INDEX, "assets", [sa.literal_column("am_asset_search_v1(hostname, ip, cloud_id, type, subtype, environment, criticality, tags)").label("search_text")],
            postgresql_using="gin", postgresql_ops={"search_text": "gin_trgm_ops"}, postgresql_where=sa.text("archived_at IS NULL"),
            postgresql_concurrently=True, if_not_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="assets", postgresql_concurrently=True, if_exists=True)
    uninstall_v1(op.get_bind())
