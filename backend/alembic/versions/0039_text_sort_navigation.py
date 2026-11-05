"""Bounded finding-text and hostname sort indexes."""
from alembic import op
import sqlalchemy as sa
from app.db.list_sort import severity_rank_index, SHORT_FINDING_TEXT, LONG_FINDING_TEXT

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

INDEXES = [
    *[(f"ix_assets_active_ip_{direction}_page", "assets",
       ["org_id", sa.text(f"ip {direction.upper()} NULLS LAST"), "created_at", "id"],
       sa.text("archived_at IS NULL")) for direction in ("asc", "desc")],
    *[(f"ix_findings_active_{field}_group_page", "findings",
       ["org_id",field,"severity",sa.text("created_at DESC NULLS LAST"),"id"],
       sa.text("archived_at IS NULL")) for field in ("workflow_status","assignee_id")],
    ("ix_findings_active_due_presence","findings",["org_id"],
     sa.text("archived_at IS NULL AND (due_date IS NOT NULL OR due_expires_at IS NOT NULL)")),
    ("ix_findings_active_review_presence","findings",["org_id"],
     sa.text("archived_at IS NULL AND (risk_review_date IS NOT NULL OR risk_review_expires_at IS NOT NULL)")),
    ("ix_findings_active_domain_page", "findings",
     ["org_id", "domain", severity_rank_index(), sa.text("created_at DESC NULLS LAST"), "id"], sa.text("archived_at IS NULL")),
    *[(f"ix_findings_active_{field}_{direction}_page", "findings",
       ["org_id", sa.text(f"lower({field}) {direction.upper()} NULLS LAST"), severity_rank_index(),
        sa.text("created_at DESC NULLS LAST"), "id"], sa.text("archived_at IS NULL"))
      for field in ("category", "source") for direction in ("asc", "desc")],
    *[(f"ix_assets_org_label_{direction}_page", "assets",
       ["org_id", sa.text(f"lower(COALESCE(hostname, ip, cloud_id)) {direction.upper()} NULLS LAST"), "id"],
       None) for direction in ("asc", "desc")],
    ("ix_assets_active_created_desc_page", "assets",
     ["org_id", sa.text("created_at DESC NULLS LAST"), "id"], sa.text("archived_at IS NULL")),
    *[(f"ix_assets_active_hostname_{direction}_page", "assets",
       ["org_id", sa.text(f"lower(hostname) {direction.upper()} NULLS LAST"), "created_at", "id"],
       sa.text("archived_at IS NULL")) for direction in ("asc", "desc")],
    *[(f"ix_findings_active_text_{direction}_page", "findings",
       ["org_id", sa.text(f"lower(COALESCE(description, category::text)) {direction.upper()} NULLS LAST"),
        severity_rank_index(), sa.text("created_at DESC NULLS LAST"), "id"],
       SHORT_FINDING_TEXT) for direction in ("asc", "desc")],
    ("ix_findings_active_long_text", "findings", ["org_id"], LONG_FINDING_TEXT),
]


def upgrade():
    with op.get_context().autocommit_block():
        for name, table, columns, predicate in INDEXES:
            invalid = op.get_bind().scalar(sa.text("""SELECT NOT i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname=:name"""), {"name": name})
            if invalid:
                raise RuntimeError(f"Interrupted index {name} is invalid; drop it concurrently before retrying")
            op.create_index(name, table, columns, postgresql_where=predicate,
                postgresql_concurrently=True, if_not_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        for name, table, _, _ in reversed(INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
