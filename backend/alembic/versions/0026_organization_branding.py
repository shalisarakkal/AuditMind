"""Organization header name visibility, enabled for existing organizations."""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("show_name_in_header", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("organizations", "show_name_in_header")
