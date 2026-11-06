"""Separate workflow invalidation from long-running import transactions."""
from sqlalchemy import event


def install_v2(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.exec_driver_sql(f"""
    CREATE OR REPLACE FUNCTION {schema}.am_list_finding_update_v2() RETURNS trigger
    LANGUAGE plpgsql AS $body$
    BEGIN
        -- Source/lifecycle changes retain the original list revision lane.
        INSERT INTO {schema}.organization_list_revisions AS dst (org_id,finding_revision)
        SELECT DISTINCT org_id,1 FROM (
            SELECT n.org_id FROM list_new n FULL JOIN list_old o ON n.id=o.id
            WHERE (to_jsonb(n) - ARRAY['workflow_status','workflow_version','workflow_updated_at',
                'assignee_id','due_date','due_timezone','due_expires_at','risk_review_date',
                'risk_review_timezone','risk_review_expires_at']) IS DISTINCT FROM
                (to_jsonb(o) - ARRAY['workflow_status','workflow_version','workflow_updated_at',
                'assignee_id','due_date','due_timezone','due_expires_at','risk_review_date',
                'risk_review_timezone','risk_review_expires_at'])
            UNION SELECT o.org_id FROM list_new n FULL JOIN list_old o ON n.id=o.id
            WHERE n.org_id IS DISTINCT FROM o.org_id
        ) changed WHERE org_id IS NOT NULL ORDER BY org_id
        ON CONFLICT(org_id) DO UPDATE SET finding_revision=dst.finding_revision+1;
        -- Separate rows avoid waiting for an import's uncommitted revision.
        INSERT INTO {schema}.organization_workflow_revisions AS dst (org_id,revision)
        SELECT DISTINCT n.org_id,1 FROM list_new n JOIN list_old o ON n.id=o.id
        WHERE (n.workflow_status,n.workflow_version,n.workflow_updated_at,n.assignee_id,
            n.due_date,n.due_timezone,n.due_expires_at,n.risk_review_date,
            n.risk_review_timezone,n.risk_review_expires_at) IS DISTINCT FROM
            (o.workflow_status,o.workflow_version,o.workflow_updated_at,o.assignee_id,
            o.due_date,o.due_timezone,o.due_expires_at,o.risk_review_date,
            o.risk_review_timezone,o.risk_review_expires_at)
        ORDER BY n.org_id
        ON CONFLICT(org_id) DO UPDATE SET revision=dst.revision+1;
        RETURN NULL;
    END $body$;
    CREATE OR REPLACE TRIGGER am_list_update AFTER UPDATE ON {schema}.findings
        REFERENCING OLD TABLE AS list_old NEW TABLE AS list_new
        FOR EACH STATEMENT EXECUTE FUNCTION {schema}.am_list_finding_update_v2();
    """)


def uninstall_v2(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.exec_driver_sql(f"""CREATE OR REPLACE TRIGGER am_list_update AFTER UPDATE ON {schema}.findings
        REFERENCING OLD TABLE AS list_old NEW TABLE AS list_new
        FOR EACH STATEMENT EXECUTE FUNCTION {schema}.am_list_revision_v1()""")
    connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {schema}.am_list_finding_update_v2()")


def register(metadata):
    @event.listens_for(metadata, "after_create")
    def create_triggers(target, connection, **kwargs):
        if "organization_workflow_revisions" in {table.name for table in kwargs.get("tables", [])}:
            install_v2(connection)
