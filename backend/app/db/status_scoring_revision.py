"""Frozen v3 list invalidation: workflow/proof decisions use their own lane."""
from sqlalchemy import event

FIELDS = ('workflow_status','workflow_version','workflow_updated_at','assignee_id',
    'due_date','due_timezone','due_expires_at','risk_review_date','risk_review_timezone','risk_review_expires_at',
    'risk_verification_state','risk_verification_version','risk_verified_workflow_version','risk_verified_at',
    'risk_verification_expires_at','risk_verified_observation_count','risk_verification_source_kind',
    'risk_verification_document_id','risk_verification_source_hash')


def install_v3(connection):
    schema=connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql('SELECT current_schema()').scalar_one())
    excluded='ARRAY['+','.join("'"+field+"'" for field in FIELDS)+']'
    before='ROW('+','.join('o.'+field for field in FIELDS)+')'
    after='ROW('+','.join('n.'+field for field in FIELDS)+')'
    connection.exec_driver_sql(f"""CREATE OR REPLACE FUNCTION {schema}.am_list_finding_update_v3() RETURNS trigger
    LANGUAGE plpgsql AS $body$ BEGIN
        INSERT INTO {schema}.organization_list_revisions AS dst (org_id,finding_revision)
        SELECT DISTINCT org_id,1 FROM (
            SELECT n.org_id FROM list_new n FULL JOIN list_old o ON n.id=o.id
            WHERE (to_jsonb(n)-{excluded}) IS DISTINCT FROM (to_jsonb(o)-{excluded})
            UNION SELECT o.org_id FROM list_new n FULL JOIN list_old o ON n.id=o.id
            WHERE n.org_id IS DISTINCT FROM o.org_id
        ) changed WHERE org_id IS NOT NULL ORDER BY org_id
        ON CONFLICT(org_id) DO UPDATE SET finding_revision=dst.finding_revision+1;
        INSERT INTO {schema}.organization_workflow_revisions AS dst (org_id,revision)
        SELECT DISTINCT n.org_id,1 FROM list_new n JOIN list_old o ON n.id=o.id
        WHERE {after} IS DISTINCT FROM {before} ORDER BY n.org_id
        ON CONFLICT(org_id) DO UPDATE SET revision=dst.revision+1;
        RETURN NULL;
    END $body$;
    CREATE OR REPLACE TRIGGER am_list_update AFTER UPDATE ON {schema}.findings
        REFERENCING OLD TABLE AS list_old NEW TABLE AS list_new
        FOR EACH STATEMENT EXECUTE FUNCTION {schema}.am_list_finding_update_v3();""")


def uninstall_v3(connection):
    from app.db.workflow_revision import install_v2
    install_v2(connection)
    schema=connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql('SELECT current_schema()').scalar_one())
    connection.exec_driver_sql(f'DROP FUNCTION IF EXISTS {schema}.am_list_finding_update_v3()')


def register(metadata):
    @event.listens_for(metadata,'after_create')
    def create_triggers(target,connection,**kwargs):
        if 'finding_verifications' in {table.name for table in kwargs.get('tables',[])}:
            install_v3(connection)
