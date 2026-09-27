# AuditMind AI — Delivery Plan

Tracks progress against the roadmap in `Blueprint.md` / `Architecture.md` (section 9).

## How this works

- Each phase below must have **all its tests green** before work starts on the next phase.
- "Green" means: unit tests pass, and integration tests pass (or are correctly
  skipped with a documented, agreed-upon reason — never silently broken).
- At the end of a phase, I report status here + a test run, **you verify, and
  give explicit go-ahead** before the next phase starts. No self-approval.
- Environment constraints discovered along the way (e.g. no Docker, no pgvector
  build toolchain) are recorded here with the workaround chosen, so decisions
  aren't relitigated.

## Environment notes

- **No Docker** on this machine — all local dev runs directly (venv + native
  PostgreSQL 18, installed at `S:\Program Files\PostgreSQL\18`).
- **pgvector 0.8.6** installed on PostgreSQL 18 (2026-09-27, ahead of Phase 3)
  and enabled in both databases (`backend/scripts/create_databases.sql`).
  Migration `0002_documents_pgvector.py` is applied.
- Backend tools (alembic, pytest, uvicorn) live in `backend\.venv` — activate
  it first (`.\.venv\Scripts\Activate.ps1`). `psql` is not on PATH
  (`S:\Program Files\PostgreSQL\18\bin`).
- Two local databases: `auditmind` (dev), `auditmind_test` (integration tests
  only, created/dropped tables per test run — never shares state with dev).

## Phase 1 — Foundations (Week 1 of the roadmap)

**Scope:** repo structure, data model, auth, basic Claude wiring.

- [x] Backend scaffold: FastAPI app, SQLAlchemy models for all 8 core entities
      (organizations, users, assets, scans, findings, risk_scores, reports,
      documents), Alembic migrations
- [x] Frontend scaffold: Next.js (App Router) + TypeScript + Tailwind, brand
      palette wired in, placeholder pages for Dashboard/Assets/Findings/Reports/Settings
- [x] Auth: register/login (JWT + bcrypt), role-based access dependency
- [x] Org selection (backend): `org_memberships` table (migration `0003`) —
      users can belong to several orgs with a role per org. `GET /orgs` lists
      the caller's orgs + role (the picker), `POST /orgs` creates one (caller
      becomes admin), `POST /orgs/{org_id}/members` lets an admin add an
      existing user. Every `/orgs/{org_id}/...` route checks membership.
- [ ] Org picker + login UI: moved to Phase 2 — the frontend has no API
      client or auth wiring yet, and that lands with the dashboard wiring
- [x] Rule-based v1 risk scoring engine (`RISL_SCORING.md` formula)
- [x] Claude smoke-test endpoint (`POST /ai/claude/test`)
- [x] CI workflow (GitHub Actions: backend pytest, frontend build+lint)
- [x] Unit tests: scoring engine (tier boundaries, deductions, weighted
      average), security (password hashing, JWT roundtrip/expiry) — **12
      passing**
- [x] Integration tests written and passing against real Postgres (auth
      register/login/duplicate-rejection, risk-score-from-seeded-findings)
- [x] Databases created (`auditmind`, `auditmind_test`), migrations
      `0001`–`0003` applied (all 9 tables, incl. `documents` with pgvector)
- [x] Integration tests for org selection (picker listing, org creation,
      cross-org denial, adding members, admin-only rules)
- [x] Full suite green: **21 passed, 0 failed, 0 skipped**
- [x] CI fixed before first run: backend job now installs `requirements-dev.txt`
      (pytest wasn't in `requirements.txt`) and runs a `pgvector/pgvector:pg18`
      service, so integration tests run in CI instead of skipping
- [x] Frontend `npm run lint` + `npm run build` pass locally
- [x] First commit, on `main` (2026-09-27)
- [x] Pushed to GitHub (private repo `shalisarakkal/AuditMind`); first CI run
      green — backend **21 passed, 0 skipped**, frontend lint + build pass
- [x] Your review + explicit approval to close out Phase 1 (2026-09-27)

**Status:** Closed 2026-09-27. All tests green locally and in CI (CI #1 on
`95440e1`: 21 backend tests passed, 0 skipped; frontend lint + build pass).

**Bugs the test suite caught and fixed during this phase** (kept here as a
record, not because they need more action):
- `passlib` + `bcrypt>=4.1` incompatibility broke all password hashing
  (pinned `bcrypt==4.0.1`)
- Enum columns (`severity`, `domain`, `role`, `tier`, `status`) were declared
  as plain `String` at the SQLAlchemy Core level, so values read back from
  the DB were raw strings, not enum members — `.value` access crashed the
  risk-scoring endpoint. Fixed with a proper `Enum(..., native_enum=False)`
  column type (`app/db/types.py:str_enum`) so DB round-trips give back real
  enum instances, matching what the `Mapped[...]` type hints already claimed.
- Alembic's default `env.py` runs all pending revisions in one transaction —
  when migration `0002` (pgvector) failed, it silently rolled back `0001`
  too. Fixed with `transaction_per_migration=True`.

## Phase 2 — Ingestion & basic risk (Week 2 of the roadmap)

**Scope:** CSV/JSON asset import, manual findings upload, dashboard wired to
real data instead of placeholder scores, login page + org picker in the
frontend (carried over from Phase 1).

- [ ] Not started — Phase 1 approved, ready to begin

## Phase 3 — AI audit & reporting (Week 3 of the roadmap)

**Scope:** load
CIS/NIST/ISO docs (pgvector is already set up), Claude-driven risk scoring with RAG citations, full report
generation endpoint.

- [ ] Not started

## Phase 4 — Polish & resilience focus (Week 4 of the roadmap)

**Scope:** per-domain scoring refinement, remediation generation, PDF/HTML
export, security hardening (rate limiting, audit logging, secrets handling).

- [ ] Not started

## Test policy

- **Unit tests** (`backend/tests/unit/`): pure logic, no DB, always run.
- **Integration tests** (`backend/tests/integration/`): hit a real Postgres
  via `TEST_DATABASE_URL`; auto-skip with a clear reason if unreachable so CI
  and local runs never silently pass or hang.
- **Frontend**: `npm run build` + `npm run lint` gate every phase; component/
  interaction tests get added once real API wiring replaces the placeholder
  dashboard data (Phase 2).
- New backend logic ships with a unit test in the same change. New endpoints
  that touch the DB ship with an integration test in the same change.
