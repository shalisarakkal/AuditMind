# AuditMind AI

AI-powered cyber resilience auditing platform. Claude reasons over asset/finding data plus CIS/NIST/ISO
standards (via pgvector RAG) to produce per-domain risk scores, remediation guidance, and audit reports.

See the planning docs in the repo root for full specs:
`Architecture.md`, `Blueprint.md`, `DATA_MODEL.md`, `CONNECTORS_SPEC.md`, `RISL_SCORING.md`,
`PROMPTS_CLAUDE.md`, `UI_FLOWS.md`, `MasterPrompt.md`.

## Stack

- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python 3.12)
- **Database**: PostgreSQL + pgvector (structured data + RAG embeddings, one datastore)
- **AI**: Claude (Anthropic API)
- **Deployment target**: AWS (Docker locally for now)

## Repo layout

```
backend/    FastAPI app, SQLAlchemy models, Alembic migrations
frontend/   Next.js app
infra/      docker-compose for local dev
```

## Local development

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
# fill in ANTHROPIC_API_KEY in backend/.env

docker compose -f infra/docker-compose.yml up --build
```

- Backend: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:3000

### Backend without Docker

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend without Docker

```bash
cd frontend
npm install
npm run dev
```

## Status

Week 1 foundation: repo structure, data model, auth stub, and a Claude test endpoint.
See `Blueprint.md` / `Architecture.md` section 9 for the full 4-week roadmap.
