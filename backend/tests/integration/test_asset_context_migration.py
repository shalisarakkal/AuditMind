"""Real isolated migration/drift/rollback checks for managed asset context."""
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine,text
from app.core.config import settings
from tests.conftest import requires_db
pytestmark=requires_db

def test_migration_up_down_and_drift_preserves_existing_asset_defaults():
    engine=create_engine(settings.TEST_DATABASE_URL);schema='context_migration_'+uuid4().hex
    backend=Path(__file__).resolve().parents[2]
    config=Config(str(backend/'alembic.ini'));config.set_main_option('script_location',str(backend/'alembic'));config.config_file_name=None
    try:
        with engine.connect() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'));c.execute(text(f'SET search_path TO "{schema}",public'));c.commit()
            config.attributes.update(connection=c,version_table_schema=schema)
            command.upgrade(config,'0058')
            org=uuid4();asset=uuid4()
            c.execute(text("INSERT INTO organizations(id,name,created_at) VALUES(:id,'Existing tenant',now())"),{'id':org})
            c.execute(text("INSERT INTO assets(id,org_id,type,hostname,environment,criticality,created_at) VALUES(:id,:org,'server','legacy.example','imported-prod','source-high',now())"),{'id':asset,'org':org});c.commit()
            command.upgrade(config,'0060');c.commit()
            assert c.scalar(text("SELECT to_regclass('ix_asset_context_history_actor')")) is not None
            command.downgrade(config,'0059');c.commit()
            assert c.scalar(text("SELECT to_regclass('ix_asset_context_history_actor')")) is None;c.commit()
            command.upgrade(config,'0060');c.commit()
            assert c.scalar(text('SELECT count(*) FROM asset_contexts'))==0
            assert c.execute(text('SELECT environment,criticality FROM assets WHERE id=:id'),{'id':asset}).one()==('imported-prod','source-high')
            # Keep the asset-specific round-trip pinned, but compare models at
            # the current head so later additive migrations are represented.
            command.upgrade(config,'head');c.commit()
            config.attributes.pop("version_table_schema")
            command.check(config);c.commit()
            config.attributes["version_table_schema"]=schema
            command.downgrade(config,'0058');c.commit()
            assert c.scalar(text("SELECT to_regclass(:t)"),{'t':schema+'.asset_contexts'}) is None;c.commit()
            command.upgrade(config,'0060');c.commit()
            c.execute(text("INSERT INTO asset_contexts(asset_id,org_id,version,environment,updated_at) VALUES(:a,:o,1,'Reviewed',now())"),{'a':asset,'o':org});c.commit()
            with pytest.raises(RuntimeError,match='Export retained asset context'):
                command.downgrade(config,'0058')
            # Alembic commits each revision: the index-only downgrade can
            # finish before 0059 refuses to discard retained business data.
            c.rollback();assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0059'
            assert c.scalar(text('SELECT count(*) FROM asset_contexts'))==1;c.commit()
            command.upgrade(config,'0060');c.commit()
            assert c.scalar(text("SELECT to_regclass('ix_asset_context_history_actor')")) is not None
    finally:
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_context_guard_installer_quotes_schema_literals():
    from app.db.asset_context import install_v1
    engine=create_engine(settings.TEST_DATABASE_URL);schema="context_quote_"+uuid4().hex+"'x"
    try:
        with engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'));c.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
            for ddl in (
                'CREATE TABLE organizations(id uuid PRIMARY KEY)',
                'CREATE TABLE users(id uuid PRIMARY KEY,name text,email text,is_active boolean)',
                'CREATE TABLE org_memberships(user_id uuid,org_id uuid)',
                'CREATE TABLE assets(id uuid PRIMARY KEY,org_id uuid)',
                'CREATE TABLE asset_contexts(asset_id uuid PRIMARY KEY,org_id uuid,owner_id uuid,owner_label text,environment text,business_criticality text,version integer)',
                'CREATE TABLE asset_context_history(asset_id uuid,org_id uuid)',
                'CREATE TABLE organization_asset_context_revisions(org_id uuid PRIMARY KEY,revision bigint)',
            ):c.execute(text(ddl))
            install_v1(c)
            org=uuid4();asset=uuid4()
            c.execute(text('INSERT INTO organizations VALUES(:id)'),{'id':org})
            c.execute(text('INSERT INTO assets VALUES(:a,:o)'),{'a':asset,'o':org})
            c.execute(text("INSERT INTO asset_contexts(asset_id,org_id,version,environment) VALUES(:a,:o,1,'Production')"),{'a':asset,'o':org})
            assert c.scalar(text('SELECT revision FROM organization_asset_context_revisions'))==1
    finally:
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
