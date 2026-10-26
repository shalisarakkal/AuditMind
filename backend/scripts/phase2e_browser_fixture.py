"""Isolated Phase 2e browser fixture; refuses application databases/schemas."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Settings, settings
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'api', 'worker', 'expire-idle', 'expire-session', 'expire-temp',
                                        'active-report', 'active-index', 'finish-jobs', 'cleanup'])
    parser.add_argument('--schema', required=True)
    parser.add_argument('--email')
    args = parser.parse_args()
    if not re.fullmatch(r'phase2e_browser_[a-f0-9]{12}', args.schema):
        raise SystemExit('Invalid isolated browser schema')
    url = make_url(settings.TEST_DATABASE_URL)
    if url.get_backend_name() != 'postgresql' or url.database != 'auditmind_test' or url.host not in ('localhost', '127.0.0.1'):
        raise SystemExit('Local auditmind_test only')
    url = url.update_query_dict({'options': f'-csearch_path={args.schema},public'})
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False), COOKIE_SECURE='false',
        PUBLIC_SIGNUP='false', ANTHROPIC_API_KEY='', OPENAI_API_KEY='', VOYAGE_API_KEY='',
        OPENROUTER_API_KEY='', OPENROUTER_INFERENCE_ENABLED='false', REPORT_AI_PROVIDER='anthropic',
        ARCHIVE_AUTO_PURGE='false', CORS_ORIGINS='http://localhost:3000',
        UPLOAD_DIR=str(Path(__file__).resolve().parents[2] / 'temp' / args.schema),
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    refreshed = Settings()
    for name in Settings.model_fields:
        setattr(settings, name, getattr(refreshed, name))
    if args.action == 'api':
        import uvicorn
        uvicorn.run('app.main:app', host='127.0.0.1', port=8011)
        return
    if args.action == 'worker':
        import runpy
        runpy.run_module('app.worker', run_name='__main__')
        return
    import app.db.base
    from app.db.base_class import Base
    from app.models.user import User
    from app.models.organization import Organization
    from app.models.membership import OrgMembership
    from app.models.enums import UserRole
    from app.services import accounts, platform
    engine = create_engine(url)
    if args.action == 'prepare':
        with engine.begin() as conn:
            assert conn.scalar(text('SELECT current_database()')) == 'auditmind_test'
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public'))
            conn.execute(text(f'CREATE SCHEMA "{args.schema}"'))  # refuses reuse
        Base.metadata.create_all(engine.execution_options(schema_translate_map={None: args.schema}))
        password = secrets.token_urlsafe(24)
        with Session(engine) as db:
            root = User(email='root@phase2e.example', name='Browser Root', is_sysadmin=True)
            org = Organization(name='Browser Alpha')
            db.add_all([root, org]); db.flush()
            accounts.set_password(db, root, password)
            db.commit()
            print(json.dumps({'root_email': root.email, 'root_password': password, 'org_id': str(org.id)}))
    elif args.action == 'cleanup':
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{args.schema}" CASCADE'))
        print('Removed isolated synthetic browser schema only')
    else:
        from datetime import datetime, timedelta, timezone
        from app.models.session import UserSession
        if not args.email or not args.email.endswith('@phase2e.example'):
            raise SystemExit('Synthetic accounts only')
        with Session(engine) as db:
            user = db.scalar(select(User).where(User.email == args.email))
            assert user is not None
            if args.action in {'active-report', 'active-index', 'finish-jobs'}:
                from app.models.report import Report
                from app.models.enums import ReportStatus
                from app.models.knowledge import KnowledgeDocument, KnowledgeVersion, KnowledgeIndex, EmbeddingProfile
                member = db.scalar(select(OrgMembership).where(OrgMembership.user_id == user.id))
                assert member is not None
                if args.action == 'active-report':
                    db.add(Report(org_id=member.org_id, title='Synthetic archive blocker',
                                  status=ReportStatus.running, heartbeat_at=datetime.now(timezone.utc)))
                elif args.action == 'active-index':
                    profile = EmbeddingProfile(provider='local', model='synthetic', revision='fixture', dimensions=1024)
                    document = KnowledgeDocument(org_id=member.org_id, title='Synthetic archive blocker')
                    db.add_all([profile, document]); db.flush()
                    version = KnowledgeVersion(document_id=document.id, number=1, edition='fixture', source='synthetic',
                        content_kind='reference', rights='synthetic', content='Synthetic reference', content_hash='b'*64)
                    db.add(version); db.flush()
                    db.add(KnowledgeIndex(version_id=version.id, profile_id=profile.id, status='running',
                                          heartbeat_at=datetime.now(timezone.utc)))
                else:
                    for report in db.scalars(select(Report).where(Report.org_id == member.org_id)):
                        report.status = ReportStatus.failed
                    for index in db.scalars(select(KnowledgeIndex).join(KnowledgeVersion).join(KnowledgeDocument)
                                            .where(KnowledgeDocument.org_id == member.org_id)):
                        index.status = 'failed'
            elif args.action == 'expire-temp':
                user.temp_password_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            else:
                for session in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))):
                    if args.action == 'expire-idle':
                        session.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
                    else:
                        session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
    engine.dispose()


if __name__ == '__main__':
    main()
