"""Separate default-off policy and versioned private publication admission."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('observation_publication_decisions', sa.Column('admission_contract', sa.String(80), nullable=False, server_default=sa.text("'reserved-storage-v1'")))
    op.add_column('observation_publication_decisions', sa.Column('source_context_hash', sa.String(64)))
    op.create_check_constraint('ck_publication_source_hash', 'observation_publication_decisions', 'source_context_hash IS NULL OR length(source_context_hash) = 64')
    op.create_table('organization_publication_settings',
        sa.Column('org_id', pg.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('version >= 0', name='ck_publication_settings_version'))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM observation_publication_decisions WHERE admission_contract <> 'reserved-storage-v1') OR EXISTS(SELECT 1 FROM organization_publication_settings WHERE version > 0 OR enabled)")):
        raise RuntimeError('Retained publication admission or policy history requires a reviewed export/rollback procedure')
    op.drop_table('organization_publication_settings')
    op.drop_constraint('ck_publication_source_hash', 'observation_publication_decisions', type_='check')
    op.drop_column('observation_publication_decisions', 'source_context_hash')
    op.drop_column('observation_publication_decisions', 'admission_contract')
