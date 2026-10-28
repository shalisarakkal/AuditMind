"""Versioned PostgreSQL invalidation DDL, shared by migration and create_all.

Keep v1 stable: later schema changes must use a new installer/migration. Statement
transition tables invalidate bulk SQL/COPY/cascades without a counter per row.
All storage references use the trigger's schema, never a caller's search_path.
"""
from sqlalchemy import event, text

INPUT_TABLES = ("organizations", "assets", "findings", "events", "knowledge_documents",
                "knowledge_versions", "domain_evidence_qualifications")
LIFECYCLE_TYPES = ("import", "archive", "restore", "purge", "asset_added", "finding_added",
    "document_uploaded", "document_retired", "document_removed", "document_reactivation_queued",
    "org_archived", "org_restored")


def install_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    lifecycle = ",".join("''" + name + "''" for name in LIFECYCLE_TYPES)
    connection.execute(text(f"""
        CREATE OR REPLACE FUNCTION {schema}.am_evidence_revision_v1() RETURNS trigger
        LANGUAGE plpgsql AS $body$
        DECLARE changed text; projection text; predicate text := '';
        BEGIN
            IF TG_OP = 'TRUNCATE' THEN
                changed := format('SELECT id AS org_id FROM %I.organizations', TG_TABLE_SCHEMA);
            ELSE
                IF TG_TABLE_NAME = 'organizations' THEN projection := 'id AS org_id';
                ELSIF TG_TABLE_NAME = 'knowledge_versions' THEN projection := 'document_id';
                ELSE projection := 'org_id'; END IF;
                IF TG_TABLE_NAME = 'events' THEN
                    predicate := ' WHERE type IN ({lifecycle})';
                END IF;
                IF TG_OP = 'INSERT' THEN changed := 'SELECT ' || projection || ' FROM evidence_new' || predicate;
                ELSIF TG_OP = 'DELETE' THEN changed := 'SELECT ' || projection || ' FROM evidence_old' || predicate;
                ELSE changed := 'SELECT ' || projection || ' FROM evidence_new' || predicate ||
                    ' UNION SELECT ' || projection || ' FROM evidence_old' || predicate;
                END IF;
                IF TG_TABLE_NAME = 'organizations' AND TG_OP = 'UPDATE' THEN
                    changed := 'SELECT id AS org_id FROM (
                        (SELECT id,archived_at,purge_requested_at FROM evidence_new EXCEPT SELECT id,archived_at,purge_requested_at FROM evidence_old)
                        UNION (SELECT id,archived_at,purge_requested_at FROM evidence_old EXCEPT SELECT id,archived_at,purge_requested_at FROM evidence_new)) changed_orgs';
                ELSIF TG_TABLE_NAME = 'findings' AND TG_OP = 'UPDATE' THEN
                    changed := 'SELECT a.org_id FROM evidence_new n FULL JOIN evidence_old o ON n.id=o.id
                        CROSS JOIN LATERAL (VALUES(n.org_id),(o.org_id)) a(org_id)
                        WHERE n.id IS NULL OR o.id IS NULL OR
                        (n.org_id,n.asset_id,n.scan_id,n.domain,n.severity,n.category,n.description,n.source,n.raw_data,n.event_count,n.first_seen,n.last_seen,n.archived_at)
                        IS DISTINCT FROM
                        (o.org_id,o.asset_id,o.scan_id,o.domain,o.severity,o.category,o.description,o.source,o.raw_data,o.event_count,o.first_seen,o.last_seen,o.archived_at)';
                ELSIF TG_TABLE_NAME = 'assets' AND TG_OP = 'UPDATE' THEN
                    changed := 'SELECT a.org_id FROM evidence_new n FULL JOIN evidence_old o ON n.id=o.id
                        CROSS JOIN LATERAL (VALUES(n.org_id),(o.org_id)) a(org_id)
                        WHERE n.id IS NULL OR o.id IS NULL OR
                        (n.org_id,n.type,n.subtype,n.type_known,n.hostname,n.ip,n.cloud_id,n.environment,n.criticality,n.tags,n.details,n.archived_at)
                        IS DISTINCT FROM
                        (o.org_id,o.type,o.subtype,o.type_known,o.hostname,o.ip,o.cloud_id,o.environment,o.criticality,o.tags,o.details,o.archived_at)';
                END IF;
                IF TG_TABLE_NAME = 'knowledge_versions' THEN
                    changed := format('SELECT d.org_id FROM (%s) v JOIN %I.knowledge_documents d ON d.id=v.document_id', changed, TG_TABLE_SCHEMA);
                END IF;
            END IF;
            EXECUTE format('INSERT INTO %I.organization_evidence_revisions AS dst (org_id, revision)
                SELECT DISTINCT c.org_id, 1 FROM (%s) c JOIN %I.organizations o ON o.id=c.org_id
                ORDER BY c.org_id ON CONFLICT (org_id) DO UPDATE
                SET revision=dst.revision+1', TG_TABLE_SCHEMA, changed, TG_TABLE_SCHEMA);
            RETURN NULL;
        END $body$;
    """))
    for table in INPUT_TABLES:
        for operation, transition in (
            ("INSERT", "REFERENCING NEW TABLE AS evidence_new"),
            ("UPDATE", "REFERENCING OLD TABLE AS evidence_old NEW TABLE AS evidence_new"),
            ("DELETE", "REFERENCING OLD TABLE AS evidence_old"), ("TRUNCATE", ""),
        ):
            connection.exec_driver_sql(f"""CREATE OR REPLACE TRIGGER am_evidence_{operation.lower()}
                AFTER {operation} ON {schema}.{table} {transition}
                FOR EACH STATEMENT EXECUTE FUNCTION {schema}.am_evidence_revision_v1()""")


def uninstall_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    for table in INPUT_TABLES:
        for operation in ("insert", "update", "delete", "truncate"):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS am_evidence_{operation} ON {schema}.{table}")
    connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {schema}.am_evidence_revision_v1()")


def register(metadata):
    @event.listens_for(metadata, "after_create")
    def create_triggers(target, connection, **kwargs):
        # Only complete metadata fixtures use create_all; production uses Alembic.
        tables = {table.name for table in kwargs.get("tables", [])}
        if connection.dialect.name == "postgresql" and "evidence_evaluations" in tables:
            install_v1(connection)
