"""Organization archive and purge (Phase 2e part 3): when an org was
archived, and when its purge was asked for (the background worker then
deletes it).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for when, who in (("archived_at", "archived_by"), ("purge_requested_at", "purge_requested_by")):
        op.add_column("organizations", sa.Column(when, sa.DateTime(timezone=True)))
        op.add_column("organizations", sa.Column(who, postgresql.UUID(as_uuid=True)))
        op.create_foreign_key(
            f"organizations_{who}_fkey", "organizations", "users", [who], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    for when, who in (("purge_requested_at", "purge_requested_by"), ("archived_at", "archived_by")):
        op.drop_constraint(f"organizations_{who}_fkey", "organizations", type_="foreignkey")
        op.drop_column("organizations", who)
        op.drop_column("organizations", when)
