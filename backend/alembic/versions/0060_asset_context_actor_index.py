"""Index retained actor references for account removal without a history scan."""
from alembic import op
import sqlalchemy as sa

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_asset_context_history_actor", "asset_context_history", ["actor_id"], postgresql_where=sa.text("actor_id IS NOT NULL"))


def downgrade():
    op.drop_index("ix_asset_context_history_actor", table_name="asset_context_history")
