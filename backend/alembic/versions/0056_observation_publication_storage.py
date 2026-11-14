"""Reserved source-owned publication storage; no enabled publication writer."""
from alembic import op
import sqlalchemy as sa
revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE observation_publication_decisions (
	id UUID NOT NULL,
	org_id UUID NOT NULL,
	finding_id UUID NOT NULL,
	observation_id UUID NOT NULL,
	source_scan_id UUID NOT NULL,
	request_id UUID NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	before_hash VARCHAR(64) NOT NULL,
	after_hash VARCHAR(64) NOT NULL,
	mapping_version VARCHAR(80) NOT NULL,
	version INTEGER NOT NULL,
	operation VARCHAR(10) NOT NULL,
	rationale TEXT NOT NULL,
	actor_id UUID,
	actor_label VARCHAR(255) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_observation_publication_version UNIQUE (org_id, finding_id, version),
	CONSTRAINT uq_observation_publication_request UNIQUE (org_id, request_id),
	CONSTRAINT uq_observation_publication_owner UNIQUE (org_id, id),
	CONSTRAINT uq_publication_snapshot_target UNIQUE (org_id, finding_id, id),
	CONSTRAINT uq_publication_state_target UNIQUE (org_id, finding_id, id, version),
	CONSTRAINT ck_observation_publication_version CHECK (version > 0),
	CONSTRAINT ck_observation_publication_operation CHECK (operation IN ('publish','undo')),
	CONSTRAINT ck_observation_publication_rationale CHECK (length(btrim(rationale)) BETWEEN 1 AND 2000),
	CONSTRAINT ck_observation_publication_hashes CHECK (length(request_hash) = 64 AND length(before_hash) = 64 AND length(after_hash) = 64),
	FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE,
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
)
""")
    op.execute('CREATE INDEX ix_observation_publication_actor ON observation_publication_decisions (actor_id)')
    op.execute("""
CREATE TABLE observation_publication_snapshots (
	id UUID NOT NULL,
	org_id UUID NOT NULL,
	decision_id UUID NOT NULL,
	finding_id UUID NOT NULL,
	source_scan_id UUID NOT NULL,
	side VARCHAR(6) NOT NULL,
	payload JSONB NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_publication_snapshot_decision FOREIGN KEY(org_id, finding_id, decision_id) REFERENCES observation_publication_decisions (org_id, finding_id, id) ON DELETE CASCADE,
	CONSTRAINT uq_publication_snapshot_side UNIQUE (org_id, decision_id, side),
	CONSTRAINT ck_publication_snapshot_side CHECK (side IN ('before','after')),
	CONSTRAINT ck_publication_snapshot_object CHECK (jsonb_typeof(payload) = 'object'),
	FOREIGN KEY(finding_id) REFERENCES findings (id) ON DELETE CASCADE,
	FOREIGN KEY(source_scan_id) REFERENCES scans (id) ON DELETE CASCADE
)
""")
    op.execute('CREATE INDEX ix_publication_snapshot_finding ON observation_publication_snapshots (finding_id)')
    op.execute('CREATE INDEX ix_publication_snapshot_scan ON observation_publication_snapshots (source_scan_id)')
    op.execute("""
CREATE TABLE observation_publication_states (
	org_id UUID NOT NULL,
	finding_id UUID NOT NULL,
	decision_id UUID NOT NULL,
	version INTEGER NOT NULL,
	state VARCHAR(8) NOT NULL,
	PRIMARY KEY (org_id, finding_id),
	CONSTRAINT fk_publication_state_decision FOREIGN KEY(org_id, finding_id, decision_id, version) REFERENCES observation_publication_decisions (org_id, finding_id, id, version) ON DELETE CASCADE,
	CONSTRAINT ck_publication_state_version CHECK (version > 0),
	CONSTRAINT ck_publication_state CHECK (state IN ('active','undone')),
	FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
)
""")
    op.execute("CREATE INDEX ix_publication_state_active ON observation_publication_states (org_id, decision_id) WHERE state = 'active'")
    op.execute("""
CREATE TABLE observation_publication_dependencies (
	id UUID NOT NULL,
	org_id UUID NOT NULL,
	decision_id UUID NOT NULL,
	resource_kind VARCHAR(20) NOT NULL,
	resource_id UUID NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_publication_dependency_decision FOREIGN KEY(org_id, decision_id) REFERENCES observation_publication_decisions (org_id, id) ON DELETE CASCADE,
	CONSTRAINT uq_publication_dependency UNIQUE (org_id, decision_id, resource_kind, resource_id),
	CONSTRAINT ck_publication_dependency_kind CHECK (resource_kind IN ('finding','observation','scan','asset','tool','identity_binding'))
)
""")
    op.execute('CREATE INDEX ix_publication_dependency_resource ON observation_publication_dependencies (org_id, resource_kind, resource_id, decision_id)')
    op.execute("""
CREATE OR REPLACE FUNCTION am_publication_snapshot_owner_v1()
RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM findings WHERE id=NEW.finding_id
            AND org_id=NEW.org_id FOR KEY SHARE)
        OR NOT EXISTS (SELECT 1 FROM scans WHERE id=NEW.source_scan_id
            AND org_id=NEW.org_id FOR KEY SHARE) THEN
        RAISE EXCEPTION 'Publication snapshot requires same-organization live owners'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END
$guard$;
CREATE TRIGGER publication_snapshot_owner
BEFORE INSERT OR UPDATE OF org_id, finding_id, source_scan_id
ON observation_publication_snapshots
FOR EACH ROW EXECUTE FUNCTION am_publication_snapshot_owner_v1();
""")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM observation_publication_decisions)")):
        raise RuntimeError("Export retained publication receipts and complete the reviewed rollback procedure before downgrade")
    op.drop_table('observation_publication_dependencies')
    op.drop_table('observation_publication_states')
    op.drop_table('observation_publication_snapshots')
    op.drop_table('observation_publication_decisions')
    op.execute('DROP FUNCTION IF EXISTS am_publication_snapshot_owner_v1()')
