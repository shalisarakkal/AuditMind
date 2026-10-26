# Testing strategy and measured coverage

Latest follow-up: **1,244 Linux PostgreSQL tests** (331.37s), **377 frontend tests**
(58.16s), lint/TypeScript/production builds, **39 local Chrome checks** and hosted
Chromium acceptance passed. See [per-SHA evidence and CI results](BACKEND_DEPENDENCY_REMEDIATION.md).
This supersedes earlier local-only/dependency checkpoints; counts are not additive.
Clean dev-only installation no longer depends on optional OpenAI SDK packages.

Latest dependency checkpoint (26 October): **1,238 full PostgreSQL tests**
(628.60s, warnings as errors), **376 frontend tests** (29.03s), lint, production
build and TypeScript passed. **39 installed-Chrome workflow checks** and **6
separate Documents grouped checks** passed; scopes are not interchangeable.
The 73 focused compatibility/14 JWT tests overlap the full suite. Backend audits
for core/dev, optional embeddings and installed packages are clean, with no
dependency conflicts. Hosted CI remains unverified. Earlier failing-audit text
below is historical. [Final evidence](BACKEND_DEPENDENCY_REMEDIATION.md).

Latest local operations increment: **1,229 full PostgreSQL tests** (651.52s),
final **20 focused tests** (7.08s), **376 frontend tests** (21.87s), lint/builds
and **39 installed-Chrome checks**. Focused coverage includes final edits/new
guard cases collected after the full run; counts are not additive. New CI jobs
are configured but hosted execution is unverified, and the backend dependency
audit fails. [Evidence and limitations](PHASE4_LOCAL_OPERATIONS.md).

Final pre-push rerun (26 October): **372 frontend tests** (22.19s), lint,
TypeScript and **54 focused PostgreSQL tests** (33.21s) passed. Prior full backend,
production-build and Chrome evidence below is preserved separately. See
[check-in review](PHASE4_VALIDATION.md) for scope, secret checks and exclusions.

26 October lifecycle selection UI follow-up: **372 frontend tests** (25.74s),
lint, TypeScript/production builds and **37 installed-Chrome workflow checks**
passed, including Archived multi-selection and shared Assets/Uploads safeguards.
The prior 1,218-test backend result remains earlier evidence, not a new run for
this frontend-only change. See [current validation](PHASE4_VALIDATION.md).

26 October deadline validation follow-up: **1,218 full PostgreSQL tests passed**
(637.17s, warnings as errors), including the **54 focused deadline/workflow tests**
(44.30s; not additive). **367 frontend tests** (23.64s), lint, production builds,
and **35 installed-Chrome workflow checks** passed. New regressions cover today's
deadlines, creation-day boundaries, local midnight and atomic bulk rejection.
See [current validation evidence](PHASE4_VALIDATION.md). No inference/paid calls.

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


25 October multi-user follow-up: 367 frontend tests/lint/build passed, with row
actions disabled during selection; 35 installed Chrome checks passed
(`phase3_browser_ea1eb15a3a45`). Added independent-session/distinct-admin PostgreSQL
configuration tests: full backend **1,187 passed in 563.87s**; final focused file
**7 passed in 4.34s**, including four cases added after full-run collection.
Overlapping runs, not additive; PostgreSQL required and warnings as errors.
See [concurrency review](MULTIUSER_CONCURRENCY.md) for test scope and limitations.


25 October archive-confirmation/search follow-up: **367 frontend tests**, lint and
isolated production build passed; **84 focused PostgreSQL tests** passed in
109.79s with warnings as errors, then **17 paging tests** passed in 23.24s after
a whitespace-query regression addition (overlapping runs, not 101 unique tests).
**35 installed Chrome checks** passed (`phase3_browser_6266c82a3ae4`), including
real pointer attempts against the inert archive-modal background. Row confirmation
names one finding/UUID; bulk confirmation freezes selected names/count/IDs. Cancel
is initially focused; cancellation and repeated submission are blocked while busy.
No schema or inference changes. Earlier full backend results were not rerun.

