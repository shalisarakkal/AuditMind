"""Findings that sum events up (Phase 2f part 2): how many events, first
and last seen, and details (the top actors and scopes, a few examples).
Empty for other findings.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("event_count", sa.Integer()))
    op.add_column("findings", sa.Column("first_seen", sa.DateTime(timezone=True)))
    op.add_column("findings", sa.Column("last_seen", sa.DateTime(timezone=True)))
    op.add_column("findings", sa.Column("details", postgresql.JSONB()))


def downgrade() -> None:
    for column in ("details", "last_seen", "first_seen", "event_count"):
        op.drop_column("findings", column)
