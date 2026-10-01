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

- Backend: http://127.0.0.1:8000 (docs at `/docs`)
- Frontend: http://127.0.0.1:3000

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

Phases 1-2 are done: multi-organization accounts and roles; asset and findings uploads
(CSV, JSON, Nessus, and tool exports through import profiles) with per-row reports;
large uploads processed by the background worker with progress, recovery and Retry;
archive, restore and purge with retention; an Activity log; paged, searchable lists;
rule-based risk scores on the Dashboard.

Next: users and organization administration (Phase 2e), activity and audit log
sources (Phase 2f), then the AI audit and reports (Phase 3). `PLAN.md` tracks every
phase, decision and test run; `Blueprint.md` / `Architecture.md` section 9 hold the
original roadmap.
