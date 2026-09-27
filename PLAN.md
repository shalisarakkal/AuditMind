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

Split into **2a (backend)** and **2b (frontend)**. There is a single check-in:
Phase 2 is marked complete only after both 2a and 2b are done and tested.
Built with the feature-dev workflow (explore → clarify → design → implement →
review).

### Phase 2a — Backend

Design: approach C ("pragmatic balance"): one ingestion service shared by the
sync and background paths, a defusedxml Nessus parser, and per-org settings.

- [x] Asset import `POST /orgs/{id}/assets/import` (CSV/JSON): per-row report
      with line numbers; existing assets matched by hostname (case-insensitive),
      else IP (only against unnamed assets); update/skip/duplicate strategy
- [x] Findings upload `POST /orgs/{id}/findings/import`: generic CSV/JSON +
      native `.nessus`; hosts matched/created as assets; duplicates (same asset
      + source + category) skipped; Nessus Info skipped or recorded as low;
      plugin family -> domain map; each upload recorded as a scan
- [x] Files <= 10 MB processed in the request (201 + report); larger ones
      (up to 100 MB, else 413) in the background (202; poll
      `GET /orgs/{id}/scans/{scan_id}`); migration `0004`
- [x] Per-org ingestion settings `GET/PATCH /orgs/{id}/settings` overriding
      the `.env` defaults (only overrides stored; null resets)
- [x] Dashboard `GET /orgs/{id}/dashboard`, computed live
- [x] Role enforcement: viewers read-only; discover + settings + members
      admin-only
- [x] Login accepts JSON and the OAuth2 form, so Swagger "Authorize" works
- [x] Tests: 192 backend tests passing (unit: parsing, Nessus incl. XXE and
      billion-laughs files, settings resolution; integration: imports, dedup,
      background path incl. a real 11 MB file, size limits, dashboard,
      settings API, full role matrix, form login). Live smoke test against
      uvicorn passed (incl. real background import)
- Known follow-up (pre-existing, not Phase 2): `alembic check` reports model
  vs. migration drift on enum column types and the `users.email` index

### Phase 2b — Frontend

- [x] API client (`src/lib/apiClient.ts`): bearer token from localStorage;
      an expired session (401 with a token) logs out and goes to /login
- [x] Login/register pages + logout; route groups `(auth)` / `(app)`, with
      a client-side guard (the JWT lives in localStorage, so no `proxy.ts`)
- [x] Sidebar org picker: remembered choice, validated against the fresh org
      list, "+ New organization"; pages remount on switch
- [x] Dashboard (live scores, top issues, recent imports), Assets table +
      Import, Findings grouped by domain + Upload (CSV/JSON/.nessus); large
      uploads poll the scan; per-row report panel; Import/Upload hidden for
      viewers
- [x] Settings → Ingestion: per-org overrides (admins edit/reset; others
      read-only), incl. the org's own Nessus family → domain mappings
- [x] Tests: Vitest + Testing Library, 45 tests (API client, auth/org
      context, guard, org picker, import button incl. background polling,
      report panel, settings panel, login/register, pages incl. viewer role);
      `npm test` added to CI
- [x] Browser E2E run against the real backend (register, import, Nessus
      upload, settings override/reset, dashboard, viewer view). Found and
      fixed: pre-hydration form submit could put credentials in the URL;
      sidebar logout off-screen on long pages; misaligned findings tables
- Out of scope, later phases: radar chart, per-asset risk score, AI
  explanation, remediation status, connector status

### Phase 2 code review (feature-dev: 3 reviewers — simplicity, bugs/security, conventions)

- [x] High: import uploads were fully received before auth ran (FastAPI parses
      the body before dependencies) — `UploadSizeLimitMiddleware` now rejects
      oversized uploads (declared or streamed) before auth; tests prove a 401
      used to come only after the whole body was read
- [x] Medium: two concurrent imports into one org could create the same host
      twice — imports into an org are serialised with a Postgres advisory
      lock (not a unique index, since the "duplicate" strategy allows repeats);
      a threaded test reproduced the race before the fix
- [x] Low: DATA_MODEL.md documents the new columns and import semantics;
      form-login test uses the shared fixture; new Nessus mapping rows start
      on the org's default domain

### Phase 2 sign-off

- [ ] Full suite green locally and in CI
- [ ] Your review + explicit approval to close out Phase 2

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
