"""run_started_at on scans and archive_jobs: when the work actually started,
as opposed to when it was asked for (a large upload can wait its turn for
the background worker). Activity shows "waited 15 min, took 1 min 24 s".
Also drops the zero counts (and warnings_total) from the events carried over
by 0011, as new events never have them.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("scans", "archive_jobs"):
        op.add_column(table, sa.Column("run_started_at", sa.DateTime(timezone=True)))
    op.execute(
        """
        UPDATE events e SET counts = NULLIF(
            (SELECT COALESCE(jsonb_object_agg(key, value), '{}'::jsonb)
             FROM jsonb_each(e.counts)
             WHERE key <> 'warnings_total' AND jsonb_typeof(value) = 'number' AND value::text <> '0'),
            '{}'::jsonb)
        WHERE jsonb_typeof(e.counts) = 'object'
        """
    )
    op.execute("UPDATE events SET counts = NULL WHERE jsonb_typeof(counts) = 'null'")


def downgrade() -> None:
    for table in ("archive_jobs", "scans"):
        op.drop_column(table, "run_started_at")
