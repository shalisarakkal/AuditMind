"""Separate default-off organization opt-in for reviewed native pair publication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0055'
down_revision='0054'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('organization_consolidation_settings',
        sa.Column('org_id',pg.UUID(as_uuid=True),sa.ForeignKey('organizations.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('enabled',sa.Boolean(),nullable=False,server_default=sa.text('false')),
        sa.Column('version',sa.Integer(),nullable=False,server_default='0'))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM finding_consolidations g JOIN findings f ON f.org_id=g.org_id AND f.id=g.canonical_finding_id AND f.consolidation_id=g.id WHERE g.state='active')")):
        raise RuntimeError('Undo published consolidations before removing their feature setting')
    op.drop_table('organization_consolidation_settings')
