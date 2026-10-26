# Backend validation — 2026-10-20

## Phase 4 backend follow-up — 2026-10-23

26 October dependency blocker **resolved**: approved transitive-only updates to
`undici@8.12.3` / `zod@4.6.7`; only the lockfile changed, not package.json or
application source. Full/production npm audits both **zero**. Fresh **367 frontend
tests** (51.92s), lint, TypeScript/isolated production build, **35 workflow Chrome
checks** (`phase3_browser_f712c790a5e4`) and **6 grouped Documents checks** passed.
Separate browser scopes, not 41 equivalent checks. No new risk accepted.
[Audit resolution](DEPENDENCY_AUDIT_2026-10-26.md).

26 October check-in preparation: [explicit scope/groups and exclusions](CHECKIN_PREPARATION.md).
The **1,203 full backend tests** below remain 25 October evidence, not rerun for
this dependency-only change. User-authorized commits: backend **86a1c2e**, frontend
**c995e5e**; the acceptance/docs commit contains this record and the
[Chrome walkthrough](PHASE4_USER_VERIFICATION.md). No push. Local-testing
check-in only, not production/live-AI release acceptance.


Step 3 search performance (25 October): migration **0024** adds six trigram and
three supporting indexes, built concurrently. Selective search uses deduplicated
indexed branches; broad labels/short terms use a scan fallback. Literal matching,
counts, tenant boundaries and exact UUID lookup are preserved. Queue-metric
polling now closes its own session, fixing an idle-transaction leak that delayed
index creation. Demo schema migrated/restarted; normal application schema untouched.

SA01 end-to-end HTTP `ssss`: 12.472–16.241s before, 2.299s first post-restart and
0.031s repeated after. Live Chrome including debounce/render: 1.127s. `Open`
(2,309,326 matches): 1.230–1.327s. Two-character `ss` remains 7.496–7.601s; short/
broad queries are not universally fast. Details and migration retry/rollback:
[search performance](FINDING_SEARCH_PERFORMANCE.md).

Frontend 367 tests/lint and normal production build passed; 35 Chrome checks
passed (`phase3_browser_cd6dcb1ec3c4`). Focused paging/workflow 39 passed (37.14s),
final paging/filter 27 passed (24.40s), migration/worker 14 passed (15.67s): these
are overlapping scopes, not additive totals. Final full PostgreSQL regression:
**1,203 passed in 607.28s**, warnings as errors. Test DB restored to **0024**, 30
tables, no leftover browser schemas and clean Alembic drift check. All nine demo
indexes valid; no idle transactions older than 30s at the post-restart check.
No paid calls, password changes, commit or push.



Lifecycle/authorization fencing follow-up (25 October): privileged organization
mutations now acquire job admission then an Organization NO KEY UPDATE fence,
refresh organization/membership/active-user state and reject stale permissions
before writing. Manual finding creation locks inventory, refreshes references and
rejects pending/stopped or completed reference archives. Bulk archive reauthorizes
per independently committed item, preserving prior jobs and explicit refusals.
Ten targeted PostgreSQL race tests passed in 6.71s; 76 existing focused regressions
passed in 91.03s (overlapping scopes; not additive full coverage). Frontend 367
tests/lint/isolated build passed; 35 Chrome checks passed
(`phase3_browser_95ae93ed5925`). Final full PostgreSQL regression: **1,201 passed
in 604.85s**, warnings as errors; includes all 10 new race cases. Focused runs
overlap this full run and are not additive. Normal demo production rebuild and
cancel-only live Chrome smoke passed; existing data/passwords retained. Test DB
restored to 0023/30 tables, no leftover browser schemas, clean Alembic check.
No migration or paid inference; Findings common-search optimization remains step 3.
See [concurrency contract](MULTIUSER_CONCURRENCY.md) for boundaries and lock costs.


25 October multi-user configuration hardening: settings lock/refresh before JSON
merge; profile create/update/delete serialize name checks and refresh cached rows;
consent serialization also protects first-time insertion. Independent-session,
distinct-admin tests are in `test_multiuser_configuration.py`. See
[audit matrix and remaining boundaries](MULTIUSER_CONCURRENCY.md). Full regression:
**1,187 passed in 563.87s**, PostgreSQL required, warnings as errors. Four more
cases were added after collection; final focused file **7 passed in 4.34s**.
These are overlapping runs. Test DB restored to 0023/30 tables, no browser schemas,
clean Alembic check. See Phase 4 validation for the full evidence scope.

25 October search/archive follow-up: 84 focused PostgreSQL paging, archive,
job-boundary and workflow/filter tests passed in 109.79s, warnings as errors.
After query whitespace normalization, 17 overlapping paging tests passed in 23.24s.
Search uses independent tenant-scoped asset/active-assignee match sets rather than
a global outer asset join/correlated assignee lookup. One SA01 count-phase benchmark
improved 14.419s to 8.052s; search performance remains unresolved. No migration,
inference or new full backend run. Frontend 367 tests/lint/build; Chrome 35 checks.

25 October unified Findings action follow-up: **67 focused PostgreSQL archive,
job-boundary and workflow/filter integration tests passed in 66.96 seconds**,
warnings as errors. No backend code/schema changed. Frontend: **365 tests**,
lint/build; Chrome: **35 real API/PostgreSQL checks**, now including an isolated
worker to complete queued bulk archives. Existing server eligibility, tenant,
role and request-limit rules remain authoritative. This is not a new full backend run.

25 October inline-document-preview follow-up: **6 focused PostgreSQL document
integration tests passed in 13.30 seconds**, warnings as errors. Existing version
retrieval/tenant boundaries and document lifecycle APIs are unchanged; this is a
frontend presentation change. **362 frontend tests, 6 grouped document Chrome
checks**, lint and build passed, plus live-demo read-only preview smoke. No new
full backend run or migration. Test DB restored to 0023 with clean drift.

24 October job-notice/Settings follow-up: **45 focused PostgreSQL archive and job
boundary tests passed in 61.35 seconds**, warnings as errors. No backend code or
schema changed. UI auto-dismiss uses the existing permission-checked dismiss
endpoint (sets `dismissed_at`, not deletion), marked background activity.
**357 frontend tests, 34 installed Chrome checks**, lint/build passed. This is not
a fresh full backend run. Test DB restored to 0023 with clean drift.

24 October Finding-ID follow-up: **39 focused PostgreSQL integration tests passed
in 70.05 seconds**, warnings as errors. Exact `finding_id` and complete UUID search
retain active-row/tenant scope and count consistency; UUIDs mentioned in other
descriptions are not identity matches. Partial text stays text search. Frontend:
**344 tests**, lint/build; installed Chrome: **32 checks**. No new migration or
fresh full backend run. Test target restored to 0023 with clean Alembic drift.

