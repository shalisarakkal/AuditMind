"""archiving (Phase 2d part 2): archived_at / archive_batch_id on scans,
assets and findings; archive batches, archive jobs, the purge log and
upload-asset links (backfilled through findings); scans.content_hash for the
repeat-upload warning. The import-matching and findings-list indexes become
partial (active rows only), so archived rows cost those queries nothing.

On a large database the backfill and index rebuilds take a while (they read
every asset and finding once).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE = sa.text("archived_at IS NULL")
IN_BATCH = sa.text("archive_batch_id IS NOT NULL")


def _uuid(name: str, *args, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def upgrade() -> None:
    op.create_table(
        "archive_batches",
        _uuid("id", primary_key=True),
        _uuid("org_id", sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(7), nullable=False),
        _uuid("item_id", nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("state", sa.String(9), nullable=False),
        _uuid("created_by", sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_archive_batches_org_type_created", "archive_batches", ["org_id", "item_type", "created_at"])
    op.create_table(
        "archive_jobs",
        _uuid("id", primary_key=True),
        _uuid("org_id", sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        _uuid("batch_id", sa.ForeignKey("archive_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(7), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        _uuid("started_by", sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("progress", postgresql.JSONB()),
        sa.Column("summary", postgresql.JSONB()),
    )
    op.create_index("ix_archive_jobs_org_status", "archive_jobs", ["org_id", "status"])
    op.create_table(
        "purge_log",
        _uuid("id", primary_key=True),
        _uuid("org_id", sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(7), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("purged_by", sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_purge_log_org_purged", "purge_log", ["org_id", "purged_at"])

    for table in ("scans", "assets", "findings"):
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True)))
        op.add_column(table, _uuid("archive_batch_id", sa.ForeignKey("archive_batches.id", ondelete="SET NULL")))
    op.add_column("scans", sa.Column("content_hash", sa.String(64)))
    op.create_index("ix_scans_org_content_hash", "scans", ["org_id", "content_hash"])

    # Rebuild the hot indexes over active rows only.
    for name, table, columns in (
        ("ix_assets_org_hostname", "assets", ["org_id", sa.text("lower(hostname)")]),
        ("ix_assets_org_ip", "assets", ["org_id", "ip"]),
        ("ix_assets_org_cloud_id", "assets", ["org_id", "cloud_id"]),
        ("ix_findings_org_created", "findings", ["org_id", "created_at"]),
        ("ix_findings_org_severity_created", "findings", ["org_id", "severity", "created_at"]),
    ):
        op.drop_index(name, table_name=table)
        op.create_index(name, table, columns, postgresql_where=ACTIVE)
    op.create_index("ix_assets_archive_batch", "assets", ["archive_batch_id"], postgresql_where=IN_BATCH)
    op.create_index("ix_findings_archive_batch", "findings", ["archive_batch_id"], postgresql_where=IN_BATCH)

    # Earlier imports: link each upload to the assets its findings are on.
    # Assets from asset-only imports can't be traced and stay unlinked. The
    # links are filled in before the key and foreign keys exist: checking each
    # of millions of rows as it goes in is a random read per row (tens of
    # minutes on a spinning disk); adding them afterwards checks them all in
    # one pass.
    op.create_table(
        "asset_scans",
        _uuid("scan_id", nullable=False),
        _uuid("asset_id", nullable=False),
    )
    op.execute("SET LOCAL work_mem = '256MB'")
    op.execute(
        "INSERT INTO asset_scans (scan_id, asset_id) "
        "SELECT DISTINCT scan_id, asset_id FROM findings WHERE scan_id IS NOT NULL AND asset_id IS NOT NULL"
    )
    op.create_primary_key("asset_scans_pkey", "asset_scans", ["scan_id", "asset_id"])
    op.create_foreign_key("asset_scans_scan_id_fkey", "asset_scans", "scans", ["scan_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("asset_scans_asset_id_fkey", "asset_scans", "assets", ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_asset_scans_asset", "asset_scans", ["asset_id"])


def downgrade() -> None:
    op.drop_table("asset_scans")
    op.drop_index("ix_findings_archive_batch", table_name="findings")
    op.drop_index("ix_assets_archive_batch", table_name="assets")
    for name, table, columns in (
        ("ix_assets_org_hostname", "assets", ["org_id", sa.text("lower(hostname)")]),
        ("ix_assets_org_ip", "assets", ["org_id", "ip"]),
        ("ix_assets_org_cloud_id", "assets", ["org_id", "cloud_id"]),
        ("ix_findings_org_created", "findings", ["org_id", "created_at"]),
        ("ix_findings_org_severity_created", "findings", ["org_id", "severity", "created_at"]),
    ):
        op.drop_index(name, table_name=table)
        op.create_index(name, table, columns)
    op.drop_index("ix_scans_org_content_hash", table_name="scans")
    op.drop_column("scans", "content_hash")
    for table in ("findings", "assets", "scans"):
        op.drop_column(table, "archive_batch_id")
        op.drop_column(table, "archived_at")
    op.drop_table("purge_log")
    op.drop_table("archive_jobs")
    op.drop_table("archive_batches")
