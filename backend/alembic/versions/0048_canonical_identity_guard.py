"""Index captured native identity for cross-pair conflict checks."""
from alembic import op
import sqlalchemy as sa
revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    # Captured context is unchanged; no asset/finding scan or data rewrite.
    op.create_index("ix_finding_canonical_identity", "finding_canonical_decisions",
        ["org_id", sa.text("(context ->> 'candidate_key')"), "pair_key", "version"])


def downgrade():
    op.drop_index("ix_finding_canonical_identity", table_name="finding_canonical_decisions")
