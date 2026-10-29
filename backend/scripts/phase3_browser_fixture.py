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
    parser.add_argument('action', choices=['prepare', 'api', 'worker', 'inspect', 'expire-pool-jobs', 'cleanup'])
    parser.add_argument('--schema', required=True)
    parser.add_argument('--workflow', action='store_true', help='Enable isolated Phase 4 acceptance organization switching')
    parser.add_argument('--evidence', action='store_true', help='Seed two reviewers and synthetic inventory for evidence acceptance')
    parser.add_argument('--pool', action='store_true', help='Guarded two-slot worker lifecycle acceptance only')
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
    if args.pool:
        os.environ.update(WORKER_CONCURRENCY='2', IMPORT_SYNC_MAX_BYTES='1')
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
    import httpx2
    def forbidden(*a, **kw):
        raise RuntimeError('External HTTP forbidden in isolated browser fixture')
    for transport_module in (httpx, httpx2):
        transport_module.HTTPTransport.handle_request = forbidden
        transport_module.AsyncHTTPTransport.handle_async_request = forbidden
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
        if args.pool:
            import threading
            from app.services import ingestion_service
            original = ingestion_service._Publisher.__init__
            lock = threading.Lock()
            arrivals = []
            run_id = secrets.token_hex(8)
            folder = settings.upload_dir
            folder.mkdir(parents=True, exist_ok=True)
            def observe(self, db, org_id, *a, **kw):
                with lock:
                    pause = len(arrivals) < 2
                    if pause:
                        arrivals.append(str(org_id))
                        (folder / 'pool-probe.json').write_text(json.dumps({'run': run_id, 'orgs': arrivals}))
                if pause:
                    until = time.monotonic() + 30
                    while not (folder / 'pool-release.flag').exists():
                        if time.monotonic() >= until:
                            raise RuntimeError('Isolated pool test did not release its publishers')
                        time.sleep(0.05)
                original(self, db, org_id, *a, **kw)
            ingestion_service._Publisher.__init__ = observe
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
                for role in ('admin', 'auditor', 'viewer', 'other') + (('reviewer',) if args.evidence else ()):
                    user = User(email=f'{role}@phase3.example', name=f'Fixture {role}')
                    db.add(user); db.flush(); accounts.set_password(db, user, password)
                    db.add(OrgMembership(user_id=user.id, org_id=beta.id if role == 'other' else alpha.id,
                        role=UserRole.admin if role in ('other', 'reviewer') else UserRole(role)))
                    if args.workflow and role == 'admin':
                        db.add(OrgMembership(user_id=user.id, org_id=beta.id, role=UserRole.admin))
                finding_ids = []
                if args.evidence:
                    from app.models.enums import Severity
                    from app.models.finding import Finding
                    assert db.scalar(text('SELECT current_schema()')) == args.schema
                    # Compactly generated, isolated synthetic data only. Enough
                    # rows for a real streamed read/concurrent-write overlap.
                    db.execute(text("""
                        INSERT INTO assets (id, org_id, type, hostname, details, created_at)
                        SELECT md5(:prefix || n::text)::uuid, :org, 'server',
                               'evidence-host-' || n::text,
                               jsonb_build_object('synthetic', repeat(md5(n::text), 32)), now()
                        FROM generate_series(1, 100000) AS n
                    """), {'prefix': args.schema, 'org': alpha.id})
                    for number in (1, 2):
                        finding = Finding(org_id=alpha.id, domain=Domain.network_config,
                            severity=Severity.high, source='manual',
                            description=f'Synthetic evidence observation {number}')
                        db.add(finding); db.flush(); finding_ids.append(str(finding.id))
                db.commit()
                if args.workflow:
                    platform_user = User(email='platform@phase3.example', name='Fixture platform', is_sysadmin=True)
                    db.add(platform_user); db.flush(); accounts.set_password(db, platform_user, password)
                    db.commit()
                print(json.dumps({'password': password, 'org': str(alpha.id), 'other_org': str(beta.id),
                    **({'finding_ids': finding_ids} if args.evidence else {})}))
        elif args.action == 'inspect':
            from app.models.report import Report
            from app.models.ai_usage import AIUsage
            from app.models.scan import Scan
            with Session(engine) as db:
                print(json.dumps({'reports': [{'title': r.title, 'status': r.status.value} for r in db.scalars(select(Report))],
                    'usage_count': len(db.scalars(select(AIUsage)).all()),
                    **({'pool_scans': [{'filename': s.filename, 'retry_count': s.retry_count, 'status': s.status.value}
                        for s in db.scalars(select(Scan))]} if args.pool else {})}))
        elif args.action == 'expire-pool-jobs':
            if not args.pool:
                raise RuntimeError('Only allowed in the isolated pool lifecycle fixture')
            from datetime import datetime, timedelta, timezone
            from sqlalchemy import update
            from app.models.scan import Scan
            with engine.begin() as conn:
                conn.execute(update(Scan).where(Scan.status == 'running').values(
                    heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=settings.WORKER_STALE_SECONDS + 60)))
            print('Expired only synthetic running import heartbeats for recovery verification')
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
