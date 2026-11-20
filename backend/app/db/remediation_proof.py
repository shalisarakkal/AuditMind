"""Frozen v1 tenant ownership and append-only proof guards."""
from sqlalchemy import event


def install_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.exec_driver_sql(f"""
CREATE OR REPLACE FUNCTION {schema}.am_remediation_proof_guard_v1() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NOT EXISTS (SELECT 1 FROM {schema}.findings WHERE id=NEW.finding_id AND org_id=NEW.org_id) THEN
   RAISE EXCEPTION 'Remediation proof requires same-organization finding' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 ELSIF TG_OP='DELETE' AND (NOT EXISTS(SELECT 1 FROM {schema}.findings WHERE id=OLD.finding_id)
   OR NOT EXISTS(SELECT 1 FROM {schema}.organizations WHERE id=OLD.org_id)) THEN
  RETURN OLD;
 END IF;
 RAISE EXCEPTION 'Remediation proof history is immutable; purge its owner through the lifecycle' USING ERRCODE='23514';
END $guard$;
CREATE TRIGGER am_remediation_proof_guard BEFORE INSERT OR UPDATE OR DELETE ON {schema}.remediation_proofs
 FOR EACH ROW EXECUTE FUNCTION {schema}.am_remediation_proof_guard_v1();
""")


def uninstall_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS am_remediation_proof_guard ON {schema}.remediation_proofs")
    connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {schema}.am_remediation_proof_guard_v1()")


def register(metadata):
    event.listen(metadata.tables["remediation_proofs"], "after_create", lambda table, connection, **kw: install_v1(connection))
    event.listen(metadata.tables["remediation_proofs"], "before_drop", lambda table, connection, **kw: uninstall_v1(connection))
