# AuditMind AI

Local operations features: [Phase 4 local operations](docs/PHASE4_LOCAL_OPERATIONS.md).
Current [dependency remediation](docs/BACKEND_DEPENDENCY_REMEDIATION.md) supersedes
the initial backend audit blocker. Phase 4 remains partial.

Phase 4 progress and remaining work: [code-backed status and next milestone](docs/PHASE4_STATUS.md).

Latest local-testing UI: consistent date-picker contrast, inclusive browser-local
workflow deadlines and safe row/bulk actions across Findings, Archived, Assets
and Uploads. See [Chrome verification steps](docs/PHASE4_USER_VERIFICATION.md)
and [current validation evidence](docs/PHASE4_VALIDATION.md). This does not enable
production deployment or live inference.

Evidence-aware AI assessment is available **opt-in/off by default**: explicit
unscored evidence states, reviewed coverage qualification and server aggregation.
See [profiles/operator workflow](docs/EVIDENCE_COVERAGE_PROFILES.md) and
[verification](docs/EVIDENCE_ASSESSMENT_VALIDATION.md). Legacy reports and the
deterministic baseline remain unchanged; no real inference is enabled.

Phase 3 technical/open/deferred status: [closure checklist](docs/PHASE3_CLOSURE.md).
Report prompt v3 adds explicit input budgets and requires approval of its updated
processing target; existing reports are unchanged. Live inference remains disabled
in the demo and is not authorized by the automated test results.

Regression verification: [testing strategy and coverage](docs/TESTING.md).
Acceptance tests require PostgreSQL/pgvector/pg_trgm (`--require-postgres`); frontend
coverage runs with `npm run test:coverage`. Real inference remains mocked.
Migration 0024 provides indexed Findings substring search; see
[measurements and concurrent-migration requirements](docs/FINDING_SEARCH_PERFORMANCE.md).

Cyber resilience auditing platform with deterministic dashboard scoring and
separate Claude/RAG reports over installed, authorized documents. Selecting a
framework does not install licensed full-text CIS/ISO standards.

**Phase 3 preview, not release-approved:** see the current
[code review and release gates](docs/RELEASE_READINESS.md).

See the planning docs in the repo root for full specs:
`Architecture.md`, `Blueprint.md`, `DATA_MODEL.md`, `CONNECTORS_SPEC.md`, `RISK_SCORING.md`,
`PROMPTS_CLAUDE.md`, `UI_FLOWS.md`, `MasterPrompt.md`.

## Stack

- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python 3.12)
- **Database**: PostgreSQL + pgvector (structured data + RAG embeddings, one datastore)
- **AI**: Claude (Anthropic API; optional OpenRouter adapter disabled by default)
- **Deployment target**: AWS (Docker locally for now)

## Repo layout

```
backend/    FastAPI app, background worker (app/worker), SQLAlchemy models, Alembic migrations
frontend/   Next.js app
infra/      docker-compose for local dev
docs/       Database performance guide, UI conventions
```

## Local development

For an isolated browser tour with synthetic data and no external AI calls, see the
[user manual](docs/USER_MANUAL.md) and run `start-demo.ps1`. This preserves the
regular application's tables and uses its own local PostgreSQL schema.

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

In `backend/.env`, set `SECRET_KEY` (required: the backend and worker refuse to start
without a random one of 32+ characters). `ANTHROPIC_API_KEY` is needed only for
approved live Anthropic inference, not the no-inference browser demo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Three processes run side by side: the backend (API), the background worker (large
uploads, archive/restore/purge jobs, daily clean-up) and the frontend. On Windows,
once the steps below are done, `start-dev.ps1` opens all three in their own windows:

```powershell
powershell -ExecutionPolicy Bypass -File start-dev.ps1
```

- Frontend: http://localhost:3000 (open the app here)
- Backend: http://127.0.0.1:8000 (docs at `/docs`). The app reaches it through the
  frontend's own `/api`, so the sign-in session cookie works; for local development
  over http, `backend/.env` has `COOKIE_SECURE=false`

In production, put a reverse proxy (e.g. nginx) in front that sends `/api` to the
backend itself with the visitor's address (`X-Forwarded-For`, and uvicorn's
`--forwarded-allow-ips`), and everything else to the frontend; serve over HTTPS with
`COOKIE_SECURE=true`. Through the frontend's own forwarding every request looks as if
it came from one address, which the per-address sign-in limit would count together.

### The first accounts

Sign-up is closed unless `PUBLIC_SIGNUP=true`. Create the Sysadmin on the server, never
through the website (it gets a temporary password, shown once, to change at the first
sign-in):

```powershell
cd backend
.venv\Scripts\python scripts\create_sysadmin.py --email you@example.com --name "Platform admin"
```

The Sysadmin creates organizations with their first admin (Platform > Organizations),
and each org's admins add its people (People). The Sysadmin reads every org but changes
none of their data.

Docker Compose (`infra/docker-compose.yml`) hasn't been kept up to date since Phase 1
and doesn't start the worker; this project is developed without Docker (see
`PLAN.md`, Environment notes).

### Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload       # the API
python -m app.worker                # the background worker, in a second window
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Status

Phases 1-2 complete, Phase 2d complete: multi-organization accounts and roles; asset and findings uploads
(CSV, JSON, Nessus, and tool exports through import profiles) with per-row reports; large uploads processed
by the background worker with progress, recovery and Retry; archive, restore and purge with retention;
an Activity log; paged, searchable lists; rule-based risk scores on the Dashboard. Security fixes verified:
SECRET_KEY rejected at startup, archived scans return 404, and asset discovery returns 501.
Phase 3 report generation is worker-backed and requires external-processing consent.
Phase 2e: sign-in sessions checked on every request, lockout, the Simple/Complex
password rule and Change password; People (admins add people with a temporary password, change roles,
reset passwords, unlock); the Sysadmin's Platform section (organizations created, archived and purged;
accounts; platform activity; security defaults) and each org's Settings > Security.

Phase 3 documents, evidence-backed reports, observability and operational controls
are implemented; final acceptance/sign-off remains pending. Operational contracts,
migration `0021`, quotas, idempotency, retention and embedding deployment instructions:
[Phase 3 operations](docs/PHASE3_OPERATIONS.md). Docker deployment and container
validation are user-deferred to [Future phase](PLAN.md#future-phase--deferred-delivery),
not core Phase 3 blockers. Reporting-period browser fields are also deferred. `PLAN.md` tracks every
phase, decision and test run; `Blueprint.md` / `Architecture.md` section 9 hold the original roadmap.
