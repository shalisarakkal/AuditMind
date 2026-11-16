from pathlib import Path
from uuid import uuid4
import pytest
import runpy
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from app.core.config import settings
from tests.conftest import requires_db

pytestmark = requires_db


def test_catalog_migration_roundtrip_drift_and_retained_data_guard():
    engine = create_engine(settings.TEST_DATABASE_URL)
    schema = "catalog_migration_" + uuid4().hex
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.config_file_name = None
    try:
        with engine.connect() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
            c.execute(text(f'SET search_path TO "{schema}",public'))
            c.commit()
            config.attributes.update(connection=c, version_table_schema=schema)
            command.upgrade(config, "0060")
            org, finding = uuid4(), uuid4()
            c.execute(text("INSERT INTO organizations(id,name,created_at) VALUES(:id,'Existing tenant',now())"), {"id": org})
            c.execute(text("INSERT INTO findings(id,org_id,domain,severity,category,created_at) VALUES(:id,:org,'identity_access','high','Existing category',now())"), {"id": finding, "org": org})
            c.commit()
            command.upgrade(config, "0061")
            c.commit()
            assert c.scalar(text("SELECT count(*) FROM control_catalogs")) == 0
            assert c.scalar(text("SELECT category FROM findings WHERE id=:id"), {"id": finding}) == "Existing category"
            config.attributes.pop("version_table_schema")
            command.check(config)
            c.commit()
            config.attributes["version_table_schema"] = schema
            command.downgrade(config, "0060")
            c.commit()
            assert c.scalar(text("SELECT to_regclass(:table)"), {"table": schema + ".control_catalogs"}) is None
            c.commit()
            command.upgrade(config, "0061")
            c.commit()
            c.execute(text("""INSERT INTO control_catalogs(id,framework,edition,title,source,rights,content_hash,installed_by,installed_by_label,installed_at)
                VALUES(:id,'SYNTHETIC','test','Synthetic retained release','local:test','Synthetic fixture only',:hash,:actor,'Test reviewer',now())"""), {"id": uuid4(), "hash": "0" * 64, "actor": uuid4()})
            c.commit()
            with pytest.raises(RuntimeError, match="Export retained catalogs"):
                command.downgrade(config, "0060")
            c.rollback()
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0061"
            assert c.scalar(text("SELECT count(*) FROM control_catalogs")) == 1
    finally:
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_catalog_guard_and_readiness_support_quoted_schema_names():
    from app.db.control_catalog import install_v1
    from app.services.control_catalog import available
    engine = create_engine(settings.TEST_DATABASE_URL)
    schema = "catalog_quote_" + uuid4().hex + "'x"
    ddl = runpy.run_path(str(Path(__file__).resolve().parents[2] / "alembic/versions/0061_control_catalog.py"))["DDL"]
    try:
        with engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
            c.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
            c.execute(text("CREATE TABLE organizations(id uuid PRIMARY KEY)"))
            c.exec_driver_sql(ddl)
            install_v1(c)
            assert available(c)
            catalog, control = uuid4(), uuid4()
            c.execute(text("""INSERT INTO control_catalogs(id,framework,edition,title,source,rights,content_hash,installed_by,installed_by_label,installed_at)
                VALUES(:id,'SYNTHETIC','test','Quoted schema fixture','local:test','Synthetic fixture only',:hash,:actor,'Test reviewer',now())"""), {"id": catalog, "hash": "0" * 64, "actor": uuid4()})
            c.execute(text("INSERT INTO catalog_controls(catalog_id,control_id,reference,title,description) VALUES(:catalog,:control,'TEST-1','Synthetic outcome','Synthetic description')"), {"catalog": catalog, "control": control})
    finally:
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
