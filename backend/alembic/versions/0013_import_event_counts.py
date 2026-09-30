"""Import events' counts named by what they count ("assets_created",
"findings_created", "duplicate_findings"...), as new events are (see
ingestion_service.event_counts): "900 created" didn't say created what.
Each import event is matched to its upload by org, file name and start time.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-30

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Report count -> event count, by kind of import (as event_counts).
NAMES = {
    "assets": {"created": "assets_created", "updated": "assets_updated", "skipped": "assets_skipped",
               "failed": "rows_failed"},
    "findings": {"created": "findings_created", "duplicates": "duplicate_findings", "skipped": "items_skipped",
                 "failed": "rows_failed"},
    "profile": {"created": "assets_created", "updated": "assets_updated", "skipped": "assets_skipped",
                "findings_created": "findings_created", "duplicates": "duplicate_findings", "failed": "rows_failed"},
}
KIND = """CASE WHEN s.scan_type = 'asset_import' THEN 'assets'
          WHEN s.scan_type IN ('findings_csv', 'findings_json', 'nessus', 'generic_findings_import') THEN 'findings'
          ELSE 'profile' END"""


def upgrade() -> None:
    mapping = ", ".join(
        f"('{kind}', '{old}', '{new}')" for kind, names in NAMES.items() for old, new in names.items()
    )
    op.execute(
        f"""
        WITH matched AS (
            SELECT DISTINCT ON (e.id) e.id, {KIND} AS kind
            FROM events e
            JOIN scans s ON s.org_id = e.org_id AND s.filename = e.item
                AND e.started_at IN (s.started_at, s.run_started_at)
            WHERE e.type = 'import' AND jsonb_typeof(e.counts) = 'object'
        ),
        names(kind, old, new) AS (VALUES {mapping})
        UPDATE events e SET counts = (
            -- Names it doesn't map (already new ones) are kept as they are.
            SELECT NULLIF(COALESCE(jsonb_object_agg(COALESCE(n.new, c.key), c.value), '{{}}'::jsonb), '{{}}'::jsonb)
            FROM jsonb_each(e.counts) c LEFT JOIN names n ON n.kind = m.kind AND n.old = c.key
        )
        FROM matched m
        WHERE e.id = m.id
        """
    )


def downgrade() -> None:
    # The old names can't be told apart again (created = assets or findings);
    # events keep the new ones.
    pass
