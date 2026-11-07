"""Verified status-aware scoring with platform inheritance and proof decisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from app.db.status_scoring_revision import install_v3,uninstall_v3

revision='0045'
down_revision='0044'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('organization_risk_policies',
        sa.Column('org_id',pg.UUID(),sa.ForeignKey('organizations.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('enabled_override',sa.Boolean()),
        sa.Column('version',sa.Integer(),nullable=False,server_default='0'))
    for name,type_,options in (
        ('risk_verification_state',sa.String(20),dict(nullable=False,server_default='unverified')),
        ('risk_verification_version',sa.Integer(),dict(nullable=False,server_default='0')),
        ('risk_verified_workflow_version',sa.Integer(),{}),
        ('risk_verified_at',sa.DateTime(timezone=True),{}),
        ('risk_verification_expires_at',sa.DateTime(timezone=True),{}),
        ('risk_verified_observation_count',sa.BigInteger(),{}),
        ('risk_verification_source_kind',sa.String(20),{}),
        ('risk_verification_document_id',pg.UUID(),{}),
        ('risk_verification_source_hash',sa.String(64),{})):
        op.add_column('findings',sa.Column(name,type_,**options))
    op.create_table('finding_verifications',
        sa.Column('id',pg.UUID(),primary_key=True),
        sa.Column('org_id',pg.UUID(),sa.ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False),
        sa.Column('finding_id',pg.UUID(),sa.ForeignKey('findings.id',ondelete='CASCADE'),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('workflow_version',sa.Integer(),nullable=False),
        sa.Column('workflow_status',sa.String(20),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),
        sa.Column('source_reference',sa.String(2048),nullable=False),
        sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('source_sha256',sa.String(64)),
        sa.Column('source_observation_count',sa.BigInteger(),nullable=False),
        sa.Column('submitter_id',pg.UUID(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('submitter_label',sa.String(255),nullable=False),
        sa.Column('actor_id',pg.UUID(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('actor_label',sa.String(255),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True)),
        sa.Column('attestation',pg.JSONB(),nullable=False),
        sa.UniqueConstraint('finding_id','version',name='uq_finding_verification_version'))
    op.create_index('ix_finding_verifications_org_id','finding_verifications',['org_id'])
    op.create_index('ix_finding_verifications_finding_id','finding_verifications',['finding_id'])
    op.create_index('ix_findings_risk_verified','findings',['org_id','domain','severity','risk_verification_expires_at'],
        postgresql_where=sa.text("archived_at IS NULL AND risk_verification_state='approved'"))
    op.add_column('risk_scores',sa.Column('scoring_context',pg.JSONB()))
    install_v3(op.get_bind())
    op.execute('UPDATE organization_list_revisions SET epoch=gen_random_uuid()')


def downgrade():
    uninstall_v3(op.get_bind())
    op.drop_column('risk_scores','scoring_context')
    op.drop_index('ix_findings_risk_verified',table_name='findings')
    op.drop_table('finding_verifications')
    for name in ('risk_verification_source_hash','risk_verification_document_id','risk_verification_source_kind',
        'risk_verified_observation_count','risk_verification_expires_at','risk_verified_at',
        'risk_verified_workflow_version','risk_verification_version','risk_verification_state'):
        op.drop_column('findings',name)
    op.drop_table('organization_risk_policies')
    op.execute('UPDATE organization_list_revisions SET epoch=gen_random_uuid()')
