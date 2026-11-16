"""Separate organization-managed asset context; no imported-field backfill."""
from alembic import op
import sqlalchemy as sa
from app.db.asset_context import install_v1, uninstall_v1
revision='0059'
down_revision='0058'
branch_labels=None
depends_on=None

def upgrade():
    op.execute(DDL)
    install_v1(op.get_bind())

def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM asset_contexts) OR EXISTS(SELECT 1 FROM asset_context_history) OR EXISTS(SELECT 1 FROM organization_asset_context_revisions WHERE revision>0)")):
        raise RuntimeError('Export retained asset context/history before a reviewed downgrade')
    uninstall_v1(op.get_bind())
    op.drop_table('organization_asset_context_revisions')
    op.drop_table('asset_context_history')
    op.drop_table('asset_contexts')

DDL=r"""
CREATE TABLE asset_contexts (
	asset_id UUID NOT NULL,
	org_id UUID NOT NULL,
	owner_id UUID,
	owner_label VARCHAR(255),
	environment VARCHAR(50),
	business_criticality VARCHAR(10),
	version INTEGER NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (asset_id),
	CONSTRAINT ck_asset_context_version CHECK (version >= 1),
	CONSTRAINT ck_asset_context_criticality CHECK (business_criticality IS NULL OR business_criticality IN ('critical','high','medium','low')),
	FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);
CREATE INDEX ix_asset_context_org_business_criticality ON asset_contexts (org_id, business_criticality, asset_id);
CREATE INDEX ix_asset_context_org_environment ON asset_contexts (org_id, environment, asset_id);
CREATE INDEX ix_asset_context_org_owner_id ON asset_contexts (org_id, owner_id, asset_id);
CREATE INDEX ix_asset_context_owner_org ON asset_contexts (owner_id, org_id) WHERE owner_id IS NOT NULL;
CREATE TABLE asset_context_history (
	id UUID NOT NULL,
	org_id UUID NOT NULL,
	asset_id UUID NOT NULL,
	actor_id UUID,
	actor_label VARCHAR(255) NOT NULL,
	version INTEGER NOT NULL,
	before JSONB NOT NULL,
	after JSONB NOT NULL,
	rationale TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_asset_context_history_version UNIQUE (asset_id, version),
	FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE,
	FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_asset_context_history_org_asset ON asset_context_history (org_id, asset_id, version);
CREATE TABLE organization_asset_context_revisions (
	org_id UUID NOT NULL,
	revision BIGINT DEFAULT 0 NOT NULL,
	PRIMARY KEY (org_id),
	FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);
"""