**Search performance remains open:** a local SA01 substring count-phase benchmark
improved from 14.419s to 8.052s after replacing the outer asset join and correlated
assignee search with independent match sets. This is one count-only measurement,
not end-to-end latency or performance acceptance. PostgreSQL indexed-search work
is still needed; no index migration was applied.


## Latest evidence-aware contract acceptance — 23 October 2026

Check-in review subsequently fixed untrusted prompt-marker truncation and added
one regression: **130 focused tests passed** afterward. The full1,115-test
checkpoint below precedes that narrow fix; a fresh1,116-test run is not claimed.
[Reproduction/user checklist](EVIDENCE_USER_VERIFICATION.md).

**1,115 full backend tests passed**, PostgreSQL required, warnings as errors, zero
failures/errors/skips. **312 frontend tests**, lint/TypeScript/build passed. Chrome:
**18 new-contract +17 legacy** checks passed with mocked inference and isolated
schemas. Test DB restored to0021; migration round-trip/drift check clean. No new
overall coverage measured. [Final evidence](EVIDENCE_ASSESSMENT_VALIDATION.md).
Earlier full/focused checkpoints below are historical, not current test counts.

## Earlier presentation regressions — 23 October 2026

**307 frontend tests** across27files, **71 focused backend tests** (43 unit/export,
20 PostgreSQL integration,8 browser-fixture), lint/TypeScript/build and **17 native
Chrome checks** passed. Python warnings treated as errors. Real API/worker/PostgreSQL,
mocked embeddings/inference. First Chrome attempt lacked mock citation IDs; fixed
fixture rerun passed in full. [Details](REPORT_SCORING_UI_REVIEW.md). No new full
backend run or coverage measurement; dated baseline below remains historical.
Test DB restored to0021 with no drift; browser schemas cleaned. Existing jsdom
navigation diagnostic remains nonfatal.

Use **real PostgreSQL**, not SQLite, for integration/regression/concurrency tests.
Dedicated target: local `auditmind_test`, PostgreSQL 18.6, pgvector 0.8.6 verified
on 22 October 2026. Never point destructive fixtures at the ordinary/demo target.

## Latest verification — 22 October 2026

