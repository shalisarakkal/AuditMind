"""Fence cancellation against pooled backend reuse after publication rollback."""
from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("scans", sa.Column("publication_xact_start", sa.DateTime(timezone=True)))
    op.add_column("scans", sa.Column("publication_xid", sa.BigInteger()))


def downgrade():
    op.drop_column("scans", "publication_xid")
    op.drop_column("scans", "publication_xact_start")
