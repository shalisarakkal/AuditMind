"""Indexed literal-substring finding/asset search; concurrent, retryable DDL."""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def indexes():
    for table, columns in (("findings", ("description", "category", "source")),
                           ("assets", ("hostname", "ip", "cloud_id"))):
        for column in columns:
            yield f"ix_{table}_{column}_trgm", table, [column], dict(
                postgresql_using="gin", postgresql_ops={column: "gin_trgm_ops"},
                **({"postgresql_where": sa.text("archived_at IS NULL")} if table == "findings" else {}))
    yield "ix_findings_active_assignee", "findings", ["assignee_id"], dict(postgresql_where=sa.text("archived_at IS NULL"))
    for name, column in (("due", "due_date"), ("review", "risk_review_date")):
        yield f"ix_findings_active_{name}_search", "findings", ["org_id"], dict(
            postgresql_where=sa.text(f"archived_at IS NULL AND {column} IS NOT NULL"))


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    # Large inventories must remain writable during index construction. Each
    # completed index survives interruption; IF NOT EXISTS supports safe retry.
    with op.get_context().autocommit_block():
        for name, table, columns, options in indexes():
            invalid = op.get_bind().scalar(sa.text("""SELECT NOT i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname=:name"""), {"name": name})
            if invalid:
                raise RuntimeError(f"Interrupted index {name} is invalid; drop that index concurrently and retry migration")
            op.create_index(name, table, columns, postgresql_concurrently=True, if_not_exists=True, **options)


def downgrade():
    with op.get_context().autocommit_block():
        for name, table, _, _ in reversed(list(indexes())):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
    # pg_trgm may be shared by other schemas/applications; never remove it here.