24 October identity-search follow-up: **38 focused PostgreSQL integration tests
passed in 43.56 seconds**, warnings as errors. Added validated, opt-in identity
scope without changing default People search. Verified name/email versus role
matches and tenant isolation. **337 frontend tests and 28 Chrome checks**, lint
and build also passed. No migration or new full backend run.

Assignee-history/search follow-up: **37 focused PostgreSQL integration tests passed
in 42.69 seconds**, with warnings as errors (`test_people_api.py`,
`test_finding_workflow.py`, `test_finding_workflow_filters.py`). No backend code or
migration changed in this increment. Frontend: **337 tests**, lint/build;
browser: **28 installed Chrome checks**. This is not a fresh full backend run.

Latest shared-date-filter full run: **1,182 passed in 556.13 seconds**, PostgreSQL
required and warnings as errors. Includes local-day inclusivity, last-microsecond,
DST, invalid/reversed-range checks across shared paging. Frontend **334 tests**,
lint, TypeScript/build and **26 Chrome checks** passed. Supersedes the 1,173 full
checkpoint below; no new schema migration.

Latest timezone correction: **1,173 full PostgreSQL tests passed in 522.38 seconds**
with warnings as errors. **331 frontend tests, 25 installed Chrome checks**, lint,
TypeScript/build and populated 0023 upgrade/downgrade/upgrade with clean drift
passed. This is a fresh full run, superseding the 1,164-test checkpoint below.
Disposable test target restored to 0023, 30 tables, zero browser schemas.

Latest manual-entry/Eastern-deadline full run: **1,164 passed in 538.45 seconds**,
PostgreSQL required and warnings as errors. This includes the new Eastern/DST
unit boundaries and overdue API boundary regression; it supersedes the earlier
1,153-test full checkpoint, not just a focused subset. Frontend: **330 tests**,
lint, TypeScript/build; **24 Chrome checks**. Test target restored to 0022 with
30 public tables, zero browser schemas and clean drift; demo/normal data not reset.

Latest saved-note/history follow-up: **30 focused PostgreSQL tests passed**;
frontend **327 tests**, lint, TypeScript/build and **21 Chrome checks** passed.
This supersedes the 29-focused/326-frontend presentation checkpoint, not the
historical full backend result. No migration or mandatory-note policy change.

**1,153 full backend tests passed** with PostgreSQL required and warnings treated
as errors after UI/filter work (earlier backend-only checkpoint: 1,146). This is a
full-suite result, separate from the focused workflow
checks. Migration 0022 passed empty/populated round trips and drift checks;
`auditmind_test` is restored at 0022 with 30 public tables. No ordinary/demo target
was migrated. [Details and limits](PHASE4_VALIDATION.md). Frontend suite: 323 passed;
lint, TypeScript and isolated production build passed, with 19 installed Chrome
workflow checks. Earlier checkpoints below are historical, not current run totals.

Later presentation-only follow-up passed **29 focused PostgreSQL tests** across
workflow integration/filter and unit/policy files; no new full backend run is
claimed. Frontend: **326 tests**, lint, TypeScript/build and **21 Chrome checks**.
The subsequently approved isolated demo was upgraded to 0022; normal schema was
not migrated. See the rollout and follow-up sections in Phase 4 validation.

## Evidence-aware contract — 2026-10-23 final checkpoint

Subsequent check-in review: final-delimiter prompt fix prevents source/title markers
from truncating captured evidence; one regression added. **130 focused tests passed**
afterward, PostgreSQL required/warnings as errors. Test target restored/checked.
The full1,115-test run below precedes this narrow fix; no1,116 full-run claim.
[Verification steps](EVIDENCE_USER_VERIFICATION.md).

**1,115 full-run tests passed in560.82s**, PostgreSQL required, warnings as errors,
zero failures/errors/skips confirmed by `temp/testing/evidence-v3-final-junit.xml`.
**312 frontend tests**, lint/TypeScript/production build, **18 new-contract and17
legacy Chrome checks** passed. Empty→0021→0020→0021 test restore, drift check and
head no-op passed;29 tables, zero browser schemas left. New mode is opt-in/off by
default; no inference, paid calls or overall coverage measurement. Earlier1,106
run superseded after final hardening. [Scope/failure history](EVIDENCE_ASSESSMENT_VALIDATION.md).

## Presentation follow-up — 2026-10-23

- **71 focused backend tests passed**:43 unit/export,20 PostgreSQL integration,
  8 browser-fixture. Python warnings as errors. **307 frontend tests** and
  lint/TypeScript/production build, **17 Chrome checks** passed.
- Initial Chrome attempt lacked mock citation IDs and failed; corrected fixture
  rerun passed. Only full successful rerun counted. Both schemas cleaned.
- Restored validated local `auditmind_test` public schema to0021 after DB fixtures;
  Alembic check found no new upgrade operations. Demo rebuilt/restarted, existing
  accounts/passwords retained, no external AI credentials supplied.
- No schema/scoring/prompt contract changes, inference or paid calls. See
  [presentation evidence](REPORT_SCORING_UI_REVIEW.md). Focused runs do not replace
  the latest full1,035-test checkpoint or update whole-project coverage below.

## Prompt/context budgets and closure — 2026-10-22

- Implemented `audit-evidence-v3` / `utf8-context-v1`: full prompt/schema/system
  byte guard, bounded finding text with original byte counts/SHA-256, deterministic
  sample/citation omissions, selected-source pins and post-selection allowlists.
  Limits are included in processing targets; fresh approval is required. No
  consent or real inference was enabled, and saved reports were not rewritten.
- Final clean PostgreSQL-required full suite: **1,035 passed in 614.96s**, warnings
  as errors, **zero failures/errors/skips**. Budget context helper: **100% lines
  and branches**; whole backend **94.24% lines / 85.53% branches** (92.59% combined).
- Targeted budget/export checks: **23 passed in 2.28s**. Oversized UTF-8 evidence
  was tested against actual PostgreSQL; descriptions remain unchanged in source
  rows, and omitted finding references are rejected.
- Synthetic PDF reproduction: disabling row splitting raises `LayoutError` for
  long provenance; enabled splitting produces a valid PDF without dropping data.
- Initial full run invalidated by overlapping suites on the public test schema;
  stopped and excluded from passing evidence. Final full run was sequential.
  A test fixture's overlength category and a premature frontend hash assertion
  were corrected and rerun; no failures were suppressed.
