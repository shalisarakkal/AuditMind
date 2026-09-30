"""asset_scans.created: whether the upload created the asset (review of
Phase 2d part 2). Archiving an upload archives only assets it created; this
was inferred from times (asset created after the upload started), which also
caught an asset added by hand while the upload waited and then matched by
it. Imports now record it. Existing links keep that inference, the best
available for them.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "asset_scans", sa.Column("created", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.execute(
        "UPDATE asset_scans l SET created = true FROM assets a, scans s "
        "WHERE a.id = l.asset_id AND s.id = l.scan_id AND a.created_at >= s.started_at"
    )


def downgrade() -> None:
    op.drop_column("asset_scans", "created")
