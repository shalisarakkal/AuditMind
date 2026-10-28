"""Temporary viewer accounts for opt-in, local synthetic SA01 HTTP checks.

Prepare prints credentials ONLY to its parent process; never log that output.
Cleanup removes only the two exact run-owned accounts, not organization content.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "inspect", "cleanup"])
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{24}", args.run_id):
        raise SystemExit("Invalid test run identity")
    from scripts.demo import configure_demo, DEMO_EMAIL
    url = configure_demo()
    from app.db.base import Base  # noqa: F401
    from app.models.user import User
    from app.models.organization import Organization
    from app.models.membership import OrgMembership
    from app.models.enums import UserRole
    from app.core.security import hash_password
    from sqlalchemy import create_engine, select, text, delete, inspect
    from sqlalchemy.orm import Session

    emails = [f"evidence-http-{args.run_id}-{n}@example.com" for n in (1, 2)]
    name = f"Synthetic evidence HTTP {args.run_id}"
    engine = create_engine(url, hide_parameters=True)
    try:
        with Session(engine) as db:
            if db.scalar(text("SELECT current_schema()")) != "auditmind_demo" or not db.scalar(select(User.id).where(User.email == DEMO_EMAIL)):
                raise SystemExit("Expected local synthetic demo only")
            org = db.scalar(select(Organization).where(Organization.name == "SA01", Organization.archived_at.is_(None)))
            if org is None:
                raise SystemExit("Active synthetic SA01 organization required")
            if args.action == "prepare":
                if db.scalar(select(User.id).where(User.email.in_(emails))):
                    raise SystemExit("Run-owned accounts already exist; refusing to replace them")
                credentials = []
                for email in emails:
                    password = secrets.token_urlsafe(36) + "Aa1!"
                    user = User(email=email, name=name, hashed_password=hash_password(password))
                    db.add(user); db.flush()
                    db.add(OrgMembership(user_id=user.id, org_id=org.id, role=UserRole.viewer))
                    credentials.append({"email": email, "password": password})
                db.commit()
                print(json.dumps({"org_id": str(org.id), "credentials": credentials}))
            elif args.action == "cleanup":
                removed = db.execute(delete(User).where(User.email.in_(emails), User.name == name, User.is_sysadmin.is_(False))).rowcount
                db.commit()
                print(json.dumps({"removed_test_accounts": removed}))
            else:
                counts = {table: db.scalar(text(f"SELECT count(*) FROM {table} WHERE org_id=:org AND archived_at IS NULL"), {"org": org.id}) for table in ("assets", "findings")}
                counts["ai_usage"] = db.scalar(text("SELECT count(*) FROM ai_usage WHERE org_id=:org"), {"org": org.id})
                job_tables = ["scans", "reports", "archive_jobs", "knowledge_indexes"]
                if inspect(engine).has_table("evidence_evaluations"):
                    job_tables.append("evidence_evaluations")
                counts["active_jobs"] = sum(db.scalar(text(f"SELECT count(*) FROM {table} WHERE status IN ('pending','running')")) for table in job_tables)
                counts["active_inventory_connections"] = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND xact_start IS NOT NULL AND (query LIKE 'FETCH FORWARD%' OR query LIKE '%WITH inventory_hashes AS MATERIALIZED%')"))
                counts["temp_bytes_database_wide"] = db.scalar(text("SELECT temp_bytes FROM pg_stat_database WHERE datname=current_database()"))
                print(json.dumps(counts))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
