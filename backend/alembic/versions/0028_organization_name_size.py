"""Configurable header organization name typography."""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("header_name_size", sa.String(6), nullable=False, server_default="medium"))
    op.create_check_constraint("organization_header_name_size", "organizations", "header_name_size IN ('small', 'medium', 'large')")


def downgrade():
    op.drop_constraint("organization_header_name_size", "organizations", type_="check")
    op.drop_column("organizations", "header_name_size")
