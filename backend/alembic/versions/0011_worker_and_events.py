"""background worker and Activity (Phase 2d part 3): heartbeat and retry
columns on scans and archive_jobs, worker_status, and events, filled from
the uploads, archive jobs and purge log so far; the purge log is then part
of events and dropped.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WHO = "COALESCE(u.name, u.email, 'System')"


def upgrade() -> None:
    for table in ("scans", "archive_jobs"):
        op.add_column(table, sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "worker_status",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("item", sa.String(255)),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("criticality", sa.String(8), nullable=False),
        sa.Column("counts", postgresql.JSONB()),
        sa.Column("details", postgresql.JSONB()),
    )
    for name, columns in (
        ("ix_events_org_started", ["org_id", "started_at"]),
        ("ix_events_org_type_started", ["org_id", "type", "started_at"]),
        ("ix_events_org_actor_started", ["org_id", "actor_id", "started_at"]),
        ("ix_events_org_criticality_started", ["org_id", "criticality", "started_at"]),
    ):
        op.create_index(name, "events", columns)

    # So far: finished uploads...
    op.execute(
        f"""
        INSERT INTO events (id, org_id, type, item, actor_id, actor_label, started_at, ended_at, outcome,
                            criticality, counts, details)
        SELECT gen_random_uuid(), s.org_id, 'import', s.filename, s.started_by, {WHO},
               COALESCE(s.started_at, s.completed_at, now()), COALESCE(s.completed_at, s.started_at, now()),
               s.status,
               CASE WHEN s.status = 'failed' OR COALESCE((s.summary->>'failed')::int, 0) > 0
                    THEN 'warning' ELSE 'info' END,
               s.summary - 'errors' - 'warnings', NULL
        FROM scans s LEFT JOIN users u ON u.id = s.started_by
        WHERE s.source = 'upload' AND s.status IN ('completed', 'failed')
        """
    )
    # ...archives and restores (purges come from the purge log, which also
    # has the duplicates purged on restore)...
    op.execute(
        f"""
        INSERT INTO events (id, org_id, type, item, actor_id, actor_label, started_at, ended_at, outcome,
                            criticality, counts, details)
        SELECT gen_random_uuid(), j.org_id, j.action, b.label, j.started_by, {WHO},
               j.started_at, COALESCE(j.completed_at, j.started_at), j.status,
               CASE WHEN j.status = 'failed' OR COALESCE((j.summary->>'duplicates_purged')::int, 0) > 0
                    THEN 'warning' ELSE 'info' END,
               j.summary - 'error', CASE WHEN j.summary ? 'error' THEN jsonb_build_object('error', j.summary->'error') END
        FROM archive_jobs j JOIN archive_batches b ON b.id = j.batch_id LEFT JOIN users u ON u.id = j.started_by
        WHERE j.action IN ('archive', 'restore') AND j.status IN ('completed', 'failed')
        """
    )
    # ...and purges.
    op.execute(
        f"""
        INSERT INTO events (id, org_id, type, item, actor_id, actor_label, started_at, ended_at, outcome,
                            criticality, counts, details)
        SELECT gen_random_uuid(), p.org_id, 'purge', p.label, p.purged_by, {WHO},
               p.purged_at, p.purged_at, 'completed', 'critical', p.counts,
               jsonb_build_object('reason', p.reason, 'archived_at', p.archived_at, 'item_type', p.item_type)
        FROM purge_log p LEFT JOIN users u ON u.id = p.purged_by
        """
    )
    op.drop_table("purge_log")


def downgrade() -> None:
    # The purge log comes back empty: its entries live on only as events,
    # which are dropped here.
    op.create_table(
        "purge_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(7), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_purge_log_org_purged", "purge_log", ["org_id", "purged_at"])
    op.drop_table("events")
    op.drop_table("worker_status")
    for table in ("archive_jobs", "scans"):
        op.drop_column(table, "retry_count")
        op.drop_column(table, "heartbeat_at")
