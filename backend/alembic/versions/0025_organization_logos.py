"""Authenticated, bounded organization branding stored with tenant data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("organization_logos",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(36), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("octet_length(image) BETWEEN 1 AND 1048576", name="organization_logo_size"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id"))


def downgrade():
    op.drop_table("organization_logos")
