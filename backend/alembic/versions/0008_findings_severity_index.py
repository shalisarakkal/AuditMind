"""findings index for the dashboard's most severe findings (org, severity,
newest first), so it doesn't sort every finding of the org.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_findings_org_severity_created", "findings", ["org_id", "severity", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_findings_org_severity_created", table_name="findings")
