"""Frozen v1 invalidation contract for list counts and seek cursors."""
from sqlalchemy import event, text

TABLES = ("organizations", "assets", "findings", "users", "org_memberships")


def install_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.execute(text(f"""CREATE OR REPLACE FUNCTION {schema}.am_list_revision_v1() RETURNS trigger
        LANGUAGE plpgsql AS $body$
        DECLARE changed text; projection text; asset_step integer := 0;
        BEGIN
            IF TG_TABLE_NAME IN ('organizations','assets') THEN asset_step := 1; END IF;
            IF TG_OP = 'TRUNCATE' THEN
                changed := format('SELECT id AS org_id FROM %I.organizations', TG_TABLE_SCHEMA);
            ELSE
                IF TG_TABLE_NAME IN ('organizations','users') THEN projection := 'id';
                ELSE projection := 'org_id'; END IF;
                IF TG_OP = 'INSERT' THEN changed := 'SELECT ' || projection || ' FROM list_new';
                ELSIF TG_OP = 'DELETE' THEN changed := 'SELECT ' || projection || ' FROM list_old';
                ELSE changed := 'SELECT ' || projection || ' FROM list_new UNION SELECT ' || projection || ' FROM list_old'; END IF;
                IF TG_TABLE_NAME = 'users' AND TG_OP = 'UPDATE' THEN
                    changed := 'SELECT n.id FROM list_new n JOIN list_old o ON o.id=n.id
                        WHERE (n.name,n.email,n.is_active) IS DISTINCT FROM (o.name,o.email,o.is_active)';
                END IF;
                IF TG_TABLE_NAME = 'users' THEN
                    changed := format('SELECT m.org_id FROM (%s) u JOIN %I.org_memberships m ON m.user_id=u.id', changed, TG_TABLE_SCHEMA);
                ELSIF TG_TABLE_NAME = 'organizations' THEN
                    changed := 'SELECT id AS org_id FROM (' || changed || ') o';
                END IF;
            END IF;
            EXECUTE format('INSERT INTO %I.organization_list_revisions AS dst (org_id,asset_revision,finding_revision)
                SELECT DISTINCT c.org_id, %s, 1 FROM (%s) c JOIN %I.organizations o ON o.id=c.org_id
                ORDER BY c.org_id ON CONFLICT (org_id) DO UPDATE SET
                asset_revision=dst.asset_revision+%s, finding_revision=dst.finding_revision+1',
                TG_TABLE_SCHEMA, asset_step, changed, TG_TABLE_SCHEMA, asset_step);
            RETURN NULL;
        END $body$"""))
    for table in TABLES:
        for operation, transition in (
            ("INSERT", "REFERENCING NEW TABLE AS list_new"),
            ("UPDATE", "REFERENCING OLD TABLE AS list_old NEW TABLE AS list_new"),
            ("DELETE", "REFERENCING OLD TABLE AS list_old"), ("TRUNCATE", ""),
        ):
            connection.exec_driver_sql(f"""CREATE OR REPLACE TRIGGER am_list_{operation.lower()}
                AFTER {operation} ON {schema}.{table} {transition}
                FOR EACH STATEMENT EXECUTE FUNCTION {schema}.am_list_revision_v1()""")
    connection.exec_driver_sql(f"""INSERT INTO {schema}.organization_list_revisions(org_id)
        SELECT id FROM {schema}.organizations ON CONFLICT DO NOTHING""")


def uninstall_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    for table in TABLES:
        for operation in ("insert", "update", "delete", "truncate"):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS am_list_{operation} ON {schema}.{table}")
    connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {schema}.am_list_revision_v1()")


def register(metadata):
    @event.listens_for(metadata, "after_create")
    def create_triggers(target, connection, **kwargs):
        if "organization_list_revisions" in {table.name for table in kwargs.get("tables", [])}:
            install_v1(connection)
