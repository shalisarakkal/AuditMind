"""Staging for imports run by the background worker (Phase 2f part 1): the
checked rows of an upload, in chunks, and how far reading has got, so an
import cut off carries on from its last chunk. UNLOGGED: cheap to write, and
emptied together after a database crash (the import then reads again).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    scan_id = lambda: sa.Column(  # noqa: E731
        "scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    op.create_table(
        "import_staging_state",
        scan_id(),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        prefixes=["UNLOGGED"],
    )
    op.create_table(
        "import_staging_chunks",
        scan_id(),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        prefixes=["UNLOGGED"],
    )


def downgrade() -> None:
    op.drop_table("import_staging_chunks")
    op.drop_table("import_staging_state")
