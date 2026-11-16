"""Frozen v1 catalog and decision immutability; evolve through new migrations."""
from sqlalchemy import event

TABLES = ("control_catalogs", "catalog_controls", "finding_control_rules", "finding_control_decisions", "finding_control_targets")


def install_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.exec_driver_sql(f"""
CREATE OR REPLACE FUNCTION {schema}.am_control_catalog_guard_v1() RETURNS trigger LANGUAGE plpgsql AS $guard$
DECLARE review_state text;
BEGIN
 IF TG_TABLE_NAME='finding_control_rules' THEN
  IF TG_OP='UPDATE' THEN
   IF (NEW.id,NEW.org_id,NEW.source,NEW.domain,NEW.category) IS DISTINCT FROM
      (OLD.id,OLD.org_id,OLD.source,OLD.domain,OLD.category) OR NEW.version<>OLD.version+1 THEN
    RAISE EXCEPTION 'Control rule identity is immutable and generation must advance once' USING ERRCODE='23514';
   END IF;
   SELECT state INTO review_state FROM {schema}.finding_control_decisions WHERE rule_id=NEW.id AND org_id=NEW.org_id AND version=NEW.version;
   IF FOUND AND ((review_state='approved' AND NEW.effective_version IS DISTINCT FROM NEW.version)
     OR (review_state='proposed' AND NEW.effective_version IS DISTINCT FROM OLD.effective_version)
     OR (review_state='withdrawn' AND NEW.effective_version IS NOT NULL)) THEN
    RAISE EXCEPTION 'Effective mapping must match its committed review state' USING ERRCODE='23514';
   END IF;
  END IF;
  IF TG_OP IN ('INSERT','UPDATE') AND NEW.effective_version IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM {schema}.finding_control_decisions WHERE rule_id=NEW.id AND org_id=NEW.org_id
      AND version=NEW.effective_version AND state='approved') THEN
   RAISE EXCEPTION 'Effective mapping requires an approved same-organization decision' USING ERRCODE='23514';
  END IF;
  IF TG_OP<>'DELETE' THEN RETURN NEW; END IF;
 ELSIF TG_OP='INSERT' THEN
  IF TG_TABLE_NAME='catalog_controls' THEN
   IF NOT EXISTS(SELECT 1 FROM {schema}.control_catalogs WHERE id=NEW.catalog_id AND created_transaction=pg_current_xact_id()::text::bigint) THEN
    RAISE EXCEPTION 'Catalog control set is sealed after installation' USING ERRCODE='23514';
   END IF;
  ELSIF TG_TABLE_NAME='finding_control_targets' THEN
   IF NOT EXISTS(SELECT 1 FROM {schema}.finding_control_decisions WHERE id=NEW.decision_id AND catalog_id=NEW.catalog_id AND created_transaction=pg_current_xact_id()::text::bigint) THEN
    RAISE EXCEPTION 'Mapping target set is sealed after decision commit' USING ERRCODE='23514';
   END IF;
  END IF;
  RETURN NEW;
 ELSIF TG_OP='UPDATE' THEN
  RAISE EXCEPTION 'Catalog releases and mapping decisions are immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN
  IF TG_TABLE_NAME IN ('control_catalogs','catalog_controls') THEN
   RAISE EXCEPTION 'Retained catalog releases cannot be deleted' USING ERRCODE='23514';
  ELSIF TG_TABLE_NAME IN ('finding_control_rules','finding_control_decisions') THEN
   IF EXISTS(SELECT 1 FROM {schema}.organizations WHERE id=OLD.org_id) THEN
    RAISE EXCEPTION 'Mapping review history is retained until organization purge' USING ERRCODE='23514';
   END IF;
  ELSIF EXISTS(SELECT 1 FROM {schema}.finding_control_decisions d JOIN {schema}.organizations o ON o.id=d.org_id WHERE d.id=OLD.decision_id) THEN
   RAISE EXCEPTION 'Mapping targets are immutable' USING ERRCODE='23514';
  END IF;
  RETURN OLD;
 END IF;
 RETURN NEW;
END $guard$;
CREATE OR REPLACE FUNCTION {schema}.am_control_decision_complete_v1() RETURNS trigger LANGUAGE plpgsql AS $complete$
DECLARE target_count integer; proposal_id uuid;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM {schema}.finding_control_decisions WHERE id=NEW.id) THEN RETURN NULL; END IF;
 SELECT count(*) INTO target_count FROM {schema}.finding_control_targets WHERE decision_id=NEW.id;
 IF (NEW.state IN ('proposed','approved') AND (target_count<1 OR target_count>20)) OR (NEW.state='withdrawn' AND target_count<>0) THEN
  RAISE EXCEPTION 'Mapping decision requires a complete bounded control set' USING ERRCODE='23514';
 END IF;
 IF NEW.state='approved' THEN
  SELECT id INTO proposal_id FROM {schema}.finding_control_decisions
   WHERE rule_id=NEW.rule_id AND org_id=NEW.org_id AND catalog_id=NEW.catalog_id AND version=NEW.proposal_version AND state='proposed';
  IF NOT FOUND THEN RAISE EXCEPTION 'Approval requires the exact retained proposal' USING ERRCODE='23514'; END IF;
  IF EXISTS(
   (SELECT control_id FROM {schema}.finding_control_targets WHERE decision_id=NEW.id EXCEPT SELECT control_id FROM {schema}.finding_control_targets WHERE decision_id=proposal_id)
   UNION ALL
   (SELECT control_id FROM {schema}.finding_control_targets WHERE decision_id=proposal_id EXCEPT SELECT control_id FROM {schema}.finding_control_targets WHERE decision_id=NEW.id)) THEN
   RAISE EXCEPTION 'Approval control set differs from its reviewed proposal' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NULL;
END $complete$;
""")
    for table in TABLES:
        connection.exec_driver_sql(f"CREATE OR REPLACE TRIGGER am_control_catalog_guard BEFORE INSERT OR UPDATE OR DELETE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION {schema}.am_control_catalog_guard_v1()")
    connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS am_control_decision_complete ON {schema}.finding_control_decisions")
    connection.exec_driver_sql(f"CREATE CONSTRAINT TRIGGER am_control_decision_complete AFTER INSERT ON {schema}.finding_control_decisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {schema}.am_control_decision_complete_v1()")


def uninstall_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    for table in TABLES:
        connection.exec_driver_sql(f"DROP TRIGGER am_control_catalog_guard ON {schema}.{table}")
    connection.exec_driver_sql(f"DROP TRIGGER am_control_decision_complete ON {schema}.finding_control_decisions")
    connection.exec_driver_sql(f"DROP FUNCTION {schema}.am_control_decision_complete_v1()")
    connection.exec_driver_sql(f"DROP FUNCTION {schema}.am_control_catalog_guard_v1()")


def register(metadata):
    @event.listens_for(metadata, "after_create")
    def install(target, connection, **kwargs):
        if "finding_control_targets" in {table.name for table in kwargs.get("tables", [])}:
            install_v1(connection)
