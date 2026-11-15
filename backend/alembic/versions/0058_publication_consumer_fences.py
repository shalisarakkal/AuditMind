"""Publication consumer epoch and indexed source lifecycle protection."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('organization_publication_revisions',
        sa.Column('org_id', pg.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='0'))
    op.execute(GUARDS)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM organization_publication_revisions WHERE revision > 0) OR EXISTS(SELECT 1 FROM observation_publication_decisions WHERE admission_contract='observation-publication-consumers-v1')")):
        raise RuntimeError('Retained consumer publication history requires reviewed rollback')
    for table in ('assets','scans','findings','identity_tools','finding_observations','observation_identity_bindings','asset_scans'):
        op.execute(f'DROP TRIGGER IF EXISTS am_publication_source_guard ON {table}')
    op.execute('DROP FUNCTION am_publication_source_guard()')
    op.execute('DROP FUNCTION am_publication_affected(uuid,text,uuid)')
    op.drop_table('organization_publication_revisions')


GUARDS = r"""
CREATE FUNCTION am_publication_affected(owner uuid, kind text, target uuid)
RETURNS boolean LANGUAGE plpgsql STABLE SET search_path FROM CURRENT AS $affected$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM observation_publication_states WHERE org_id=owner AND state='active') THEN RETURN false; END IF;
 RETURN EXISTS(
 SELECT 1 FROM observation_publication_states s
 JOIN observation_publication_decisions r ON r.org_id=s.org_id AND r.id=s.decision_id
 WHERE s.org_id=owner AND s.state='active' AND r.admission_contract='observation-publication-consumers-v1'
 AND s.finding_id IN (
   SELECT target WHERE kind='finding'
   UNION
   SELECT r.finding_id FROM observation_publication_dependencies d
   JOIN observation_publication_decisions r ON r.org_id=d.org_id AND r.id=d.decision_id
   JOIN observation_publication_states live ON live.org_id=r.org_id AND live.decision_id=r.id AND live.state='active'
   WHERE d.org_id=owner AND d.resource_kind=kind AND d.resource_id=target
   UNION
   SELECT o.finding_id FROM finding_observations o WHERE kind='scan' AND o.org_id=owner AND o.scan_id=target
   UNION
   SELECT o.finding_id FROM finding_observations o WHERE kind='observation' AND o.org_id=owner AND o.id=target
   UNION
   SELECT o.finding_id FROM finding_observations o WHERE kind='asset' AND o.org_id=owner AND o.asset_identity->>'asset_id'=target::text
   UNION
   SELECT r.finding_id FROM asset_scans a
   JOIN observation_publication_dependencies d ON d.org_id=owner AND d.resource_kind='asset' AND d.resource_id=a.asset_id
   JOIN observation_publication_decisions r ON r.org_id=d.org_id AND r.id=d.decision_id
   JOIN observation_publication_states live ON live.org_id=r.org_id AND live.decision_id=r.id AND live.state='active'
   WHERE kind='scan' AND a.scan_id=target AND a.created
   UNION
   SELECT o.finding_id FROM asset_scans a JOIN finding_observations o
     ON o.org_id=owner AND o.asset_identity->>'asset_id'=a.asset_id::text
   WHERE kind='scan' AND a.scan_id=target AND a.created
 ));
END
$affected$;

