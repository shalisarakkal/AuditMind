"""Isolated local browser demo. Never migrates existing application tables."""

import argparse
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings, settings

DEMO_SCHEMA = "auditmind_demo"
DEMO_EMAIL = "demo.admin@example.com"
PLATFORM_EMAIL = "demo.platform@example.com"
DEMO_ORG = "AuditMind Demo - Synthetic Data"


def demo_url(base_url: str):
    url = make_url(base_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The demo requires local PostgreSQL; remote and non-PostgreSQL targets are refused")
    if not url.database or url.database.endswith("_test"):
        raise ValueError("Do not host browser demos in a disposable test database")
    # A dedicated schema requires no CREATEDB privilege and is invisible to
    # ordinary application queries, which retain their existing search_path.
    return url.update_query_dict({"options": "-csearch_path=auditmind_demo,public"})


def configure_demo():
    url = demo_url(settings.DATABASE_URL)
    os.environ.update(
        DATABASE_URL=url.render_as_string(hide_password=False),
        COOKIE_SECURE="false", PUBLIC_SIGNUP="false",
        RULE_BASED_TEST_REPORTS_ENABLED="true", ARCHIVE_AUTO_PURGE="false",
        ANTHROPIC_API_KEY="", OPENAI_API_KEY="", VOYAGE_API_KEY="",
        OPENROUTER_API_KEY="", OPENROUTER_INFERENCE_ENABLED="false",
        REPORT_EVIDENCE_V3_ENABLED="false", REPORT_EVIDENCE_QUALIFICATIONS_FILE="",
        CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000",
        UPLOAD_DIR=str(Path(__file__).resolve().parents[2] / "temp" / "auditmind-demo" / "uploads"),
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
    )
    # config was imported to derive the local connection. Refresh that same
    # singleton before importing anything that constructs the application engine.
    refreshed = Settings()
    for name in Settings.model_fields:
        setattr(settings, name, getattr(refreshed, name))
    return url


def seed_demo(db: Session) -> dict[str, str]:
    import app.db.base  # noqa: F401: register all mapped models
    from app.core.security import hash_password
    from app.models.asset import Asset
    from app.models.enums import Domain, Severity, UserRole
    from app.models.finding import Finding
    from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
    from app.models.membership import OrgMembership
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.knowledge_service import digest
    from app.services.report_service import create_rule_based_test_report

    if db.scalar(select(User.id).where(User.email == DEMO_EMAIL)):
        # Never overwrite passwords or re-create content the user has edited.
        return {}
    if db.scalar(select(User.id).limit(1)) or db.scalar(select(Organization.id).limit(1)):
        raise ValueError("Refusing to seed a populated database without the expected demo account")
    passwords = {DEMO_EMAIL: secrets.token_urlsafe(24), PLATFORM_EMAIL: secrets.token_urlsafe(24)}
    admin = User(email=DEMO_EMAIL, name="Demo organization admin", hashed_password=hash_password(passwords[DEMO_EMAIL]))
    platform = User(email=PLATFORM_EMAIL, name="Demo platform admin", is_sysadmin=True,
                    hashed_password=hash_password(passwords[PLATFORM_EMAIL]))
    org = Organization(name=DEMO_ORG, industry="Synthetic training data", size="small")
    db.add_all([admin, platform, org])
    db.flush()
    db.add(OrgMembership(user_id=admin.id, org_id=org.id, role=UserRole.admin))
    assets = [Asset(org_id=org.id, type=kind, hostname=host, ip=f"192.0.2.{i + 10}",
                    environment="demo", criticality="high", tags=["synthetic", "demo"])
              for i, (kind, host) in enumerate([
                  ("server", "demo-web-01"), ("server", "demo-backup-01"),
                  ("workstation", "demo-laptop-01"), ("network_device", "demo-firewall-01")])]
    db.add_all(assets)
    db.flush()
    descriptions = ["MFA missing on a synthetic admin account", "Overly broad synthetic firewall rule",
                    "Synthetic server requires a security patch", "Demo restore exercise overdue",
                    "Synthetic log source not monitored", "Demo incident response exercise overdue",
                    "Synthetic policy review overdue"]
    for i, domain in enumerate(Domain):
        db.add(Finding(org_id=org.id, asset_id=assets[i % len(assets)].id, domain=domain,
                       severity=list(Severity)[i % len(Severity)], source="synthetic-demo",
                       category="Training example", description=descriptions[i]))
    policy = "Synthetic demo policy: require MFA for administrators, patch critical systems, and test backup recovery quarterly. Not an official compliance standard."
    document = KnowledgeDocument(org_id=org.id, title="Synthetic demo security policy")
    db.add(document)
    db.flush()
    db.add(KnowledgeVersion(document_id=document.id, number=1, edition="Demo v1", source="Local synthetic example",
                            content_kind="full_text", rights="Project-created synthetic training text",
                            content=policy, content_hash=digest(policy)))
    db.flush()
    # This service commits the entire seed atomically. No AI call or embedding
    # index is queued; local semantic indexing needs a separately prepared cache.
    create_rule_based_test_report(db, org.id, "DEMO - Rule-based preview (not AI)", admin.id)
    return passwords


def prepare(url):
    from alembic import command
    from alembic.config import Config

    maintenance = create_engine(url.difference_update_query(["options"]))
    try:
        with maintenance.begin() as connection:
            connection.execute(text('CREATE SCHEMA IF NOT EXISTS "auditmind_demo"'))
    finally:
        maintenance.dispose()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_schema()")) != DEMO_SCHEMA:
                raise ValueError("Refusing to prepare anything outside the auditmind_demo schema")
            if "users" in inspect(connection).get_table_names(schema=DEMO_SCHEMA):
                count = connection.scalar(text("SELECT count(*) FROM users"))
                expected = connection.scalar(text("SELECT count(*) FROM users WHERE email = :email"), {"email": DEMO_EMAIL})
                if count and not expected:
                    raise ValueError("Refusing to migrate an existing non-demo schema")
            connection.commit()
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.commit()
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
            config.config_file_name = None
            config.attributes["connection"] = connection
            # On the first run public.alembic_version is still visible through
            # the pgvector search path. Never borrow the application's revision.
            config.attributes["version_table_schema"] = DEMO_SCHEMA
            command.upgrade(config, "head")
            config.attributes.pop("version_table_schema")
            command.check(config)
        with Session(engine) as db:
            passwords = seed_demo(db)
        print("Isolated auditmind_demo schema ready at migration head. Existing application/test tables unchanged.")
        if passwords:
            for email, password in passwords.items():
                print(f"Sign-in: {email}    Password (shown once): {password}")
        else:
            print("Existing demo retained; use your existing demo password. No account passwords were reset.")
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "seed-evidence-examples", "api", "worker"])
    args = parser.parse_args()
    url = configure_demo()
    if args.action == "prepare":
        prepare(url)
    elif args.action == "seed-evidence-examples":
        from scripts.evidence_examples import seed_examples
        engine = create_engine(url)
        try:
            with Session(engine) as db:
                count = seed_examples(db)
            print(f"Created {count} synthetic example reports. No inference or consent changes.")
        finally:
            engine.dispose()
    elif args.action == "api":
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
    else:
        import runpy
        runpy.run_module("app.worker", run_name="__main__")


if __name__ == "__main__":
    main()