Latest prompt-budget implementation: **1,035 full-run tests passed**, zero
failures/errors/skips, in 614.96s. Coverage **94.24% lines / 85.53% branches**
(92.59% combined); input-budget helper 100% lines/branches. Artifacts are
`backend-budget-junit.xml`, `backend-budget-coverage.json`, `backend-budget-html`
under `temp/testing`. Frontend remains **300 passing tests** with fresh
lint/TypeScript/build passes. See [closure verification](PHASE3_CLOSURE.md#verification-for-this-implementation).
The earlier coverage-expansion checkpoint below is retained for comparison.

| Run | Result |
| --- | --- |
| Full backend, PostgreSQL required, warnings as errors | **1,005 passed in 633.78s; zero failures/errors/skips** |
| Coverage-driven follow-up: embeddings + real-PostgreSQL shared baseline | **19 passed in 7.37s**, including 11 new cases added after full-run collection |
| Frontend | **300 passed**, 26 files; lint, TypeScript and production build passed |
| Native installed Chrome | Phase 2e **25**, Phase 3 **16** grouped checks passed; isolated PostgreSQL schemas cleaned |
| Intercepted-API Chrome | Auth recovery **4** checks, Documents **3** role scenarios, report dialog **2** viewport scenarios passed |
| Offline tooling | **15** self-tests passed; no inference |
| Dependencies | Production npm audit zero; installed tree valid; Python `pip check` clean. Existing seven development-only braces entries remain. |
| Migrations | Empty test schema → 0021 → 0020 → 0021; drift check clean, repeated upgrade no-op; 29 tables restored; zero browser fixture schemas remain. |

Backend cumulative instrumentation after the full run and coverage-driven follow-up:
**94.19% lines** (7318/7769), **85.34% branches** (1531/1794), **92.53% combined**.
Do not confuse the combined pytest-cov percentage with line-only coverage.
The full run was collected before 11 additional cases were added; this is not a
claim of one 1,016-test full run. Final targeted JUnit and full-run JUnit both
record zero failures/errors/skips. Early new-test assertion mismatches were fixed
and rerun; final counts above are passing runs only.

`knowledge_standards.py` went from no direct pytest coverage to **100% lines and
branches**, using real PostgreSQL/API/worker tests for sysadmin permission,
repeat-load identity, published NIST retrieval and exclusion of restricted CIS/ISO
reference-only text. `knowledge_embeddings.py` now has **98.55% lines / 88.89%
branches** with fully mocked SDKs/models, not real provider-quality evaluation.

Machine-readable evidence: `temp/testing/backend-junit.xml`,
`backend-targeted-junit.xml`, `backend-coverage.json`, `backend-html/index.html`,
plus frontend reports below. Backend coverage is cumulative instrumentation;
browser/subprocess coverage is not merged. Full backend run: Python 3.12.7.

## Required PostgreSQL acceptance mode

From `backend`, install pinned development requirements, then run:

```powershell
New-Item -ItemType Directory -Force -Path ..\temp\testing | Out-Null
$env:COVERAGE_FILE = '..\temp\testing\backend.coverage'
.\.venv\Scripts\python.exe -m pytest -q -ra -W error --require-postgres --cov=app --cov-branch --cov-report=term:skip-covered --cov-report=json:../temp/testing/backend-coverage.json --cov-report=html:../temp/testing/backend-html --junitxml=../temp/testing/backend-junit.xml
```

`--require-postgres` fails before tests if the PostgreSQL test target is unavailable
and fails acceptance runs containing skipped tests. There is no SQLite fallback.
The coverage report's `skip-covered` option only hides fully covered source files
from the terminal table; it does not skip any tests.
Default real httpx synchronous/asynchronous transports are blocked by an autouse
fixture; provider tests must explicitly install mocked transports. FastAPI's
in-process TestClient and PostgreSQL's native driver remain available. Browser
fixtures run in separate processes with their own inference-disabled/mocked
boundaries. No real inference or model downloads belong in the regression suite.

The public test schema is rebuilt/dropped by fixtures. Do not run two suites
mutating that schema concurrently. Restore its Alembic head after completion,
run `alembic check`, and verify a repeated upgrade is a no-op, using the explicitly
validated test target/connection—not whichever ordinary database is configured.

## Frontend coverage

From `frontend`:

```powershell
npm.cmd run test:coverage
npm.cmd run lint
npx.cmd tsc --noEmit --incremental false
```

V8 reports include all `src` TS/TSX application files, including unimported files;
only tests, test helpers and declarations are excluded. Artifacts:
`temp/testing/frontend-coverage/index.html`, `coverage-summary.json`,
`coverage-final.json`. Server/framework behavior also requires real Chrome tests;
unit coverage does not prove browser rendering or semantic AI quality.

Measured 22 October 2026: **300 tests across 26 files passed**, **91.98% lines**,
**84.85% branches**, **89.93% statements**, **86.95% functions**. Initial baseline
was 274 tests, 89.65% lines and 83.42% branches. Added report-detail lifecycle and
download tests address actual gaps: route 100% lines/93.75% branches; download
helper 100% lines/branches. No application source was excluded to raise coverage.
Existing non-failing React `act(...)`/jsdom navigation diagnostics remain visible.

## Browser and operational matrix

| Layer | Coverage |
| --- | --- |
| Backend full suite | API permissions, tenant isolation, auth/session lifecycle, parsers/imports, archive/restore/purge, workers, scoring, documents, evidence snapshots, reports, quotas, idempotency, retention and mocked provider failures; line/branch reports identify remaining gaps. |
| Frontend unit/component | All existing suites plus report-detail pending/running polling, loading/errors, unmount handling, download errors/retry, safe filenames, authorization headers, ZIP payloads and blob URL cleanup. |
| Chrome Phase 2e | Real API/worker/PostgreSQL isolated-schema identity, permissions, organization lifecycle and browser security checks. |
| Chrome Phase 3 | Real API/worker/PostgreSQL, mocked inference/embeddings: document publication/retrieval, consent, roles/isolation, report success/invalid output/429/cancellation, exports and snapshot preservation. |
| Chrome intercepted UI | Auth renewal/error recovery, Documents admin/viewer/platform controls, report-dialog desktop/mobile keyboard/layout and scoped Axe AA checks. |
| Migrations | Restore/check test revision 0021 and verify no metadata drift after destructive fixture runs. |
| Offline tools | Local benchmark 10, evaluation CLI 1 and free-probe safety 4 self-tests; no inference. |

With the native demo already running, invoke from repository root:

```powershell
node scripts/browser-phase2e.cjs
node scripts/browser-phase3.cjs
node scripts/browser-auth-recovery.cjs
node scripts/browser-documents-ui.cjs
node scripts/browser-report-dialog.cjs
```

Native harnesses create random isolated schemas in `auditmind_test`, use their own
synthetic credentials, refuse occupied fixture ports, stop only owned processes
and remove only their validated fixture schemas. They never use `SIGN_IN.txt`.
Do not count intercepted API scenarios as real-backend acceptance.

## Limits and follow-up

Measured remaining gaps include document API error/bulk paths, worker recovery
error branches, observability and legacy embedding/RAG/standards helpers. Frontend
unit gaps include platform-account actions, some Documents transitions and
framework/proxy/server wrappers. Some of these execute in Chrome but are not
included in unit-coverage percentages. Prioritize these by risk; do not exclude
them or declare 100% overall coverage. Load/soak and real model-quality testing
remain separate work.

Coverage is measured evidence, not a claim of exhaustive testing or zero defects.
Browser/subprocess execution is not merged into pytest/Vitest coverage figures.
Production load/soak, real AI quality/model/pricing acceptance and container/cloud
deployment are not established by these runs. Docker/cache/container deployment
and browser reporting-date controls are user-deferred [Future](../PLAN.md#future-phase--deferred-delivery)
items. The known development-only braces advisory is not silently accepted.

See [backend validation](BACKEND_VALIDATION.md),
[native Phase 3 acceptance](PHASE3_ACCEPTANCE.md) and
[release readiness](RELEASE_READINESS.md) for exact dated run results and sign-off limits.

# Phase 4 remediation checkpoint — 23 October 2026

25 October unified Findings actions: **365 frontend tests, 67 focused PostgreSQL
archive/workflow tests (66.96 seconds, warnings as errors), 35 installed Chrome
checks**, lint/build passed. Tests cover mixed/cross-page eligibility, independent
100-workflow/500-selection limits, frozen archive targets, real queued bulk archive
completion, sticky row actions, roles and regressions. Chrome uses an isolated
worker/schema and disables inference. Earlier full backend and document browser
results are historical rather than combined totals.

25 October inline-preview follow-up: **362 frontend tests, 6 focused PostgreSQL
document tests (13.30 seconds, warnings as errors), 6 grouped installed-Chrome
checks across viewer/admin/platform**, lint/build and live-demo preview smoke
passed. Covers inline placement, column spans, local loading/error/retry, stale
response suppression, filter reset, text safety, removed versions, focus/keyboard
scrolling and mobile containment; scoped Axe AA passes open/closed preview states.
Browser role fixtures are intercepted, not live consent/upload writes. These are
document-focused results, not another full backend or workflow browser run.

24 October job-notice/Settings follow-up: **357 frontend tests, 45 focused
PostgreSQL archive/boundary tests (61.35 seconds, warnings as errors), 34 installed
Chrome checks**, lint and build passed. Covers visible-time dismissal, hover/
focus/tab/viewport pauses, failures/manual retry, warnings, mixed groups, persisted
background dismissal, full Settings desktop width and no mobile page overflow.
Upload-report review is unchanged; earlier full backend results remain historical.

24 October Finding-ID traceability: **344 frontend tests, 39 focused PostgreSQL
tests (70.05 seconds, warnings as errors), 32 installed Chrome checks**, lint,
TypeScript/build passed. Covers expand/copy and clipboard refusal, exact-ID
lookup/counts, archived exclusion, organization switching, report/Activity links,
refresh, malformed IDs and foreign-tenant denial. Earlier full backend evidence
remains historical, not combined with this focused result.

24 October identity-search follow-up: **337 frontend tests, 38 focused PostgreSQL
tests in 43.56 seconds (warnings as errors), 28 installed Chrome checks**, lint
and build passed. Assignee search excludes role/status-only matches; People-page
search remains unchanged. This is not another full backend run.

Latest assignee-history/search follow-up: **337 frontend tests, 37 focused
PostgreSQL integration tests (42.69 seconds, warnings as errors), 28 installed
Chrome checks**, lint and production build passed. Tests cover unchanged owner
suppression, names/email instead of raw user IDs, member search, empty results,
pagination, retained selection and save-only assignment. Earlier full backend
evidence below remains the latest full run; this follow-up is focused.

Latest compact-time/full-day-filter checkpoint: **1,182 full PostgreSQL tests
passed in 556.13 seconds**, **334 frontend tests**, lint, TypeScript/build and
**26 installed Chrome checks**. Shared From/To processing includes the entire
browser-local day, including final microseconds and DST boundaries. No time widgets
or new migration; earlier checkpoints below are historical.

Latest browser-timezone correction: **1,173 full PostgreSQL tests passed in 522.38
seconds**, **331 frontend tests**, lint, TypeScript/build and **25 Chrome checks**.
Migration 0023 populated round trip/drift passed. Covers fixed expiry, author-zone
validation, metadata preservation/clearing, DST, half-hour offsets and cross-browser
timezone viewing. This supersedes the full checkpoint below; not just a focused run.

Latest manual-entry/Eastern-deadline checkpoint: **1,164 full PostgreSQL tests
passed in 538.45 seconds** (`--require-postgres -W error`), **330 frontend tests**,
lint, TypeScript/build and **24 installed Chrome checks**. Unlike the focused
follow-ups below, this is a fresh complete backend run. Earlier counts remain
historical. `pip check` passed; no new coverage percentage or load acceptance claimed.

Latest saved-note/history follow-up: **327 frontend tests**, lint, TypeScript/build,
**30 focused PostgreSQL tests**, and **21 installed Chrome checks** passed.
The full backend run below predates this follow-up; no new full-suite claim.

The remediation increment passed **1,153 full PostgreSQL backend tests**, **323
frontend tests**, lint, TypeScript and an isolated production build. Migration
0022 passed empty/populated upgrade and downgrade/upgrade checks with clean drift.
See [Phase 4 validation](PHASE4_VALIDATION.md) for commands, focused results and
delivery limits. Nineteen installed Chrome checks cover workflow UI/filters with
scoped automated accessibility checks. No new coverage/load measurement is claimed.
Older Phase 3 checkpoints elsewhere in this document remain historical, not counts
for this increment.

Later note-discovery/mixed-selection follow-up: **326 frontend tests**, lint,
TypeScript/build, **21 installed Chrome checks** and **29 focused PostgreSQL
workflow tests** passed. The earlier **1,153 full backend** result remains the
last full-suite checkpoint, not a fresh full run for these presentation changes.
