"""Opt-in Chrome fixture: isolated local test schema, mocked inference only."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Settings, settings
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'api', 'worker', 'inspect', 'cleanup'])
    parser.add_argument('--schema', required=True)
    parser.add_argument('--workflow', action='store_true', help='Enable isolated Phase 4 acceptance organization switching')
    args = parser.parse_args()
    if not re.fullmatch(r'phase3_browser_[a-f0-9]{12}', args.schema):
        raise SystemExit('Invalid isolated fixture schema')
    url = make_url(settings.TEST_DATABASE_URL)
    if url.get_backend_name() != 'postgresql' or url.database != 'auditmind_test' or url.host not in ('localhost', '127.0.0.1'):
        raise SystemExit('Local auditmind_test only')
    url = url.update_query_dict({'options': f'-csearch_path={args.schema},public'})
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),
        SECRET_KEY='phase3-browser-only-' + args.schema, PUBLIC_SIGNUP='false', COOKIE_SECURE='false',
        ANTHROPIC_API_KEY='', OPENAI_API_KEY='', VOYAGE_API_KEY='', OPENROUTER_API_KEY='',
        OPENROUTER_INFERENCE_ENABLED='false', REPORT_AI_PROVIDER='anthropic',
        CLAUDE_MODEL='claude-browser-fixture', ARCHIVE_AUTO_PURGE='false', WORKER_POLL_SECONDS='0.2',
        CORS_ORIGINS='http://localhost:3000,http://localhost:3014' if args.workflow else 'http://localhost:3000', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        UPLOAD_DIR=str(Path(__file__).resolve().parents[2] / 'temp' / args.schema))
    refreshed = Settings()
    for name in Settings.model_fields:
        setattr(settings, name, getattr(refreshed, name))
    import app.db.base
    from app.db.base_class import Base
    from app.models.enums import Domain, UserRole
    from app.models.user import User
    from app.models.organization import Organization
    from app.models.membership import OrgMembership
    from app.services import accounts, knowledge_embeddings, claude_service
    # No model downloads or external HTTP are possible through these boundaries.
    import httpx
    def forbidden(*a, **kw):
        raise RuntimeError('External HTTP forbidden in isolated browser fixture')
    httpx.HTTPTransport.handle_request = forbidden
    knowledge_embeddings.embed = lambda profile, texts, **kw: [[1.0] + [0.0] * (profile.dimensions - 1) for _ in texts]
    attempts = {}
    def complete(**kwargs):
        prompt = kwargs['messages'][0]['content']
        citations, _ = json.JSONDecoder().raw_decode(prompt.split(
            'RELEVANT COMPLIANCE CONTROLS & BENCHMARKS (RAG Context):', 1)[1].lstrip())
        citation_ids = [c['citation_id'] for c in citations]
        attempts[prompt] = attempts.get(prompt, 0) + 1
        if 'Fixture cancel' in prompt:
            time.sleep(5)
            from anthropic import APITimeoutError
            raise APITimeoutError(request=httpx.Request('POST', 'https://mock.invalid'))
        if 'Fixture retry' in prompt and attempts[prompt] == 1:
            from anthropic import RateLimitError
            raise RateLimitError('Synthetic 429', response=httpx.Response(429, request=httpx.Request('POST', 'https://mock.invalid')), body=None)
        payload = {} if 'Fixture invalid' in prompt else {
            'title': 'Synthetic browser assessment', 'executive_summary': 'Mock inference; synthetic evidence only.',
            'resilience_summary': 'Not an independently verified audit.', 'overall_score': 60, 'overall_tier': 'medium',
            'domains': [{'domain': d.value, 'score': 60, 'tier': 'medium', 'justification': 'Synthetic evidence.', 'citation_ids': citation_ids} for d in Domain],
            'remediations': [{'title': 'Review policy', 'description': 'Verify synthetic policy independently.',
                'priority': 'Medium', 'domain': Domain.identity_access.value, 'estimated_effort': 'Moderate',
                'expected_impact': 'Improve evidence quality', 'confidence': .5,
                'affected_finding_ids': [], 'affected_asset_ids': [], 'citation_ids': citation_ids}]}
        if payload and settings.REPORT_EVIDENCE_V3_ENABLED:
            payload.pop('overall_score')
            payload.pop('overall_tier')
            for domain in payload['domains']:
                domain.update(score=None, tier=None, evidence_status='insufficient',
                    evidence_reason='Synthetic policy alone does not establish operational coverage.',
                    evidence_finding_ids=[], strengths=[], weaknesses=[])
        return SimpleNamespace(content=[SimpleNamespace(type='text', text=json.dumps(payload))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=200))
    claude_service.get_client = lambda: SimpleNamespace(messages=SimpleNamespace(create=complete))
    # Configuration is enabled only after all real HTTP and provider calls above
    # have been replaced. No actual credential is read or made available.
    settings.ANTHROPIC_API_KEY = 'isolated-mock-only'
    if args.action == 'api':
        import uvicorn
        uvicorn.run('app.main:app', host='127.0.0.1', port=8012)
        return
    if args.action == 'worker':
        import runpy
        runpy.run_module('app.worker', run_name='__main__')
        return
    engine = create_engine(url, hide_parameters=True)
    created_schema = False
    try:
        if args.action == 'prepare':
            with engine.begin() as connection:
                assert connection.scalar(text('select current_database()')) == 'auditmind_test'
                connection.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public'))
                connection.execute(text(f'CREATE SCHEMA "{args.schema}"'))
            created_schema = True
            Base.metadata.create_all(engine.execution_options(schema_translate_map={None: args.schema}))
            password = secrets.token_urlsafe(24)
            with Session(engine) as db:
                alpha, beta = Organization(name='Phase3 Alpha'), Organization(name='Phase3 Beta')
                db.add_all([alpha, beta]); db.flush()
                for role in ('admin', 'auditor', 'viewer', 'other'):
                    user = User(email=f'{role}@phase3.example', name=f'Fixture {role}')
                    db.add(user); db.flush(); accounts.set_password(db, user, password)
                    db.add(OrgMembership(user_id=user.id, org_id=beta.id if role == 'other' else alpha.id,
                        role=UserRole.admin if role == 'other' else UserRole(role)))
                    if args.workflow and role == 'admin':
                        db.add(OrgMembership(user_id=user.id, org_id=beta.id, role=UserRole.admin))
                db.commit()
                print(json.dumps({'password': password, 'org': str(alpha.id), 'other_org': str(beta.id)}))
        elif args.action == 'inspect':
            from app.models.report import Report
            from app.models.ai_usage import AIUsage
            with Session(engine) as db:
                print(json.dumps({'reports': [{'title': r.title, 'status': r.status.value} for r in db.scalars(select(Report))],
                    'usage_count': len(db.scalars(select(AIUsage)).all())}))
        else:
            with engine.begin() as connection:
                assert connection.scalar(text('select current_database()')) == 'auditmind_test'
                connection.execute(text(f'DROP SCHEMA "{args.schema}" CASCADE'))
            print('Removed isolated synthetic Phase 3 schema only')
    except Exception:
        if args.action == 'prepare' and created_schema:
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{args.schema}" CASCADE'))
        raise
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
