from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from app.core.config import settings
from tests.conftest import requires_db

pytestmark = requires_db


def test_proof_migration_roundtrip_drift_and_retention_guard():
    engine = create_engine(settings.TEST_DATABASE_URL)
    schema = "proof_migration_" + uuid4().hex
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
            command.upgrade(config, "0061")
            org, finding = uuid4(), uuid4()
            c.execute(text("INSERT INTO organizations(id,name,created_at) VALUES(:id,'Proof migration fixture',now())"), {"id": org})
            c.execute(text("INSERT INTO findings(id,org_id,domain,severity,created_at) VALUES(:id,:org,'identity_access','high',now())"), {"id": finding, "org": org})
            c.commit()
            command.upgrade(config, "0062")
            c.commit()
            assert c.scalar(text("SELECT count(*) FROM remediation_proofs")) == 0
            assert c.scalar(text("SELECT workflow_version FROM findings WHERE id=:id"), {"id": finding}) == 0
            config.attributes.pop("version_table_schema")
            command.check(config)
            c.commit()
            config.attributes["version_table_schema"] = schema
            command.downgrade(config, "0061")
            c.commit()
            assert c.scalar(text("SELECT to_regclass(:name)"), {"name": schema + ".remediation_proofs"}) is None
            c.commit()
            command.upgrade(config, "0062")
            c.commit()
            c.execute(text("""INSERT INTO remediation_proofs(id,org_id,finding_id,version,workflow_version,state,source_reference,
                observed_at,submitter_id,submitter_label,actor_id,actor_label,note,created_at,context)
                VALUES(:id,:org,:finding,1,0,'pending','https://example.com/synthetic',now(),:actor,'Fixture',:actor,'Fixture','Synthetic proof',now(),'{}'::jsonb)"""),
                {"id": uuid4(), "org": org, "finding": finding, "actor": uuid4()})
            c.commit()
            with pytest.raises(RuntimeError, match="Export retained remediation proof"):
                command.downgrade(config, "0061")
            c.rollback()
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0062"
    finally:
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_guard_quotes_schema_and_rejects_an_existing_foreign_tenant():
    from datetime import datetime, timezone
    from sqlalchemy.exc import IntegrityError
    from app.models.remediation_proof import RemediationProof
    from app.services.remediation_proof import _ready
    engine = create_engine(settings.TEST_DATABASE_URL)
    schema = "proof_quote_" + uuid4().hex + "'x"
    quoted = engine.dialect.identifier_preparer.quote_schema(schema)
    try:
        with engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA {quoted}'))
            c.execute(text(f'SET LOCAL search_path TO {quoted},public'))
            c.execute(text("CREATE TABLE organizations(id uuid PRIMARY KEY)"))
            c.execute(text("CREATE TABLE findings(id uuid PRIMARY KEY, org_id uuid REFERENCES organizations(id) ON DELETE CASCADE)"))
            RemediationProof.__table__.create(c)
            _ready(c)
            org, other, finding, actor = uuid4(), uuid4(), uuid4(), uuid4()
            c.execute(text("INSERT INTO organizations(id) VALUES(:first),(:second)"), {"first": org, "second": other})
            c.execute(text("INSERT INTO findings(id,org_id) VALUES(:id,:org)"), {"id": finding, "org": org})
            values = dict(org_id=org, finding_id=finding, version=1, workflow_version=0, state="pending",
                source_reference="https://example.com/synthetic-quoted-proof", observed_at=datetime.now(timezone.utc),
                submitter_id=actor, submitter_label="Synthetic submitter", actor_id=actor, actor_label="Synthetic actor",
                note="Synthetic quoted-schema proof", created_at=datetime.now(timezone.utc), context={})
            c.execute(RemediationProof.__table__.insert().values(**values))
            with pytest.raises(IntegrityError, match="same-organization"):
                with c.begin_nested():
                    c.execute(RemediationProof.__table__.insert().values(**{**values, "org_id": other, "version": 2}))
            assert c.scalar(text("SELECT count(*) FROM remediation_proofs")) == 1
            c.execute(text("DELETE FROM organizations WHERE id=:id"), {"id": org})
            assert c.scalar(text("SELECT count(*) FROM remediation_proofs")) == 0
    finally:
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS {quoted} CASCADE'))
        engine.dispose()
