# Testing strategy and measured coverage

## Latest presentation regressions — 23 October 2026

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