- Frontend **300 passed**, lint, TypeScript and fresh production build passed.
  Demo restarted on v3 with existing data/passwords retained and inference disabled.
- Artifacts: `temp/testing/backend-budget-junit.xml`, `backend-budget-coverage.json`,
  `backend-budget-html/index.html`. See [closure checklist](PHASE3_CLOSURE.md).
- After the clean full suite, v3 Chrome native/mock checklist **16/16 passed**;
  schema `phase3_browser_87c7b5fb0631` removed, zero page errors. Test DB restored
  empty→0021→0020→0021; metadata drift clean and repeat upgrade no-op, 29 tables;
  zero leftover browser fixture schemas. UTF8 encoding verified. Production npm
  audit still zero. No ordinary/demo migration or password reset.

## Expanded PostgreSQL/coverage verification — 2026-10-22

- Confirmed **PostgreSQL 18.6 / pgvector 0.8.6**, dedicated `auditmind_test`.
  No SQLite substitutes. Added `--require-postgres`: unavailable DB or skipped
  tests fail the acceptance run. Real synchronous/asynchronous httpx transports
  are blocked by default; tests use explicit mocks.
- Full instrumented backend: **1,005 passed in 633.78s**, **zero errors, failures
  or skipped tests**, warnings as errors. Final coverage-driven follow-up:
  **19 passed in 7.37s**, including 11 new cases added after full collection.
- Cumulative backend coverage: **94.19% lines, 85.34% branches**; combined
  line/branch metric **92.53%**. NIST/shared-baseline module 100% lines/branches;
  embedding adapters 98.55% lines/88.89% branches with mocked models/SDKs.
- Frontend expanded from 274 to **300 passing tests**, **91.98% lines**, **84.85%
  branches**. Report detail 100% lines/93.75% branches; download helper 100% both.
  Lint, TypeScript and production build pass. Existing non-failing React/jsdom
  diagnostics remain visible.
- Fresh Chrome: Phase 2e **25** and Phase 3 **16** real-stack grouped checks passed
  on isolated PostgreSQL schemas. Auth recovery 4 intercepted checks, Documents
  3 role scenarios and dialog 2 viewport scenarios passed. No new model/paid calls.
- Offline tooling: **15 self-tests passed**; `pip check` clean. Production npm
  audit zero; seven development-only braces entries remain, not silently accepted.
- Real CLI negative preflights reject SQLite and unreachable PostgreSQL with
  usage exit 4 before tests. No DB-backed test silently skipped.
- After all DB tests, fresh migration path **empty → 0021 → 0020 → 0021** passed;
  downgrade removed ledger/idempotency fields and re-upgrade restored them.
  `alembic check` clean, repeated upgrade no-op; test public schema restored with
  **29 tables**. Read-only check: zero Phase 2e/3 browser fixture schemas remain.
- Demo was rebuilt/restarted with existing accounts/passwords/data preserved.
  No ordinary/demo schema change or Docker deployment. Docker and date UI remain Future scope.

Reproduction, artifact locations and remaining measured gaps: [TESTING.md](TESTING.md).

## Native Phase 3 browser acceptance — 2026-10-22

- Real Chrome **155.0.8059.85**: **16 native end-to-end checks passed**, real
  frontend/API/worker/PostgreSQL, only inference and embeddings mocked. Zero page
  errors. Final isolated schema `phase3_browser_ff40431384d2` cleaned up.
- Separate intercepted-API UI runs: **3 Documents role scenarios**, **2 report
  dialog viewports** passed with zero scoped Axe AA violations.
- Fixture safety unit tests: **8 passed** (0.15s), rejecting broad schemas,
  nonlocal hosts and wrong/non-test database targets before engine creation.
- Relevant API/worker/accounting/evidence regressions: **54 passed in 41.93s**
  with warnings as errors. No full-suite rerun was required for these new test
  scripts/documentation; the earlier 987-test run is recorded below, not counted
  as a fresh run here.
- After DB regressions, `auditmind_test.public` restored to **0021**, **29 tables**;
  Alembic metadata check clean, repeated upgrade a no-op. Read-only namespace
  check confirmed **zero remaining Phase 3 browser fixture schemas**, including
  cleaned-up earlier harness iterations.
- Existing demo and ordinary data preserved; no paid inference, real model calls,
  model downloads, password resets or Docker deployment.