CREATE FUNCTION am_publication_source_guard() RETURNS trigger LANGUAGE plpgsql SET search_path FROM CURRENT AS $guard$
DECLARE owner uuid; target uuid; kind text;
BEGIN
 IF TG_OP='INSERT' THEN
   IF TG_TABLE_NAME='asset_scans' THEN
     IF NOT NEW.created THEN RETURN NEW; END IF;
     SELECT org_id INTO owner FROM assets WHERE id=NEW.asset_id;
     target:=NEW.asset_id; kind:='asset';
   ELSE
     owner:=NEW.org_id; target:=NEW.observation_id; kind:='observation';
   END IF;
 ELSIF TG_TABLE_NAME='asset_scans' THEN
   IF TG_OP='DELETE' AND NOT OLD.created THEN RETURN OLD; END IF;
   IF TG_OP='UPDATE' THEN
     IF NOT OLD.created AND NOT NEW.created THEN RETURN NEW; END IF;
   END IF;
   SELECT org_id INTO owner FROM assets WHERE id=OLD.asset_id;
   target:=OLD.asset_id; kind:='asset';
 ELSE
   owner:=OLD.org_id;
   target:=OLD.id;
   kind:=CASE TG_TABLE_NAME WHEN 'assets' THEN 'asset' WHEN 'scans' THEN 'scan'
     WHEN 'findings' THEN 'finding' WHEN 'identity_tools' THEN 'tool'
     WHEN 'finding_observations' THEN 'observation' ELSE 'identity_binding' END;
 END IF;
 IF TG_OP='UPDATE' THEN
   IF TG_TABLE_NAME='asset_scans' THEN
     IF ROW(OLD.scan_id,OLD.asset_id,OLD.created) IS NOT DISTINCT FROM ROW(NEW.scan_id,NEW.asset_id,NEW.created) THEN RETURN NEW; END IF;
     IF NEW.created AND am_publication_affected((SELECT org_id FROM assets WHERE id=NEW.asset_id),'asset',NEW.asset_id) THEN
       RAISE EXCEPTION 'Undo the active observation publication before changing creator ownership' USING ERRCODE='23514';
     END IF;
   END IF;
   IF TG_TABLE_NAME='observation_identity_bindings' THEN
     -- Account purge may clear its FK; immutable review material and label stay.
     IF (to_jsonb(OLD)-'actor_id') IS NOT DISTINCT FROM (to_jsonb(NEW)-'actor_id')
       AND (OLD.actor_id IS NOT DISTINCT FROM NEW.actor_id OR NEW.actor_id IS NULL) THEN RETURN NEW; END IF;
     IF am_publication_affected(NEW.org_id,'observation',NEW.observation_id) THEN
       RAISE EXCEPTION 'Undo the active observation publication before changing source identity' USING ERRCODE='23514';
     END IF;
   END IF;
   IF TG_TABLE_NAME='assets' THEN
   IF ROW(OLD.org_id,OLD.id,OLD.type,OLD.hostname,OLD.ip,OLD.cloud_id,OLD.archived_at)
     IS NOT DISTINCT FROM ROW(NEW.org_id,NEW.id,NEW.type,NEW.hostname,NEW.ip,NEW.cloud_id,NEW.archived_at)
     THEN RETURN NEW; END IF;
   END IF;
   IF TG_TABLE_NAME='scans' THEN
   IF ROW(OLD.org_id,OLD.id,OLD.filename,OLD.scan_type,OLD.profile,OLD.ingestion_config_fingerprint,OLD.content_hash,OLD.status,OLD.archived_at)
     IS NOT DISTINCT FROM ROW(NEW.org_id,NEW.id,NEW.filename,NEW.scan_type,NEW.profile,NEW.ingestion_config_fingerprint,NEW.content_hash,NEW.status,NEW.archived_at)
     THEN RETURN NEW; END IF;
   END IF;
   IF TG_TABLE_NAME='findings' THEN
     IF ROW(OLD.org_id,OLD.id,OLD.scan_id,OLD.asset_id,OLD.archived_at)
       IS NOT DISTINCT FROM ROW(NEW.org_id,NEW.id,NEW.scan_id,NEW.asset_id,NEW.archived_at) THEN RETURN NEW; END IF;
   END IF;
 END IF;
 -- Organization purge owns all retained data and is not single-source recovery.
 IF NOT EXISTS(SELECT 1 FROM organizations WHERE id=owner) THEN
   IF TG_OP='DELETE' THEN RETURN OLD; END IF;
   RETURN NEW;
 END IF;
 IF am_publication_affected(owner,kind,target) THEN
   RAISE EXCEPTION 'Undo the active observation publication before changing or removing a retained source'
     USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $guard$;
CREATE TRIGGER am_publication_source_guard BEFORE UPDATE OF org_id,id,type,hostname,ip,cloud_id,archived_at OR DELETE ON assets FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
CREATE TRIGGER am_publication_source_guard BEFORE UPDATE OF org_id,id,filename,scan_type,profile,ingestion_config_fingerprint,content_hash,status,archived_at OR DELETE ON scans FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
CREATE TRIGGER am_publication_source_guard BEFORE UPDATE OF org_id,id,scan_id,asset_id,archived_at OR DELETE ON findings FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
CREATE TRIGGER am_publication_source_guard BEFORE UPDATE OR DELETE ON identity_tools FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
CREATE TRIGGER am_publication_source_guard BEFORE UPDATE OR DELETE ON finding_observations FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
CREATE TRIGGER am_publication_source_guard BEFORE INSERT OR UPDATE OR DELETE ON observation_identity_bindings FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
CREATE TRIGGER am_publication_source_guard BEFORE INSERT OR UPDATE OR DELETE ON asset_scans FOR EACH ROW EXECUTE FUNCTION am_publication_source_guard();
"""
