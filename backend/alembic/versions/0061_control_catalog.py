"""Immutable control catalog releases and reviewed organization category mappings."""
from alembic import op
import sqlalchemy as sa
from app.db.control_catalog import install_v1, uninstall_v1

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(DDL)
    install_v1(op.get_bind())


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM control_catalogs) OR EXISTS(SELECT 1 FROM finding_control_rules)")):
        raise RuntimeError("Export retained catalogs and mapping history before reviewed downgrade")
    uninstall_v1(op.get_bind())
    op.drop_constraint("fk_finding_control_latest", "finding_control_rules", type_="foreignkey")
    op.drop_constraint("fk_finding_control_effective", "finding_control_rules", type_="foreignkey")
    for table in ("finding_control_targets", "finding_control_decisions", "finding_control_rules", "catalog_controls", "control_catalogs"):
        op.drop_table(table)


DDL = r"""
CREATE TABLE control_catalogs (
	id UUID NOT NULL,
	framework VARCHAR(50) NOT NULL,
	edition VARCHAR(100) NOT NULL,
	title VARCHAR(255) NOT NULL,
	source TEXT NOT NULL,
	rights TEXT NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	created_transaction BIGINT DEFAULT (pg_current_xact_id()::text::bigint) NOT NULL,
	installed_by UUID NOT NULL,
	installed_by_label VARCHAR(255) NOT NULL,
	installed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_control_catalog_content UNIQUE (framework, content_hash)
);
CREATE TABLE catalog_controls (
	catalog_id UUID NOT NULL,
	control_id UUID NOT NULL,
	reference VARCHAR(100) NOT NULL,
	title TEXT NOT NULL,
	description TEXT NOT NULL,
	PRIMARY KEY (catalog_id, control_id),
	CONSTRAINT uq_catalog_control_reference UNIQUE (catalog_id, reference),
	FOREIGN KEY(catalog_id) REFERENCES control_catalogs (id) ON DELETE RESTRICT
);
CREATE TABLE finding_control_rules (
	id UUID NOT NULL,
	org_id UUID NOT NULL,
	source VARCHAR(100) NOT NULL,
	domain VARCHAR(50) NOT NULL,
	category VARCHAR(100) NOT NULL,
	version INTEGER NOT NULL,
	effective_version INTEGER,
	PRIMARY KEY (id),
	CONSTRAINT uq_finding_control_rule_key UNIQUE (org_id, source, domain, category),
	CONSTRAINT uq_finding_control_rule_org UNIQUE (org_id, id),
	CONSTRAINT ck_finding_control_rule_generation CHECK (version >= 1 AND (effective_version IS NULL OR (effective_version >= 1 AND effective_version <= version))),
	FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);
CREATE TABLE finding_control_decisions (
	id UUID NOT NULL,
	org_id UUID NOT NULL,
	rule_id UUID NOT NULL,
	version INTEGER NOT NULL,
	state VARCHAR(20) NOT NULL,
	catalog_id UUID NOT NULL,
	proposal_version INTEGER,
	created_transaction BIGINT DEFAULT (pg_current_xact_id()::text::bigint) NOT NULL,
	rationale TEXT NOT NULL,
	actor_id UUID NOT NULL,
	actor_label VARCHAR(255) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_control_decision_rule_org FOREIGN KEY(org_id, rule_id) REFERENCES finding_control_rules (org_id, id) ON DELETE CASCADE,
	CONSTRAINT uq_control_decision_version UNIQUE (rule_id, version),
	CONSTRAINT uq_control_decision_catalog UNIQUE (id, catalog_id),
	CONSTRAINT ck_control_decision_version CHECK (version >= 1),
	CONSTRAINT ck_control_decision_state CHECK (state IN ('proposed','approved','withdrawn')),
	CONSTRAINT ck_control_decision_proposal CHECK ((state='approved' AND proposal_version=version-1 AND proposal_version IS NOT NULL) OR (state<>'approved' AND proposal_version IS NULL)),
	CONSTRAINT fk_control_decision_proposal FOREIGN KEY(rule_id, proposal_version) REFERENCES finding_control_decisions (rule_id, version) DEFERRABLE INITIALLY DEFERRED,
	FOREIGN KEY(catalog_id) REFERENCES control_catalogs (id) ON DELETE RESTRICT
);
CREATE INDEX ix_control_decision_catalog ON finding_control_decisions (catalog_id);
CREATE INDEX ix_control_decision_org_rule ON finding_control_decisions (org_id, rule_id, version);
CREATE TABLE finding_control_targets (
	decision_id UUID NOT NULL,
	catalog_id UUID NOT NULL,
	control_id UUID NOT NULL,
	PRIMARY KEY (decision_id, control_id),
	CONSTRAINT fk_control_target_decision_catalog FOREIGN KEY(decision_id, catalog_id) REFERENCES finding_control_decisions (id, catalog_id) ON DELETE CASCADE,
	CONSTRAINT fk_control_target_revision FOREIGN KEY(catalog_id, control_id) REFERENCES catalog_controls (catalog_id, control_id) ON DELETE RESTRICT
);
CREATE INDEX ix_control_target_catalog_control ON finding_control_targets (catalog_id, control_id);
ALTER TABLE finding_control_rules ADD CONSTRAINT fk_finding_control_effective FOREIGN KEY(id, effective_version) REFERENCES finding_control_decisions (rule_id, version) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE finding_control_rules ADD CONSTRAINT fk_finding_control_latest FOREIGN KEY(id, version) REFERENCES finding_control_decisions (rule_id, version) DEFERRABLE INITIALLY DEFERRED;
"""
