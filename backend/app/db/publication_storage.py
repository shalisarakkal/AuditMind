"""Tenant guards for reserved publication snapshots, not ordinary import rows."""
from sqlalchemy import event

SQL = """
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
"""


def register(metadata):
    @event.listens_for(metadata, 'after_create')
    def install(target, connection, **kwargs):
        if 'observation_publication_snapshots' in {table.name for table in kwargs.get('tables', [])}:
            connection.exec_driver_sql(SQL)

    @event.listens_for(metadata, 'after_drop')
    def uninstall(target, connection, **kwargs):
        connection.exec_driver_sql('DROP FUNCTION IF EXISTS am_publication_snapshot_owner_v1()')
