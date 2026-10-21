# AuditMind AI

AI-powered cyber resilience auditing platform. Claude reasons over asset/finding data plus CIS/NIST/ISO
standards (via pgvector RAG) to produce per-domain risk scores, remediation guidance, and audit reports.

See the planning docs in the repo root for full specs:
`Architecture.md`, `Blueprint.md`, `DATA_MODEL.md`, `CONNECTORS_SPEC.md`, `RISK_SCORING.md`,
`PROMPTS_CLAUDE.md`, `UI_FLOWS.md`, `MasterPrompt.md`.

## Stack

- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python 3.12)
- **Database**: PostgreSQL + pgvector (structured data + RAG embeddings, one datastore)
- **AI**: Claude (Anthropic API)
- **Deployment target**: AWS (Docker locally for now)

## Repo layout

```
backend/    FastAPI app, background worker (app/worker), SQLAlchemy models, Alembic migrations
frontend/   Next.js app
infra/      docker-compose for local dev
docs/       Database performance guide, UI conventions
```

## Local development

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

In `backend/.env`, set `SECRET_KEY` (required: the backend and worker refuse to start
without a random one of 32+ characters) and `ANTHROPIC_API_KEY`:

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
[Phase 3 operations](docs/PHASE3_OPERATIONS.md). Container validation requires a
Docker-capable staging host. `PLAN.md` tracks every
phase, decision and test run; `Blueprint.md` / `Architecture.md` section 9 hold the original roadmap.
