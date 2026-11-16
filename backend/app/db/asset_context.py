"""Frozen v1 context ownership and list invalidation; new contracts need a migration."""
from sqlalchemy import event

def install_v1(connection):
    schema=connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    # Identifiers embedded inside PL/pgSQL string literals need both layers
    # of quoting, even though ordinary identifier positions use schema.
    literal_schema=schema.replace("'", "''")
    connection.exec_driver_sql(f"""
CREATE OR REPLACE FUNCTION {schema}.am_asset_context_guard_v1() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 IF NOT pg_try_advisory_xact_lock(33014,hashtext(NEW.asset_id::text)) THEN
  RAISE EXCEPTION 'Asset context is busy; retry' USING ERRCODE='55P03';
 END IF;
 IF TG_OP='UPDATE' AND (NEW.asset_id,NEW.org_id) IS DISTINCT FROM (OLD.asset_id,OLD.org_id) THEN
  RAISE EXCEPTION 'Asset context ownership is immutable' USING ERRCODE='23514';
 END IF;
 PERFORM 1 FROM {schema}.assets WHERE id=NEW.asset_id AND org_id=NEW.org_id FOR KEY SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Asset context requires a same-organization asset' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='asset_contexts' THEN
  IF NEW.owner_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.owner_id IS DISTINCT FROM OLD.owner_id) THEN
   PERFORM 1 FROM {schema}.org_memberships m JOIN {schema}.users u ON u.id=m.user_id
    WHERE m.org_id=NEW.org_id AND m.user_id=NEW.owner_id AND u.is_active FOR KEY SHARE OF m,u;
   IF NOT FOUND THEN RAISE EXCEPTION 'Asset owner must be an active organization member' USING ERRCODE='23514'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $guard$;
CREATE OR REPLACE FUNCTION {schema}.am_asset_context_tenant_v1() RETURNS trigger LANGUAGE plpgsql AS $tenant$
BEGIN
 IF NEW.org_id IS DISTINCT FROM OLD.org_id THEN
  IF NOT pg_try_advisory_xact_lock(33014,hashtext(NEW.id::text)) THEN
   RAISE EXCEPTION 'Asset context is busy; retry' USING ERRCODE='55P03';
  END IF;
  IF EXISTS(SELECT 1 FROM {schema}.asset_contexts WHERE asset_id=OLD.id)
   OR EXISTS(SELECT 1 FROM {schema}.asset_context_history WHERE asset_id=OLD.id) THEN
   RAISE EXCEPTION 'Retained context prevents asset tenant transfer' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $tenant$;
CREATE OR REPLACE FUNCTION {schema}.am_asset_context_revision_v1() RETURNS trigger LANGUAGE plpgsql AS $revision$
DECLARE changed text;
BEGIN
 IF TG_OP='TRUNCATE' THEN changed:='SELECT id AS org_id FROM {literal_schema}.organizations';
 ELSIF TG_TABLE_NAME='asset_contexts' THEN
  IF TG_OP='INSERT' THEN changed:='SELECT org_id FROM context_new';
  ELSIF TG_OP='DELETE' THEN changed:='SELECT org_id FROM context_old';
  ELSE changed:='SELECT n.org_id FROM context_new n JOIN context_old o ON n.asset_id=o.asset_id WHERE
   (n.owner_id,n.owner_label,n.environment,n.business_criticality,n.version) IS DISTINCT FROM
   (o.owner_id,o.owner_label,o.environment,o.business_criticality,o.version)'; END IF;
 ELSIF TG_TABLE_NAME='users' THEN
  IF TG_OP='UPDATE' THEN
   IF NOT EXISTS(SELECT 1 FROM context_new n JOIN context_old o ON n.id=o.id WHERE
    (n.name,n.email,n.is_active) IS DISTINCT FROM (o.name,o.email,o.is_active)) THEN RETURN NULL; END IF;
   changed:='SELECT n.id FROM context_new n JOIN context_old o ON n.id=o.id WHERE
    (n.name,n.email,n.is_active) IS DISTINCT FROM (o.name,o.email,o.is_active)';
  ELSIF TG_OP='INSERT' THEN changed:='SELECT id FROM context_new';
  ELSE changed:='SELECT id FROM context_old'; END IF;
  changed:='SELECT c.org_id FROM ('||changed||') u JOIN {literal_schema}.asset_contexts c ON c.owner_id=u.id';
 ELSE
  IF TG_OP='UPDATE' THEN RETURN NULL;
  ELSIF TG_OP='INSERT' THEN changed:='SELECT user_id,org_id FROM context_new';
  ELSE changed:='SELECT user_id,org_id FROM context_old'; END IF;
  changed:='SELECT c.org_id FROM ('||changed||') m JOIN {literal_schema}.asset_contexts c ON c.org_id=m.org_id AND c.owner_id=m.user_id';
 END IF;
 EXECUTE 'INSERT INTO {literal_schema}.organization_asset_context_revisions AS dst (org_id,revision)
  SELECT DISTINCT a.org_id,1 FROM ('||changed||') a JOIN {literal_schema}.organizations o ON o.id=a.org_id
  ORDER BY a.org_id ON CONFLICT(org_id) DO UPDATE SET revision=dst.revision+1';
 RETURN NULL;
END $revision$;
""")
    for table in ('asset_contexts','asset_context_history'):
        connection.exec_driver_sql(f"CREATE OR REPLACE TRIGGER am_asset_context_guard BEFORE INSERT OR UPDATE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION {schema}.am_asset_context_guard_v1()")
    connection.exec_driver_sql(f"CREATE OR REPLACE TRIGGER am_asset_context_tenant BEFORE UPDATE OF org_id ON {schema}.assets FOR EACH ROW EXECUTE FUNCTION {schema}.am_asset_context_tenant_v1()")
    for table in ('asset_contexts','users','org_memberships'):
        for operation,transition in (('INSERT','REFERENCING NEW TABLE AS context_new'),('DELETE','REFERENCING OLD TABLE AS context_old'),('UPDATE','REFERENCING OLD TABLE AS context_old NEW TABLE AS context_new'),('TRUNCATE','')):
            connection.exec_driver_sql(f"CREATE OR REPLACE TRIGGER am_asset_context_revision_{operation.lower()} AFTER {operation} ON {schema}.{table} {transition} FOR EACH STATEMENT EXECUTE FUNCTION {schema}.am_asset_context_revision_v1()")

def uninstall_v1(connection):
    schema=connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    for table in ('asset_contexts','users','org_memberships'):
        for operation in ('insert','delete','update','truncate'):
            connection.exec_driver_sql(f"DROP TRIGGER am_asset_context_revision_{operation} ON {schema}.{table}")
    for table in ('asset_contexts','asset_context_history'):
        connection.exec_driver_sql(f"DROP TRIGGER am_asset_context_guard ON {schema}.{table}")
    connection.exec_driver_sql(f"DROP TRIGGER am_asset_context_tenant ON {schema}.assets")
    for name in ('guard','tenant','revision'):
        connection.exec_driver_sql(f"DROP FUNCTION {schema}.am_asset_context_{name}_v1()")

def register(metadata):
    @event.listens_for(metadata,'after_create')
    def create_context_triggers(target,connection,**kwargs):
        if 'asset_context_history' in {t.name for t in kwargs.get('tables',[])}: install_v1(connection)
