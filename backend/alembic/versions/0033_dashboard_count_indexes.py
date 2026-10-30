"""Compact active-row indexes for exact Dashboard aggregation."""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_findings_active_org_domain_severity", "findings", ["org_id", "domain", "severity"]),
    ("ix_assets_active_org_count", "assets", ["org_id"]),
)


def upgrade():
    # Like 0024, build outside a transaction so existing inventories stay
    # writable. Completed indexes survive interruption; invalid ones need an
    # explicit concurrent drop before retry, not a silent IF NOT EXISTS skip.
    with op.get_context().autocommit_block():
        for name, table, columns in INDEXES:
            invalid = op.get_bind().scalar(sa.text("""SELECT NOT i.indisvalid
                FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname=:name"""), {"name": name})
            if invalid:
                raise RuntimeError(f"Interrupted index {name} is invalid; drop that index concurrently and retry migration")
            op.create_index(name, table, columns, postgresql_where=sa.text("archived_at IS NULL"),
                            postgresql_concurrently=True, if_not_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        for name, table, _ in reversed(INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
