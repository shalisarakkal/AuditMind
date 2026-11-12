"""Recover an interrupted concurrent-index migration in a private schema."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from tests.conftest import requires_db

pytestmark = requires_db


def test_visibility_migration_recovers_after_concurrent_build_interruption():
    url = make_url(settings.TEST_DATABASE_URL)
    assert url.get_backend_name() == 'postgresql' and url.database == 'auditmind_test'
    engine = create_engine(url)
    schema = 'visibility_migration_' + uuid4().hex
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    config.config_file_name = None
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.commit()
            config.attributes.update(connection=connection, version_table_schema=schema)
            command.upgrade(config, '0052')
            connection.commit()
            builds = 0
            def interrupt(conn, cursor, statement, parameters, context, executemany):
                nonlocal builds
                if statement.startswith('CREATE INDEX CONCURRENTLY'):
                    builds += 1
                    if builds == 5:
                        raise RuntimeError('synthetic concurrent index interruption')
            event.listen(connection, 'before_cursor_execute', interrupt)
            try:
                with pytest.raises(RuntimeError, match='synthetic concurrent index interruption'):
                    command.upgrade(config, '0053')
            finally:
                event.remove(connection, 'before_cursor_execute', interrupt)
                connection.rollback()
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0052'
            connection.commit()
            command.upgrade(config, '0053')
            connection.commit()
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0053'
            assert connection.scalar(text("SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND NOT i.indisvalid"), {'schema':schema}) == 0
            indexes = inspect(connection).get_indexes('findings', schema=schema)
            assert not any(item['name'].endswith('_c53') for item in indexes)
            assert 'consolidation_alias_id IS NULL' in str(next(item for item in indexes if item['name']=='ix_findings_active_org_domain_severity')['dialect_options']['postgresql_where'])
            connection.commit()
            command.downgrade(config, '0052')
            connection.commit()
            assert 'consolidation_alias_id' not in {item['name'] for item in inspect(connection).get_columns('findings',schema=schema)}
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


from tests.integration.test_finding_consolidation_foundation import native
from tests.integration.test_consolidation_visibility import apply, undo_fixture


def test_downgrade_refuses_retained_history_even_after_undo(db_session, native):
    from uuid import UUID
    who, payload, result = apply(db_session, native)
    db_session.commit()
    undo_fixture(db_session, UUID(native['org']), who, result)
    db_session.commit()
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    config.config_file_name = None
    with db_session.get_bind().connect() as connection:
        config.attributes['connection'] = connection
        command.stamp(config, '0053')
        connection.commit()
        with pytest.raises(RuntimeError, match='Retained consolidation visibility/history'):
            command.downgrade(config, '0052')
        connection.rollback()
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0053'
        assert 'consolidation_history_id' in {item['name'] for item in inspect(connection).get_columns('findings')}

        connection.commit()
        # A retained revision must still block downgrade after physical source
        # cleanup removes the last marker. This uses a rolled-back test-only
        # mutation; production cleanup must not strip audit links to downgrade.
        connection.execute(text('UPDATE findings SET consolidation_history_id=NULL'))
        with pytest.raises(RuntimeError, match='Retained consolidation visibility/history'):
            command.downgrade(config, '0052')
        connection.rollback()
