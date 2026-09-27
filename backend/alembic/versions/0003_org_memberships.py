"""org_memberships — users can belong to several orgs, with a role per org
(org selection). Replaces users.org_id / users.role; existing users keep
access to their current org with their current role.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_memberships",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_org_memberships_org_id", "org_memberships", ["org_id"])

    op.execute(
        "INSERT INTO org_memberships (user_id, org_id, role, created_at) "
        "SELECT id, org_id, role, created_at FROM users"
    )

    op.drop_column("users", "org_id")
    op.drop_column("users", "role")


def downgrade() -> None:
    # Each user goes back to a single org: their oldest membership. Fails on
    # users with no membership at all (NOT NULL), rather than guessing an org.
    op.add_column("users", sa.Column("org_id", postgresql.UUID(as_uuid=True)))
    op.add_column("users", sa.Column("role", sa.String(50)))
    op.execute(
        "UPDATE users u SET org_id = m.org_id, role = m.role FROM ("
        "  SELECT DISTINCT ON (user_id) user_id, org_id, role FROM org_memberships"
        "  ORDER BY user_id, created_at"
        ") m WHERE m.user_id = u.id"
    )
    op.alter_column("users", "org_id", nullable=False)
    op.alter_column("users", "role", nullable=False)
    op.create_foreign_key(
        "users_org_id_fkey", "users", "organizations", ["org_id"], ["id"], ondelete="CASCADE"
    )

    op.drop_index("ix_org_memberships_org_id", table_name="org_memberships")
    op.drop_table("org_memberships")
