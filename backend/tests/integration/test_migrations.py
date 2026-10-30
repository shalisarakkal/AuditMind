"""Exercise real Alembic upgrades and rollback without using create_all."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from tests.conftest import _drop_test_schema, requires_db

pytestmark = requires_db


def test_metadata_cleanup_removes_stale_migration_revision(db_session):
    engine = db_session.get_bind()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0009')"))
    _drop_test_schema(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()


def test_migrations_upgrade_rollback_and_preserve_legacy_reports():
    url = make_url(settings.TEST_DATABASE_URL)
    assert url.get_backend_name() == "postgresql" and url.database == "auditmind_test"
    engine = create_engine(url)
    schema = f"migration_test_{uuid4().hex}"
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    # Do not reconfigure the application's/test runner's log handlers.
    config.config_file_name = None
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == "auditmind_test"
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.commit()
            config.attributes.update(connection=connection, version_table_schema=schema)

            command.upgrade(config, "head")
            assert connection.scalar(text(f'SELECT version_num FROM "{schema}".alembic_version')) == head
            assert {"reports", "knowledge_versions", "knowledge_chunks", "report_evidence_uses"} <= set(
                inspect(connection).get_table_names(schema=schema)
            )
            assert {index["name"] for index in inspect(connection).get_indexes("findings", schema=schema)} >= {
                "ix_findings_description_trgm", "ix_findings_category_trgm", "ix_findings_source_trgm",
                "ix_findings_active_assignee", "ix_findings_active_due_search", "ix_findings_active_review_search",
            }
            for table, name, columns in (
                ("findings", "ix_findings_active_org_domain_severity", ["org_id", "domain", "severity"]),
                ("assets", "ix_assets_active_org_count", ["org_id"]),
            ):
                index = next(i for i in inspect(connection).get_indexes(table, schema=schema) if i["name"] == name)
                assert index["column_names"] == columns
                assert "archived_at IS NULL" in str(index["dialect_options"]["postgresql_where"])
            connection.commit()
            for table, columns in (("assets", ("type", "subtype", "environment", "criticality")),
                                   ("findings", ("source", "workflow_status", "assignee_id", "scan_id"))):
                indexes = {i["name"]: i for i in inspect(connection).get_indexes(table, schema=schema)}
                for column in columns:
                    index = indexes[f"ix_{table}_active_org_{column}"]
                    assert index["column_names"] == ["org_id", column]
                    assert "archived_at IS NULL" in str(index["dialect_options"]["postgresql_where"])
            connection.commit()
            command.downgrade(config, "0035")
            assert "ix_assets_active_org_subtype" not in {i["name"] for i in inspect(connection).get_indexes("assets", schema=schema)}
            connection.commit()
            command.upgrade(config, "head")
            connection.commit()
            search_index = next(i for i in inspect(connection).get_indexes("assets", schema=schema) if i["name"] == "ix_assets_active_search_trgm")
            assert search_index["dialect_options"]["postgresql_using"] == "gin"
            assert "archived_at IS NULL" in str(search_index["dialect_options"]["postgresql_where"])
            assert connection.execute(text("""SELECT p.provolatile,p.proparallel FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname=:schema AND p.proname='am_asset_search_v1'"""), {"schema": schema}).one() == ("i", "s")
            connection.commit()
            command.downgrade(config, "0036")
            assert "ix_assets_active_search_trgm" not in {i["name"] for i in inspect(connection).get_indexes("assets", schema=schema)}
            assert connection.scalar(text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema AND proname='am_asset_search_v1'"), {"schema": schema}) == 0
            connection.commit()
            command.upgrade(config, "head")
            connection.commit()
            connection.execute(text("INSERT INTO platform_settings (key,value) VALUES ('dashboard_snapshots',CAST(:value AS jsonb))"),
                               {"value": '{"enabled":true,"version":5}'})
            connection.commit()
            command.downgrade(config, "0032")
            assert connection.scalar(text("SELECT value FROM platform_settings WHERE key='dashboard_snapshots'")) == {"enabled": False, "version": 6}
            assert "ix_assets_active_org_count" not in {i["name"] for i in inspect(connection).get_indexes("assets", schema=schema)}
            assert "ix_findings_active_org_domain_severity" not in {i["name"] for i in inspect(connection).get_indexes("findings", schema=schema)}
            connection.commit()
            command.upgrade(config, "head")
            assert connection.scalar(text("""SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND NOT i.indisvalid"""),
                {"schema": schema}) == 0
            connection.commit()
            command.downgrade(config, "0018")
            assert "knowledge_versions" not in inspect(connection).get_table_names(schema=schema)

            org, report = uuid4(), uuid4()
            connection.execute(text("INSERT INTO organizations (id, name, created_at) VALUES (:id, 'Migration test', now())"), {"id": org})
            connection.execute(text("INSERT INTO reports (id, org_id, title, status) VALUES (:id, :org, 'Legacy report', 'generated')"),
                               {"id": report, "org": org})
            connection.commit()
            command.upgrade(config, "head")
            migrated = connection.execute(
                text("SELECT title, status, retry_count, created_at FROM reports WHERE id=:id"), {"id": report},
            ).one()
            assert migrated[:3] == ("Legacy report", "generated", 0)
            assert migrated.created_at is not None
            assert connection.scalar(text("SELECT show_name_in_header FROM organizations WHERE id=:id"), {"id": org}) is True
            assert connection.scalar(text("SELECT header_logo_size FROM organizations WHERE id=:id"), {"id": org}) == "medium"
            assert connection.scalar(text("SELECT header_name_size FROM organizations WHERE id=:id"), {"id": org}) == "medium"
            assert connection.execute(text("SELECT dashboard_refresh_interval_seconds,dashboard_refresh_settings_version FROM organizations WHERE id=:id"), {"id": org}).one() == (None, 0)
            connection.execute(text("UPDATE organizations SET dashboard_refresh_interval_seconds=120,dashboard_refresh_settings_version=1 WHERE id=:id"), {"id": org})
            connection.commit()
            command.downgrade(config, "0034")
            assert "dashboard_refresh_interval_seconds" not in {c["name"] for c in inspect(connection).get_columns("organizations", schema=schema)}
            connection.commit()
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT dashboard_refresh_interval_seconds FROM organizations WHERE id=:id"), {"id": org}) is None
            assert {"evidence_evaluations", "organization_evidence_revisions"} <= set(inspect(connection).get_table_names(schema=schema))
            connection.execute(text("INSERT INTO organization_scoring_settings (org_id,evidence_qualified_enabled,version) VALUES (:id,true,5)"), {"id": org})
            connection.execute(text("INSERT INTO assets (id,org_id,type,hostname,created_at) VALUES (:id,:org,'server','migration-evidence',now())"), {"id": uuid4(), "org": org})
            assert connection.scalar(text("SELECT revision FROM organization_evidence_revisions WHERE org_id=:id"), {"id": org}) >= 1
            connection.commit()
            command.downgrade(config, "0030")
            assert connection.execute(text("SELECT evidence_qualified_enabled,version FROM organization_scoring_settings WHERE org_id=:id"), {"id": org}).one() == (False, 6)
            assert "evidence_evaluations" not in inspect(connection).get_table_names(schema=schema)
            assert connection.scalar(text("SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND t.tgname LIKE 'am_evidence_%'"), {"schema": schema}) == 0
            connection.commit()
            command.upgrade(config, "head")
            connection.execute(text("DELETE FROM organization_scoring_settings WHERE org_id=:id"), {"id": org})
            connection.commit()
            qualification = uuid4()
            connection.execute(text("""INSERT INTO domain_evidence_qualifications
                (id,org_id,domain,policy_version,status,scope,rationale,updated_at)
                VALUES (:id,:org,'network_config','domain-evidence-v1','conflicting','all','migration test',NOW())"""),
                {"id": qualification, "org": org})
            connection.commit()
            command.downgrade(config, "0029")
            assert connection.execute(text("SELECT status,version FROM domain_evidence_qualifications WHERE id=:id"),
                {"id": qualification}).one() == ("draft", 2)
            connection.commit()
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT reviewed_at FROM domain_evidence_qualifications WHERE id=:id"), {"id": qualification}) is None
            assert {"organization_scoring_settings", "domain_evidence_qualifications"} <= set(inspect(connection).get_table_names(schema=schema))
            connection.execute(text("INSERT INTO organization_scoring_settings (org_id) VALUES (:id)"), {"id": org})
            assert connection.scalar(text("SELECT evidence_qualified_enabled FROM organization_scoring_settings WHERE org_id=:id"), {"id": org}) is False
            connection.commit()
            command.downgrade(config, "0028")
            assert "organization_scoring_settings" not in inspect(connection).get_table_names(schema=schema)
            assert connection.scalar(text("SELECT title FROM reports WHERE id=:id"), {"id": report}) == "Legacy report"
            connection.commit()
            command.upgrade(config, "head")
            assert {index["name"] for index in inspect(connection).get_indexes("reports", schema=schema)} >= {
                "ix_reports_org_created", "ix_reports_org_status",
            }
            connection.commit()
            command.upgrade(config, "head")  # Repeated deployment must be a no-op.
            assert connection.scalar(text(f'SELECT version_num FROM "{schema}".alembic_version')) == head
            connection.commit()
            # Autogenerate compares the default schema. Use this private
            # engine's isolated schema, not the test database's public tables.
            original_schema = connection.dialect.default_schema_name
            connection.dialect.default_schema_name = schema
            config.attributes.pop("version_table_schema")
            try:
                command.check(config)
            finally:
                connection.dialect.default_schema_name = original_schema
                config.attributes["version_table_schema"] = schema
    finally:
        # Only the random schema created above, inside the named test DB.
        with engine.begin() as cleanup:
            assert cleanup.scalar(text("SELECT current_database()")) == "auditmind_test"
            cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
