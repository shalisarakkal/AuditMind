"""assets.type_known: false when an asset's type is a guess (a profile default,
an unrecognised OS, or the placeholder for a finding's unknown host). Imports
match an existing asset by hostname and category, and a guessed asset matches
any category. Existing assets are all treated as known.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("type_known", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("assets", "type_known")
