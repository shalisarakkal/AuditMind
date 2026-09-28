"""import profiles (Phase 2c): assets.subtype (the original type name, e.g.
"laptop", when an alias mapped it to a category) and assets.details (extra
device facts from profile imports: OS, open ports, agent version...);
scans.profile (the import profile a file was read with); import_profiles for
each org's own copies of the built-in profiles; an (org_id, cloud_id) index,
since cloud resources are matched on import by their cloud ID.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("subtype", sa.String(100)))
    op.add_column(
        "assets",
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("scans", sa.Column("profile", sa.String(100)))
    # Cloud resources are matched on import by their cloud ID.
    op.create_index("ix_assets_org_cloud_id", "assets", ["org_id", "cloud_id"])

    op.create_table(
        "import_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("family", sa.String(50), nullable=False),
        sa.Column("column_map", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_import_profiles_org_name"),
    )
    op.create_index("ix_import_profiles_org_id", "import_profiles", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_import_profiles_org_id", table_name="import_profiles")
    op.drop_table("import_profiles")
    op.drop_column("scans", "profile")
    op.drop_index("ix_assets_org_cloud_id", table_name="assets")
    op.drop_column("assets", "details")
    op.drop_column("assets", "subtype")
