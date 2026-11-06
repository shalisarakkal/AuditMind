"""Durable import abort requests and fenced publication connection identity."""
from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("scans", sa.Column("abort_requested_at", sa.DateTime(timezone=True)))
    op.add_column("scans", sa.Column("publication_pid", sa.Integer()))
    op.add_column("scans", sa.Column("publication_backend_start", sa.DateTime(timezone=True)))


def downgrade():
    for name in ("publication_backend_start", "publication_pid", "abort_requested_at"):
        op.drop_column("scans", name)