See [acceptance checklist, artifacts and limitations](PHASE3_ACCEPTANCE.md).
User moved Docker deployment/container validation and optional browser reporting
dates to [Future phase](../PLAN.md#future-phase--deferred-delivery), not core gates.

## Authorized remediation verification — 2026-10-22

- Full backend warnings-as-errors run: **987 passed in 526.62s**.
- After that run, cancellation tests were expanded to both direct Anthropic and
  OpenRouter and strengthened to assert a genuine retryable failure reached the
  retry path: final focused run **24 passed in 16.62s**. This includes the two
  additional direct-Anthropic cases not collected by the preceding full run.
- Unit coverage rejects cancelled, failed, pending, completed, missing and
  foreign-organization jobs using a fresh populated read. Integration coverage
  cancels from an independent committed PostgreSQL session during timeout/429;
  exactly one mocked request and one failed usage reservation remain.
- Frontend: **274 passed**, lint and TypeScript no-emit passed; Next **16.4.2**
  production build passed, including a second build through the demo launcher.
- `npm audit --omit=dev`: **zero vulnerabilities**, exit 0. Unrestricted audit:
  **seven high development-only entries**, one unpatched braces root advisory.
  No claim that the unrestricted audit passes. Installed dependency tree valid.
- Chrome **155.0.8059.85** login smoke: HTTP 200, sign-in controls visible,
  zero page errors. Not a complete Phase 3 browser checklist.
- Demo restarted on loopback with existing accounts/data and inference disabled;
  no password resets or paid calls. After all DB-backed runs, disposable
  `auditmind_test.public` was restored to **0021** (29 tables including Alembic
  metadata); `alembic check` was clean and a repeated upgrade was a no-op.

Details and remaining gates: [release readiness](RELEASE_READINESS.md).

## Original review run — 2026-10-22 (before authorized fixes)

Full suite: `python -m pytest -q -W error` — **979 passed in 503.35s**.
Frontend: **274 passed in 24 files**; `npm run lint` and
`npx tsc --noEmit --incremental false` passed. Non-failing React `act(...)`
diagnostics remain. Python `pip check` passed (not a vulnerability scan).

After fixture cleanup, disposable PostgreSQL `auditmind_test.public` was restored
with `alembic upgrade head`; `alembic check` reported no new operations and a
second upgrade was a no-op. Revision **0021**, 29 tables including version metadata.
No ordinary/demo migration, paid call or live inference occurred.

Production frontend `npm audit --omit=dev --json` failed with **three high-severity
packages**. Mock-only cancellation review also reproduced authorization of a new
attempt after cancellation. See [release readiness](RELEASE_READINESS.md) for
findings, scope and open gates. Passing suites do not clear those findings.
This run did not perform a fresh frontend build or complete Phase 3 Chrome acceptance.
Offline script self-tests also passed: local benchmark **10 tests**, local
evaluation CLI **1 test**, free OpenRouter probe safety **4 tests**. These did not
run a model or make HTTP inference calls.

## Earlier verification records

Latest supplement (2026-10-21): optional OpenRouter/Claude reporting implemented
with real inference disabled. Complete backend suite **965 passed** with warnings
as errors; after final hardening/additional tests, focused provider/report
regressions **93 passed**. Frontend **274 passed**, lint and TypeScript passed.
Disposable test database restored to `0021`; metadata check clean. No paid calls,
ordinary/demo migration or consent changes. See
[OpenRouter verification and remaining gates](OPENROUTER_REPORTING.md) for exact
scope, commands and the distinction between the full run and final focused run.

The local test target is restored to PostgreSQL `auditmind_test`, with pgvector
0.8.6. The ignored local `backend/.env` was corrected; `.env.example` already
contains the proper target. The development database was not migrated.

## Changes reviewed

- Test target validation rejects SQLite, malformed URLs (including invalid ports),
  and names without `_test`, before destructive fixture setup.
- Fixture cleanup removes stale Alembic revision markers together with application
  tables. Previously the database claimed revision `0009` with no application tables.
- Alembic accepts an explicitly supplied connection and version-table schema for
  isolated migration tests. Ordinary CLI commands continue to use `DATABASE_URL`.
- Migration regression creates a random schema only inside `auditmind_test`,
  upgrades from empty to head, rolls back to `0018`, upgrades a legacy report,
  checks reporting indexes and timestamps, repeats the upgrade, then cleans up.

## Results

- Complete backend suite: **783 passed, 7 failed, 0 skipped**, 450.40 seconds.
- After the final fixture changes, all unit and health tests, authentication and
  report API integrations, database safety regressions, and migration regressions:
  **395 passed**, 26.08 seconds.
- Fresh Alembic upgrade of `auditmind_test`: **passed**, revision **0020 (head)**,
  27 application tables. A repeated upgrade also passed.
- `alembic check` against that freshly migrated database: **failed**. Differences
  include enum VARCHAR lengths, reporting/document indexes missing from ORM
  metadata, and the users email unique constraint/index representation.
- Changed tracked test infrastructure passes `git diff --check`; Python
  compilation checks pass.

The complete run was started before the new test-infrastructure regressions were
added; the focused follow-up validates those additions and the final fixture code.
These results do not constitute a green complete suite.

## Baseline review findings (resolved below)

1. Five cases of `test_claude_problems_come_back_as_clear_errors` fail because
   `api/routes/ai.py` catches `ValueError` but the tested Anthropic exceptions
   propagate. Expected HTTP error mapping is not preserved.
2. `test_bulk_retire_and_remove_versions` expects purge to succeed while pending
   publication jobs still reference the versions; the API correctly reports a
   conflict under its current protection rule. Reconcile the test/workflow contract.
3. `test_reactivate_retired_version_reindexes_before_publishing` ends with a 503.
   Its embedding mock does not accept the retrieval adapter's `query=True` keyword.
4. Additional code review found that `claude_service.ask_claude()` references an
   undefined `get_client()`. Mocked report-generation tests do not cover this real
   provider initialization path.
5. Schema/model drift was unresolved in this baseline; resolved in Step 4 below.

No provider requests, model downloads, or development-database migrations were
performed. The unrelated AI/document behavior and existing migration history were
preserved for separate fixes.

See [backend testing instructions](../backend/tests/README.md) for repeatable
unit/integration/regression and migration test commands.

## Step 4 — Schema/model drift resolved

The migrated schema was already correct. ORM declarations now preserve its seven
legacy `VARCHAR(50)` enum columns, named email unique constraint and separate
lookup index, and three composite reporting/document indexes. Newer enum columns
retain their inferred lengths. No migration file or existing data was changed.

Review confirmed that uniqueness enforcement, enum conversion/validation, and
organization-first index column ordering remain intact. The changes pass Python
compilation and scoped whitespace checks.

- Focused schema-contract and migration regressions: **14 passed**.
- Complete backend suite, including the final changes: **805 passed, 7 failed,
  0 skipped**, 453.10 seconds. The same five Claude error-mapping and two document
  cases listed above remain; no new failures appeared.
- Migration regression now runs `alembic check` after a fresh migration and
  rollback/re-upgrade cycle in its isolated schema.
- Read-only `alembic check` against the development database: **passed**;
  current revision remains `0020`. No development migration was run.
- After the suite, `auditmind_test` was rebuilt from empty through Alembic:
  fresh upgrade, drift check, and repeated upgrade all **passed**. It is left at
  `0020 (head)` with 27 application tables and pgvector intact.

Step 4 is complete. At that checkpoint, the remaining AI/document failures and
missing Claude client factory still prevented a green complete suite; these are
resolved in the follow-up below.

## AI/document follow-up — complete suite green

Restored synchronized, lazy Claude client initialization with the configured
timeout and SDK retries disabled, so application retries bound total attempts.
Provider failures now preserve explicit HTTP status mapping without exposing raw
provider evidence. Attempt statistics are counted once, and invalid structured
responses no longer log their contents.

Retirement now cancels queued publication work and disables publication by running
jobs. Purge remains blocked until running work acknowledges retirement. Review
also corrected a stale-session race by refreshing index status under its row
lock. The retrieval embedding mock now accepts the adapter's query keyword.

- Focused Claude/document/API regressions: **41 passed**.
- Final complete backend suite: **827 passed, 0 failed, 0 skipped**, 475.10 seconds.
- The suite emitted **1,740 warnings**, suppressed in its summary run; this is
  not a warning-free result.
- Python compilation and scoped tracked whitespace checks: **passed**.
- After the suite, fresh Alembic upgrade, schema-drift check, and repeated upgrade
  of the verified `auditmind_test` target: **passed**. The test database is left
  at revision **0020**, with 27 application tables.
- Migration regression coverage includes rollback/re-upgrade in an isolated
  schema. No development-database migration was performed.

All five baseline review findings above are resolved. Provider calls were mocked;
these results do not establish live Claude connectivity or production readiness.

## Operational completion and repository cleanup — 2026-10-20

Item 5 implementation now includes PostgreSQL-backed per-attempt quota/cost
reservations, durable token accounting, concurrent organization-scoped report
idempotency, configurable terminal-report retention, and an offline embedding
API/worker image with an external read-only model cache. Migration `0021` adds
the ledger and idempotency constraint; no existing migration was rewritten for
these additions. See [operational contracts](PHASE3_OPERATIONS.md).

Review checked transaction boundaries (no quota lock held during provider I/O),
cross-process admission serialization, conservative charging of unknown outcomes,
idempotent replay/conflict and organization isolation, active-job retention
exclusion, evidence-link cleanup, and page-local retry-key reuse. Provider failure
paths remain mocked. Tests cover independent concurrent database sessions, durable
state after process-metric reset, token/cost recording, and no network call after
quota rejection. Static packaging tests verify offline pinned-model loading,
cache configuration, secret exclusion, non-root image identity, and release-task
migrations rather than startup migrations.

- Final complete backend suite: **837 passed, 0 failed, 0 skipped**, 472.21 seconds.
- **1,774 warnings** remain; this is not a warning-free result.
- Frontend: **239 tests passed**, ESLint passed, production build and TypeScript
  checks passed.
- Python compilation, scoped/staged whitespace checks, and `pip check`: passed.
- Fresh upgrade, schema-drift check, and repeated upgrade of `auditmind_test`:
  passed at **0021**, with **28 application tables**. Rollback/re-upgrade coverage
  is included in the complete suite's isolated-schema migration test.
- No development-database migration, provider request, or model download was run.

Item 6 cleanup reconciles the current roadmap/status with these results, adds
line-ending rules and normalizes pending source/docs, and removes the empty stray
`backend/[--part-mb` artifact (no data was stored there). The application and
archived NIST catalogs still match the documented SHA-256. Project work is grouped
into local source-data, backend/deployment, backend-regression, frontend, and
documentation commits; unrelated local `cline.json` remains untouched. No push is
part of this task.

**Release gate still open:** Docker is unavailable on this machine. Container
build/startup, mounted-cache semantic verification, and staging end-to-end/live
provider checks have not run. Packaging is implemented and statically checked,
not runtime-certified. Full Phase 3 acceptance and production sign-off remain
separate from the green automated suite. The new migration must be applied through
an approved release procedure before these changes run against a real database.

## Approved scope and consent-retry follow-up — 2026-10-21

The user approved deterministic `/risk/score`, AI assessments through reports,
shared 80/60/40 tier boundaries, and separate Phase 3a delivery. These decisions
are recorded in the roadmap, architecture, blueprint and operations guide. AI
tier alignment remains a separate implementation task; legacy snapshots must
not be rewritten.

Report generation now passes an authorization callback through structured Claude
calls. It runs before every attempt, outside provider-error mapping and quota
reservation. Revocation stops retries with the original authorization error;
the check's read transaction is ended before external I/O. Review confirmed the
existing pre-publication consent check remains in place.

- Focused unit/integration/regression run: **36 passed**, 47 warnings, 9.50 seconds.
- New coverage: initial authorization denial, revocation after a timeout,
  structured-wrapper forwarding, and the report pipeline issuing only one mocked
  provider request after revocation. No second quota reservation is created.
- Worker/report operational regressions passed in the same run.
- Python compilation and scoped whitespace checks passed.
- The full 837-test backend suite and frontend checks above are prior-run results,
  not rerun for this patch. No frontend behavior changed in this patch.
- No real provider calls, model downloads or development migrations were run.

This fixes the reproduced consent-between-retries defect; it does not establish
full Phase 3 acceptance or resolve the remaining remediation, scoring, evidence
snapshot, period-UI and Chrome/staging acceptance work.

## Shared scoring and remediation evidence contract — 2026-10-21

New AI domain/overall validation and rule-based test reports now reuse the
deterministic tier function (80/60/40 boundaries). AI scores remain separate from
the rule-based baseline; persisted legacy tiers, including the old high tier at
score 35, are neither revalidated nor rewritten on read/download.

New AI remediations require numeric confidence in [0,1] and explicit UUID finding/
asset lists. Malformed, duplicate and out-of-sample finding IDs are rejected;
asset IDs must link to findings referenced by that action. Empty lists support
general recommendations and assetless findings without fabricated identifiers.
Confidence is model-estimated support, not a calibrated probability. Explicit
non-AI test snapshots use null confidence; real AI generation rejects null.
The viewer, HTML and PDF display confidence and references with legacy fallbacks.

Prompt/consent identity is now `audit-evidence-v2`, schema version 2 and rubric
`shared-tiers-v1`. Existing v1 approval does not authorize new generation; admins
must renew approval for the updated target. No migration or snapshot backfill is
needed. Documentation records this rollout requirement and the legacy behavior.

- Initial focused backend unit/integration/regression run: **75 passed**.
- Complete backend suite: **874 passed, 0 failed, 0 skipped**, 495.94 seconds;
  **1,774 warnings** remain.
- Six database follow-up cases added after the complete run began: **6 passed**,
  41 warnings, 6.68 seconds. They verify stored own-organization references,
  cross-organization finding/asset rejection, assetless findings, HTML/PDF output,
  retained legacy snapshots and renewal of old consent. No application code
  changed between the complete run and this follow-up.
- Frontend: **240 tests passed**; lint, TypeScript and production build passed.
- Python compilation and scoped whitespace checks passed. Review covered shared
  tier logic, schema/UUID validation, safe output escaping, pre-persistence
  validation, versioned consent, legacy compatibility and absence of snapshot
  rewrites. Provider requests were mocked; no model downloads occurred.
- After the tests, fresh upgrade, drift check and repeated upgrade on the verified
  `auditmind_test` target passed at **0021**, with **28 application tables**.
  Development database unchanged.

Chrome end-to-end and Docker/staging acceptance remain outstanding. The next core
implementation gaps are consistent evidence capture and reporting-period UI.

## Consistent evidence capture — 2026-10-21

Inventory counts/categories, severity totals, sampled finding values, rule scores
and retrieved citations now share an independent PostgreSQL repeatable-read
transaction. It commits source-use registrations atomically before returning
evidence and closes before Claude calls. Source locks have stable UUID ordering;
serialization/deadlock conflicts retry the entire capture at most three times.
Repeated conflicts fail closed without publishing mixed evidence or partial pins.
Pending ORM changes in the caller session are rejected without committing or
discarding them; report/source registration verifies organization ownership.

Authorization remains current through a separate read-committed session for
external embedding consent and profile checks. Provenance includes capture
isolation/attempt count/database-clock timestamps and captured inventory totals.
The operations guide explicitly records the query-embedding transaction lifetime
and provider-managed embedding retry limitation; it does not claim that an
already-issued SDK operation is aborted by revocation.

- Initial focused unit/integration/regression run: **79 passed**.
- New concurrency regressions: **16 cases**, included in a **77-passed** focused
  run alongside document, report, consent and assessment-contract regressions.
- Final complete backend suite: **896 passed, 0 failed, 0 skipped**, 537.31 seconds.
  **1,814 warnings** remain.
- Fresh upgrade, schema-drift check and repeated upgrade of `auditmind_test`:
  **passed at 0021**, with **28 application tables**. No migration was added.
- Python compilation and scoped whitespace checks passed.
- An additional isolated-schema PostgreSQL probe confirmed report heartbeat
  updates do not invalidate foreign-key source-use registration. Only disposable
  probe tables in `auditmind_test` were created and removed.
- Review covered MVCC boundaries, source-registration atomicity, session/pool
  isolation, whole-capture retry behavior, current authorization, source-purge
  races, and source locks being released before Claude execution.

The new regression cases commit independent writers between evidence reads and
verify that counts/samples/rule scores retain the original view; document
publication forces a full fresh capture with matching new findings and citations.
Failure tests verify bounded retries and rollback of all source-use registrations.
The provider-boundary regression observes committed pins and acquires a source
lock immediately, then confirms active-report usage still blocks purge.

No real providers or model downloads were used. Development data was not migrated
or changed. This follow-up changes no frontend behavior; prior frontend results
remain 240 tests plus lint/TypeScript/build passing, not rerun here. Next core work:
reporting-period UI, followed by Chrome/staging and release acceptance.

## Backend warning remediation - 2026-10-21

The earlier 1,814-warning result above is historical, not the current result.
A complete diagnostic run before changing installed dependencies used
`pytest -q --tb=short --show-capture=no -W default`: **896 passed**, **402 warnings**,
497.02 seconds. The different count reflects warning deduplication, not fixes:
401 warnings came from `python-jose` calling deprecated `datetime.utcnow()`
during JWT validation, and one came from Starlette's deprecated AnyIO
`BlockingPortal` alias. These were the only warning types in that complete run.

Changes:

- Upgraded `python-jose[cryptography]` from 3.3.0 to 3.5.0, which uses timezone-aware
  UTC during validation. No application token format or password hashing change.
- Temporarily pinned AnyIO to 4.14.1 for the current FastAPI 0.115.6 / Starlette
  0.41.3 stack. This avoids the alias deprecation introduced in AnyIO 4.15; it is
  a compatibility constraint, not a patch to upstream Starlette. Reassess/remove
  the pin when upgrading FastAPI and Starlette together. Sources and rationale
  are recorded in `backend/tests/README.md`.
- Added five JWT regressions: session claims, invalid signatures, unsigned
  tokens, independent legacy HS256 compatibility and algorithm allowlisting.
  Existing expiry and signed round-trip checks remain.
- `pytest.ini` now turns JWT and Starlette test-client deprecations into errors.
  No warning ignore filters or site-packages edits were added. Other warnings
  remain visible during ordinary runs.

Verification on Windows / Python 3.12.7:

- Focused security suite with `-W error`: **9 passed**, 1.04 seconds.
- Complete backend suite with `pytest -q --tb=short --show-capture=no -W error`:
  **901 passed, 0 failed, 0 skipped, 0 warnings**, 491.82 seconds. This includes
  unit, API integration, worker, concurrency, regression and migration tests.
- Dependency installation succeeded and `pip check` reported no broken
  requirements. Scoped whitespace checks and Python compilation passed.
- After testing, fresh upgrade, drift check and repeated upgrade passed with
  `-W error` on the verified `auditmind_test` target: revision **0021**, **28
  application tables**, no new upgrade operations. Development data unchanged.
- Review covered version constraints, explicit JWT algorithm restrictions,
  expiry validation, existing token compatibility and unchanged password hashing.

No frontend files were changed for this remediation. Frontend/Chrome, Linux CI,
container builds and real-provider acceptance were not rerun; this is not a
claim of a broader dependency security audit or complete Phase 3 acceptance.

## Isolated browser demo and user manual - 2026-10-21

`start-demo.ps1` prepares and runs a synthetic browser demonstration. The existing
local role cannot create databases, so the implemented isolation is a dedicated
`auditmind_demo` schema, not a new database. Only that schema is migrated and
seeded. The regular `public` revision remains **0020**, with its original **9 users
and 9 organizations**; the demo is at **0021**, with **4 assets and 7 findings**.
The regular development application is not upgraded or declared release-ready.

The demo starts API, worker and production frontend bound to 127.0.0.1, with
separate generated organization/platform credentials. External provider keys are
blanked before service imports, public sign-up stays closed, local model downloads
are disabled and rule-based previews are explicitly non-AI. Repeated preparation
preserves passwords and edits; the launcher supports stop/restart with data retained.
Process cleanup checks both PID and recorded start time before stopping a process.

Readiness testing found stale frontend configuration pointing to port 8002. The
launcher now overrides BACKEND_URL and NEXT_PUBLIC_API_URL for build/runtime,
validates its own build marker for SkipBuild, and checks the frontend API proxy
in addition to API liveness and the login page. No personal .env files were edited.
The first browser harness used networkidle against an intentionally polling app;
it now waits for routes/UI state. Search-input accessibility role was corrected
in the harness from textbox to searchbox. These were not application test passes
until the final smoke run succeeded.

Verification:

- Focused demo safety/idempotency/credential isolation plus JWT regressions:
  **16 passed, 0 warnings**, with `-W error`, 2.84 seconds. Seven cases cover the
  new setup; database-backed cases use `auditmind_test`, not the demo or app tables.
- Full frontend suite: **240 passed** with `npm test -- --maxWorkers=2`; lint passed.
  The first concurrent build/test attempt had worker-start timeouts and was not
  accepted. The lower-concurrency rerun completed without those errors.
- Production frontend build and its TypeScript check passed after the proxy fix.
- Installed **Google Chrome 155.0.8059.85**, headless through Playwright's chrome
  channel: organization/platform sign-ins; nine organization pages and five
  platform pages; asset hostname filtering/clearing; authenticated worker heartbeat;
  session refresh; creation of a non-AI report through the UI; HTML content and PDF
  signature downloads; no uncaught page exceptions or HTTP 5xx responses observed.
- Stop/restart with SkipBuild and retained credentials/data passed; the final
  Chrome smoke ran successfully after restart. API, worker and frontend were left
  running for the user's browser tour.
- Test database restored with fresh/repeated upgrade and drift check at **0021**,
  **28 application tables**, using `-W error`. No schema drift detected.
- Scoped whitespace checks, Python compilation and browser-script syntax check
  passed. Review covered schema/revision isolation, no credential reset, disabled
  paid providers, loopback bindings, proxy/build settings and safe process cleanup.

[User manual](USER_MANUAL.md) includes sign-in, permissions, feature tour, scoring,
imports and example CSV files, evidence lifecycle, consent, reports/exports,
administration and troubleshooting. Generated local sign-in details, screenshots,
download samples and browser result JSON are in ignored `temp/auditmind-demo/`;
they are not committed or public credentials. Delete the local credential note
after storing passwords securely; it contains only initial demo passwords.

This is a desktop Chrome smoke test, not complete browser release acceptance,
mobile/accessibility coverage, a new complete backend-suite run, container
validation or real-provider approval. Real semantic indexing still requires its
prepared model cache; the synthetic document remains unpublished until indexed.
No real AI requests or new model downloads were made.

## Filter dropdown dismissal - 2026-10-21

The shared PickFilter used native details/summary toggling only; it did not close
on outside clicks. Added a capture-phase document click listener and Escape
handling, with listener cleanup on unmount. Internal checkbox/Clear clicks stay
open, dismissal preserves selections and Escape restores summary focus when focus
was inside. Opening a different filter also dismisses the previous one. PickFilter's
list prop now declares only the two operations it actually consumes.

- Five new component regressions cover outside dismissal/selection preservation,
  multi-select/Clear, Escape/focus, summary toggling/another picker and event
  propagation/listener cleanup.
- Complete frontend suite: **245 passed**, `npm test -- --maxWorkers=2`, 38.95 seconds.
  Lint and the final production build/TypeScript check passed. The first build
  rejected an incomplete test-fixture type assertion; the fixture and component
  prop contract were corrected before the accepted verification run.
- Scoped whitespace and browser-harness syntax checks passed. The shared fix
  applies across pages using PickFilter, not just the Assets type selector.
- Rebuilt/restarted the isolated demo successfully with its existing data and
  credentials retained. The manual now explains outside-click/Escape dismissal.
- Extended the real-Chrome harness for this interaction, but the signed-in rerun
  could not proceed: saved initial demo credentials no longer match account hashes.
  One failed login was observed; there were no repeated login attempts or password
  resets. This change is **not claimed as signed-in Chrome verified**. The prior
  browser smoke evidence above predates this fix.

Backend application/schema code was unchanged; no backend suite was rerun for this
frontend-only interaction fix.

## Protected account renewal and Platform loading recovery - 2026-10-21

The API client excluded all `/auth/` paths from renewal, so an expired bearer on
`/auth/me` could fail even when the session cookie remained valid. `useMe` returned
null for both loading and errors; SysadminOnly interpreted that error as perpetual
Loading. Protected account routes now use the existing one-retry/shared-refresh
logic. Only login, register, refresh and logout remain exempt, including when
queried with URL parameters. Renewal failures preserve the existing server-error
behavior; repeated unauthorized responses clear the token and notify sign-out.

Added `useMeState` without breaking existing `useMe` consumers. The shared Platform
guard distinguishes loading/errors, offers Retry and continues to deny non-sysadmins.
No account privileges, session duration, password policies or backend authorization
rules were changed.

- Complete frontend suite: **256 passed**, 36.75 seconds, with two test workers;
  lint and production build/TypeScript checks passed.
- Eleven new regressions cover protected account renewal, excluded session
  endpoints, bounded repeated refusal/sign-out, Platform renewal and error/retry,
  and denial of non-sysadmins. Existing concurrency/server-unavailability tests
  remain in the complete suite.
- Real installed Chrome **155.0.8059.85**, using intercepted API fixtures against
  the production frontend: an expired account lookup renews and renders Security
  defaults without a hard refresh; a temporary failed lookup shows an error/Retry;
  Retry restores the form without a reload. No uncaught page exceptions observed.
  This is a controlled browser regression, not live authentication using the user's
  changed demo credentials. No account/password reset was needed or performed.
- Browser harness: `scripts/browser-auth-recovery.cjs`; result JSON is in ignored
  `temp/auditmind-demo/browser/auth-recovery.json`. The harness intercepts API calls
  and does not change backend data, settings or provider configuration.
- Scoped whitespace and harness syntax checks passed. Review covered route
  exclusions, bounded retry behavior, authorization denial and error/loading states.
- The isolated demo was rebuilt/restarted and left running. Backend code/schema
  was unchanged and the backend suite was not rerun for this frontend-only fix.

## Report-generation dialog UI alignment - 2026-10-21

AI and rule-based preview generation now share an application-owned native dialog
with labelled title/description/close action, explicit organization context,
initial focus, Tab/Shift+Tab wrapping, Escape handling and focus restoration.
Named navy/cyan tokens replace custom modal colours. A viewport-height limit,
scrollable content and sticky actions keep the form usable on small screens.
Frameworks use fieldset/legend, labelled controls and plain-language evidence/
licensing guidance. Errors are announced through alerts. Submission remains
single-flight; controls and dismissal are blocked until the request settles.

The dialog fetches report consent on each opening and organization change. Loading,
missing and failed checks block AI submission. Missing approval links to Documents
with the selected organization ID; auditors are told to ask an admin. Failed checks
offer Retry. The dialog never grants consent. Server refusal triggers a fresh
consent check, while backend authorization remains authoritative. Approval does
not assert provider credentials, indexed evidence or worker readiness; these are
called out separately rather than claimed as checked. Test previews make no
consent request and remain explicitly non-AI.

- Complete frontend suite: **265 passed**, 43.36 seconds, with two workers; lint
  and final production build/TypeScript checks passed. Nine new dialog cases cover
  organization/reopen isolation, focus wrapping, consent blocking/link, auditor
  guidance, check failure/retry, validation/single-flight/busy cancellation,
  revocation after server refusal, dismissal/focus return and non-AI previews.
  Existing report/idempotency regressions were updated for the consent preflight.
- Installed Chrome **155.0.8059.85**, production frontend with intercepted synthetic
  API fixtures: **1440x900 and 390x640** both passed consent gating, scoped Documents
  navigation, retry/enabling after approval, initial focus, repeated keyboard
  containment, Escape/focus return, viewport fit, reachable actions and preview
  mode checks. No generation requests or uncaught browser exceptions occurred.
- Axe scans scoped to the open dialog, WCAG 2 A/AA and 2.1 AA tags: **0 violations**
  at both sizes. This does not claim a whole-application accessibility audit.
- The initial Chrome run exposed native Tab behavior leaving document focus at
  the end of the tab order; explicit wrapping was added and the final checks rerun.
  Component tests polyfill only dialog open/close in jsdom; real focus containment
  and modal behavior are verified in Chrome, not inferred from that polyfill.
- The existing controlled Chrome account-renewal/retry regression also passed
  against the final build. Browser scripts/results/screenshots are respectively
  `scripts/browser-report-dialog.cjs` and ignored `temp/auditmind-demo/browser/`.
- Scoped whitespace and browser-script syntax checks passed. Review covered
  consent boundaries/stale state, single-flight behavior, native dialog lifecycle,
  focus cleanup, group semantics, error announcements and role-specific guidance.
- The demo was rebuilt/restarted and left running. Existing accounts, consent,
  provider credentials and security settings were not changed. No live provider
  calls, backend code/schema changes or backend-suite rerun were part of this fix.

UI conventions and the user manual now document the report form's behavior.

## Documents permissions, lifecycle and UI alignment - 2026-10-21

The common DocumentsLibrary now hides mutation selections/bulk actions/forms in
read-only mode and restricts mutable rows to their owning scope. Changing scope or
write access remounts the library state, dropping prior selections. Organization
Documents displays its actual organization name; Shared standards is guarded by
SysadminOnly as well as the unchanged backend authorization. Platform configuration
and baseline controls are not mounted for read-only library consumers.

Reactivation status requires a retained retired version and a pending/running
publication job. Initial publication is Queued/Processing, not Reactivating.
Lifecycle/processing states use shared StatusBadge with an optional display label;
existing callers retain the same default behavior. Source, rights and hashes are
available in collapsed Version details. Pending reactivation still blocks removal.

Upload document is the header action and opens a labelled inline form with focus,
submission/cancel actions and preserved upload metadata contract. Separate named
consent sections show approval/local-processing status and optional target details.
Approve/revoke requires explicit inline confirmation with the target; loading or
failed status checks disable changes. This does not auto-grant approval. Platform
embedding fields now have visible labels, busy guards and distinct success/errors.
Permitted-evidence search has independent loading/error/count/empty-result states,
and clears old results before a new request, without altering document-list filters.

- Complete frontend suite: **274 passed**, 40.35 seconds, with two workers;
  lint and production build/TypeScript checks passed. Nine new cases cover read-only
  viewer/auditor UI, ownership, initial lifecycle labels/compact metadata, header
  upload/cancel, explicit report-consent confirmation, evidence results/errors,
  read-only platform controls and the non-sysadmin Shared standards route guard.
  Existing reactivation, bulk removal/retirement and shared-component tests passed.
- Backend `tests/integration/test_documents_api.py`: **6 passed**, 6.98 seconds,
  `-W error`. Covers ingestion/scope, viewer/consent restrictions, bulk lifecycle,
  reactivation and queued/running retirement/purge protections. No backend source
  changed and the complete backend suite was not rerun for this UI task.
- Installed Chrome **155.0.8059.85**, desktop production frontend with synthetic
  intercepted API fixtures: viewer, organization-admin and platform-admin views
  passed ownership/read-only checks, correct badges, compact version details,
  labelled uploads, explicit consent confirmation, empty evidence search and
  visible platform configuration labels. Fixture uploads checked multipart file
  naming; no real uploads, consent grants, profile changes or provider calls occurred.
- Main-content Axe scans (WCAG 2 A/AA and 2.1 AA tags): **0 violations** in all
  three browser scenarios. These were desktop scans, not mobile/full-app acceptance.
  An initial harness exact-text selector included extra scope text in its cell;
  it was corrected before the accepted run. No uncaught page exceptions observed.
- Harness and local evidence: `scripts/browser-documents-ui.cjs`; ignored JSON/
  screenshots in `temp/auditmind-demo/browser/`. Scoped whitespace and script syntax
  checks passed. Review covered ownership/role controls, remount isolation,
  lifecycle wording, confirmation targets, semantic labels and search error states.
- After DB-backed testing, `auditmind_test` fresh upgrade, drift check and repeated
  upgrade passed at **0021**, **28 application tables**, with `-W error`.
- The isolated demo was rebuilt/restarted and left running. Existing account,
  consent, security and embedding-profile values were not modified. UI conventions
  and the user manual describe the revised library flows.
# Phase 2e lifecycle boundary and browser acceptance — 2026-10-21

The original Phase 2d/2e requirements were traced to implementation. Fixed the
later Phase 3 integration gap: all org-owned active job types block organization
archive, job admission shares the org row lock against exclusive archive, and
inactive-org legacy AI/index jobs fail closed. Import/retry/archive admissions
use the same boundary. No migration or real consent change is required.

- Full backend: `pytest -q -W error` — **918 passed**, 536.17 s, no skips.
- Final focused pass after column-based lifecycle re-read and upload/archive
  admission refinements: archive boundary, archive API, review fixes, background
  import, worker/activity, documents, worker reports and platform API modules —
  **139 passed**, 149.05 s, no skips, warnings treated as errors.
- Frontend: **274 passed**; ESLint passed. No frontend implementation change or
  rebuild was needed; browser tests used the existing production frontend.
- Installed Chrome **155.0.8059.85**, headless desktop 1440×1000:
  `node scripts/browser-phase2e.cjs` — **25 grouped acceptance checks passed**,
  no page exceptions. Real API, real worker, real PostgreSQL in a unique local
  test schema; only transport routing was intercepted, not API behavior.
- Time/active-job cases used restricted synthetic database fixtures. No external
  provider calls/downloads. All credentials were blank in the isolated backend.
  Real demo users, SA01, passwords and consent were not changed.
- Browser child processes stopped and synthetic schemas removed. Verified no
  `phase2e_browser_*` schemas remain. Test public schema restored to migration
  **0021**, 28 application tables; drift check and repeated upgrade passed.
- Syntax checks passed for the browser harness, fixture CLI and regression file;
  scoped `git diff --check` passed (existing Git line-ending notice is not a
  test/runtime warning).

Full checklist, qualifications and code-review decisions:
[PHASE2E_ACCEPTANCE.md](PHASE2E_ACCEPTANCE.md). PLAN.md stale lifecycle/Phase 2e
checkboxes reconciled; historical sign-off retained without inventing a new one.
