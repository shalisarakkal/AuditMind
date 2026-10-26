"""Persist author timezone and fixed finding expiry instants; legacy dates Eastern."""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    for prefix, column in (("due", "due_date"), ("risk_review", "risk_review_date")):
        op.add_column("findings", sa.Column(f"{prefix}_timezone", sa.String(100)))
        op.add_column("findings", sa.Column(f"{prefix}_expires_at", sa.DateTime(timezone=True)))
    # One scan of potentially millions of findings, not one per deadline field.
    op.execute(sa.text("""UPDATE findings SET
        due_timezone=CASE WHEN due_date IS NOT NULL THEN 'America/New_York' END,
        due_expires_at=((due_date+1)::timestamp AT TIME ZONE 'America/New_York'),
        risk_review_timezone=CASE WHEN risk_review_date IS NOT NULL THEN 'America/New_York' END,
        risk_review_expires_at=((risk_review_date+1)::timestamp AT TIME ZONE 'America/New_York')
        WHERE due_date IS NOT NULL OR risk_review_date IS NOT NULL"""))


def downgrade():
    for prefix in ("due", "risk_review"):
        op.drop_column("findings", f"{prefix}_expires_at")
        op.drop_column("findings", f"{prefix}_timezone")
