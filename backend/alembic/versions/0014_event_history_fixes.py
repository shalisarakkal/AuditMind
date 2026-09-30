"""Fixes to the Activity history carried over by 0011-0013 (review of Phase
2d part 3):
- imports with the generic findings profile count findings, not assets;
- failed imports get their error message back, from their upload's report;
- the duplicates purged on a restore were carried over twice (as a purge
  event, and in the restore's own event): the purge copies go.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-30

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# An import event and its upload: same org, file name and start.
MATCH = """FROM scans s WHERE s.org_id = e.org_id AND s.filename = e.item
           AND e.started_at IN (s.started_at, s.run_started_at)"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE events e SET counts = (
            SELECT jsonb_object_agg(
                CASE c.key WHEN 'assets_created' THEN 'findings_created'
                           WHEN 'assets_skipped' THEN 'items_skipped' ELSE c.key END, c.value)
            FROM jsonb_each(e.counts) c)
        WHERE e.type = 'import' AND jsonb_typeof(e.counts) = 'object'
          AND EXISTS (SELECT 1 {MATCH} AND s.scan_type = 'generic_findings_import')
        """
    )
    op.execute(
        f"""
        UPDATE events e SET details = jsonb_build_object('error', (
            SELECT COALESCE(s.summary->>'error',
                            (SELECT x->>'message' FROM jsonb_array_elements(
                                 CASE WHEN jsonb_typeof(s.summary->'errors') = 'array' THEN s.summary->'errors' END) x
                             WHERE (x->>'row')::int = 0 LIMIT 1))
            {MATCH} LIMIT 1))
        WHERE e.type = 'import' AND e.outcome = 'failed' AND e.details IS NULL
          AND EXISTS (SELECT 1 {MATCH} AND (s.summary ? 'error' OR jsonb_typeof(s.summary->'errors') = 'array'))
        """
    )
    op.execute("UPDATE events SET details = NULL WHERE details = jsonb_build_object('error', NULL)")
    op.execute("DELETE FROM events WHERE type = 'purge' AND details->>'reason' = 'duplicate'")


def downgrade() -> None:
    # Data fixes only; nothing to undo.
    pass
