"""Compact active facet indexes for bounded ordered distinct probes."""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

INDEXES = tuple(
    (f"ix_{table}_active_org_{column}", table, ["org_id", column])
    for table, columns in (
        ("assets", ("type", "subtype", "environment", "criticality")),
        ("findings", ("source", "workflow_status", "assignee_id", "scan_id")),
    ) for column in columns
)


def upgrade():
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
