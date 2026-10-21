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
