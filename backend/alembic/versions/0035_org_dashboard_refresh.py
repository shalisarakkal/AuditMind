"""Inheritable organization Dashboard refresh intervals."""
from alembic import op
import sqlalchemy as sa
revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("dashboard_refresh_interval_seconds", sa.Integer()))
    op.add_column("organizations", sa.Column("dashboard_refresh_settings_version", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.create_check_constraint("organization_dashboard_refresh_interval", "organizations",
        "dashboard_refresh_interval_seconds IS NULL OR dashboard_refresh_interval_seconds BETWEEN 60 AND 86400")
    op.create_check_constraint("organization_dashboard_refresh_version", "organizations", "dashboard_refresh_settings_version >= 0")


def downgrade():
    op.drop_constraint("organization_dashboard_refresh_version", "organizations", type_="check")
    op.drop_constraint("organization_dashboard_refresh_interval", "organizations", type_="check")
    op.drop_column("organizations", "dashboard_refresh_settings_version")
    op.drop_column("organizations", "dashboard_refresh_interval_seconds")
