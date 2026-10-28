# Testing strategy and measured coverage

## Evidence-scoring pilot commands

After the isolated production build described in
[Phase 4 validation](PHASE4_VALIDATION.md), run from the repository root:

- `node scripts/browser-evidence-acceptance.cjs`: 11 opt-in/permission/partial/
  invalidation/rollback scenarios (hosted Ubuntu verified at `898b309`).
- `node scripts/browser-evidence-acceptance.cjs --pilot`: additionally exercises
  all seven profile approvals, genuine zero, weighted complete aggregation, real
  expiry, re-review, incompatible scopes and canonical native date input at exact
  minutes/nonzero seconds. This is the 17-scenario CI correctness variant.
- `node scripts/browser-evidence-acceptance.cjs --pilot --load`: also measures a
  bounded 60-second, six-account/two-organization mixed-read workload with four
  waves of paired worker evaluations (18 scenarios). Local opt-in only; no production-load claim.

All variants share a unique, guarded local `auditmind_test` schema and use real
Chrome/API/worker/PostgreSQL with external HTTP blocked. They restore synthetic
settings off and remove their fixture; artifacts remain under
`temp/testing/evidence-review`. Ports 3014/8012 must be free. Do not overlap
public-schema backend tests or performance benchmarks. See
[the latest dated results](PHASE4_VALIDATION.md) rather than adding historical counts.

## Latest drag/drop regression — 27 October 2026

**428 frontend tests passed** (70.39s), lint and isolated build/TypeScript passed.
File-only capture guard and page-wide queue regressions cover native-input/text
preservation, listener cleanup and no double delivery. Chrome uses native OS-file
drag payloads outside the upload button and checks URL/queue behavior. See latest
validation for final evidence. No backend change/full rerun: 1,281 remains the
earlier full policy run, not a new count for this frontend fix.
Final **68 Chrome check executions passed** (`phase3_browser_3052352df4b8`), including
real native OS-file drag data (two filenames), app URL preservation and single queue
delivery. First attempt raced page hydration; explicit visible-control waits fixed
the acceptance timing. No browser page errors or AI usage.

## Latest exact-file policy increment — 27 October 2026

Fresh **425 frontend tests passed** (73.87s), lint and isolated build/TypeScript
passed. PostgreSQL-focused passes: 33 policy/settings tests and 101 broader
import/archive/worker/activity regressions. Policy tests cover all shared import
endpoints, concurrent identical admission, permissions, organization isolation,
reset/validation, in-flight protection and failed/archived attempts. Frontend
regressions verify single/batch skip feedback and no matched-scan tracking.
See [latest validation](PHASE4_VALIDATION.md) for the full backend and browser
final results; counts below are earlier checkpoints and must not be added.
Fresh **1,281 full PostgreSQL tests passed** (691.72s, required PostgreSQL,
warnings as errors), including migration checks. Test DB restored to 0028,
31 tables, repeated upgrade/no drift passed. This is the new full backend run,
not a sum of the focused results or the older 1,268-test baseline.
Final **67 Chrome executions passed** (`phase3_browser_2b4dd2510d0c`) against real
isolated PostgreSQL/API/worker. Initial hidden-label selector failure was fixed by
targeting Activity table rows; final full rerun passed, with no browser errors or
AI usage. Ask/Skip/Reimport/reset and skip audit visibility are exercised.

## Latest grouped upload-decision increment — 27 October 2026

New mixed-queue regressions verify duplicates never block later ready files,
explicit selected skip/reimport, no automatic confirmation, no accepted-file
resubmission and failure-only retry. Existing duplicate tests now exercise the
grouped single-file path as well. Chrome adds real duplicate/new-file submission,
selected skip/reimport and scoped accessibility through real API/PostgreSQL.
See [latest validation](PHASE4_VALIDATION.md) for completed-run counts/artifacts.
No backend/schema changes or fresh full backend run; no demo/worker restart.
The final full frontend suite passed **422 tests** (80.90s, two workers); the
62-test focused post-review pass overlaps this total. Lint and isolated build/
TypeScript passed. **64 Chrome check executions passed** on the final build
(`phase3_browser_63afc981a1bf`), including the real grouped-duplicate scenario.
Earlier 420/417 counts below are historical checkpoints.

## Latest upload-dialog presentation follow-up

**420 frontend tests passed** (82.77s, two workers), **63 Chrome executions passed**
(`phase3_browser_eb4fecbe009f`), lint and isolated production
build/TypeScript passed. New regressions cover idle dialog cancellation without
submission, compact grouped progress and automatic failure expansion. See
[validation evidence](PHASE4_VALIDATION.md) for Chrome layout/accessibility checks.
No backend code/schema change or fresh full backend run. Demo/worker were not
restarted while large imports ran; the new presentation is not yet activated.

## Latest shared batch-upload increment — 26 October 2026

**417 frontend tests passed** (25.00s), including four new queue regressions;
lint/TypeScript and isolated/demo builds passed. **61 Chrome check executions
passed**, including one-click multi-file submission against real PostgreSQL/API/
worker (`phase3_browser_2cf4a9d36ca5`). See the latest
[validation record](PHASE4_VALIDATION.md) for browser artifacts and scope.
No backend code/schema changed; the **1,268 backend tests** below are the previous
full run, not rerun or added to these results. No inference calls.

## Final combined-tree check-in gate — 26 October 2026

**1,268 full PostgreSQL tests passed** (668.14s, required PostgreSQL, warnings as
errors), **413 frontend tests passed** (25.09s final rerun), lint/TypeScript/build
and **61 Chrome executions** passed (`phase3_browser_526fedeba757`). Real migration
upgrade/rollback/no-op/drift included through 0028. npm/core-dev/optional-embedding
audits are clean; pip check, high-severity Bandit and tracked-file/whitespace
guards passed. Low/medium static findings remain tracked, not waived. Preliminary
interrupted backend run is not counted. Older focused/full results below are
historical, not additive. [Authoritative local/hosted evidence](PHASE4_VALIDATION.md).

## Historical implementation checkpoints

Password visibility: **411 frontend tests** (24.16s), lint/build/TypeScript passed.
New shared-control tests cover keyboard/no-submit behavior, per-field masking,
remounts, metadata, disabled state and temporary handover copy/reset; existing
auth/change-password/People/platform regressions pass. Backend unchanged; earlier
focused/full backend counts are not reruns. **61 Chrome executions passed** through
real test API/PostgreSQL, including synthetic reset/change-password and Axe. Final
13 focused People tests overlap the full frontend suite; do not add the counts.
[Browser evidence](PHASE4_VALIDATION.md).

Platform product-logo sizing: **406 frontend tests** (24.69s), lint/build/TypeScript,
**29 focused PostgreSQL checks** (25.59s, including two migration tests) and **25
separate platform API regressions** (46.95s) passed, warnings as errors. The 54
backend checks cover disjoint files; no new full-suite run. No migration beyond
0028. **55 Chrome check executions passed**, including platform permissions,
cross-user sizing, conflicts and Axe. [Current browser evidence](PHASE4_VALIDATION.md).

Company-name typography follow-up: **399 frontend tests** (37.68s), lint/build/
TypeScript and **28 PostgreSQL tests** (34.73s, warnings as errors) passed: 26
focused branding/logo/settings tests plus two migration checks at 0028. Earlier
full backend counts are not reruns. **52 Chrome check executions passed**, including
computed font sizes, persistence and stale edits. [Current evidence](PHASE4_VALIDATION.md).

Configurable organization-logo size: **395 frontend tests** (23.96s), lint/build/
TypeScript and **27 PostgreSQL tests** (34.38s, warnings as errors) passed. Backend
scope is 25 focused branding/logo/settings checks plus two migration tests at
0027, not a new full-suite run. **50 Chrome check executions passed**, including
size persistence/permissions, mobile layout and two-tab conflicts.
[Current browser evidence](PHASE4_VALIDATION.md).

Header preference/sizing: **391 frontend tests** (24.65s), lint/build/TypeScript,
**24 focused PostgreSQL backend tests** (19.78s), **two migration tests** (2.65s)
and **48 Chrome check executions** passed. Migration round-trip/no-op/drift at
0026 passed. Focused backend checks are not a new full-suite run; prior 1,260
results remain historical. [Evidence](PHASE4_VALIDATION.md).

Signed-in branding follow-up: **387 frontend tests** (28.95s), lint/build/TypeScript
and **47 Chrome check executions** passed. Product branding appears once in the
sidebar, while the header retains organization identity/company branding. Auth
presentation is unchanged. Backend unchanged; earlier full PostgreSQL evidence
is not a rerun. [Scope/artifact](PHASE4_VALIDATION.md).

Authentication presentation follow-up: **385 frontend tests** (21.99s), lint/
build/TypeScript and **47 Chrome check executions** passed, with full-page Axe,
keyboard and desktop/mobile auth screenshots. Authentication groups repeat for
admin contexts; open signup uses a presentation-only fixture. Backend unchanged;
prior full PostgreSQL evidence is not a rerun. [Scope/artifact](PHASE4_VALIDATION.md).

Product-asset follow-up: **383 frontend tests** (32.88s), lint/build/TypeScript
and **43 installed-Chrome checks** passed. New checks verify the fixed product
SVG across sign-in/sidebar/header and the independent favicon. Backend unchanged;
the 1,260-test result below is earlier evidence, not rerun for this UI-only change.
[Scope and artifact](PHASE4_VALIDATION.md).

Latest local logo increment: **1,260 full PostgreSQL tests** (629.34s, warnings
as errors), **382 frontend tests** (26.05s), lint/TypeScript/build and **42 Chrome
checks** passed. Migration round-trip/drift passed at 0025. Focused counts overlap;
interrupted runs are not counted. Hosted c008efc below is the preceding baseline,
not execution of this uncommitted feature. [Evidence](PHASE4_VALIDATION.md).

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
## Background evaluation / opt-in Dashboard checks (28 October 2026)

Current contract: [durable jobs and safe invalidation](BACKGROUND_EVIDENCE_EVALUATION.md).
Run PostgreSQL suites with `--require-postgres -W error`; new integration coverage
is in `test_background_evidence.py`, lifecycle checks in `test_platform_api.py`,
and populated migration 0031 downgrade/upgrade/drift in `test_migrations.py`.
All default-off baseline tests remain required. Never overlap a public-schema
backend suite with an isolated browser fixture.

Installed Chrome: `node scripts/browser-evidence-acceptance.cjs` starts a real worker
in an isolated synthetic schema and tests navigation-resume, partial scoring after
explicit admin opt-in, review/invalidation/permissions and mode rollback. Full
regression: `node scripts/browser-finding-workflow.cjs`. Build the isolated frontend
first using the procedure in [validation](PHASE4_VALIDATION.md).
The browser CI job now runs these two suites sequentially and retains both artifact
folders. Hosted execution passed for `5ce836b` in
[run 40749424003](https://github.com/shalisarakkal/AuditMind/actions/runs/40749424003).

`node scripts/browser-evidence-http.cjs` now measures durable worker jobs against
the idle synthetic SA01 demo: 202 acknowledgment, completion/records, navigation,
two-viewer job deduplication, cheap state-read latency and real cancellation. Use
`--cancel-only` for the latter. It creates/removes its own temporary viewers,
preserves inventory and keeps scoring off. Do not run alongside benchmarks/imports
or full backend tests. Previous stream-protocol timings remain historical.

Final backend regression: **1,366 passed in 849.31 s**, PostgreSQL required,
warnings as errors, zero failures/errors/skips. Test DB restored to 0031 (35 tables),
repeated upgrade no-op and clean drift. Frontend: 465 tests, lint/TypeScript and
both isolated/normal production builds passed; dedicated Chrome seven checks,
full browser 71 checks and full-size worker five measurement checks passed.
The first full-run legacy metrics assertion and final short-batch progress defect
were fixed and included in the green rerun, not waived. Results/artifact paths are in
[the current validation entry](PHASE4_VALIDATION.md). All four hosted Linux jobs
succeeded for the pushed implementation `5ce836ba6dd00f026eb5490f37da8b4e8f249a27`
in [run 40749424003](https://github.com/shalisarakkal/AuditMind/actions/runs/40749424003).
The earlier prerequisite run for `c7ee354` is historical, not the evidence for this feature.

## Evidence qualification backend checkpoints (27 October 2026)

Backend registry/review stages: 1,327 full PostgreSQL tests passed, followed by
55 focused tests after final review hardening (overlapping, not additive).
71 installed-Chrome regression checks passed with new default-off/empty-coverage
API guards (`phase3_browser_e493ebae1bcc`). Reviewer UI and Dashboard integration
are not implemented or enabled; no fresh frontend-unit count is claimed.
Migration round trips/drift, high-severity Bandit and secret/whitespace checks pass.
Disposable test DB restored to 0030; demo unchanged. Hosted ceef079 results are
historical and do not validate this uncommitted/unpushed backend work.

# Empty-dashboard regression follow-up (27 October 2026)

Latest increment: 434 frontend tests passed, ESLint and production builds passed.
61 focused PostgreSQL scoring/dashboard/archive tests passed; this includes the
initial 9 dashboard tests and is not a replacement for the historical full suite.
Chrome: 70 checks passed (`phase3_browser_61c079037c36`).
The API/UI now distinguish completely empty active organizations from numeric
scores. Asset-only/partial-evidence baseline scoring is deliberately unchanged.
# Evidence reviewer preview validation (27 October 2026)

Latest full checkpoint (28 October): **1,335 PostgreSQL tests passed in 753.92 s**
with `--require-postgres -W error`, zero skips/failures/errors. Includes the two
new real-ASGI disconnect cleanup regressions. Disposable local test DB restored
to head 0030, 33 public tables, clean Alembic drift. **456 frontend tests**, lint,
TypeScript/isolated build, scoped high-severity Bandit, dependency consistency and
tracked/new task-file secret checks pass. This replaces earlier full counts for
the current local work; it is not evidence of hosted CI for an unpushed SHA.
The subsequent approved local check-in separates backend, Settings, presentation
and acceptance/docs scopes; see [commit record](PHASE4_VALIDATION.md). No push or
new hosted CI execution is included.

28 October real-service follow-up: authenticated Chrome/Next/API scans complete
6,374,205 SA01 records in 116.524/110.537 s sequentially and 135.653/133.253 s
for simultaneous viewers. Fingerprints/counts agree; these are uncontrolled
local-cache measurements. In-flight cancellation exposed an idle transaction leak;
shielded iterator cleanup and two PostgreSQL/ASGI regression cases fix it.
Post-fix real Cancel restores the UI promptly; DB cleanup waits for the current
fetch (~27.8 s with polling), not an immediate statement kill.

Six focused Chrome checks pass in an isolated 100,000-asset schema: two independent
admins' concurrent review (200/409), retained edits/reload, permissions, partial
eligibility, concurrent inventory publication/snapshot invalidation, revoke/rebind
and material conflict. No ordinary inventory mutation, AI usage or scoring
enablement. Repeat with `node scripts/browser-evidence-acceptance.cjs` after the
isolated build, sequentially with backend suites. Performance/cancellation runner:
`node scripts/browser-evidence-http.cjs` (or `--cancel-only`) against the idle demo.
Artifacts, commands and limitations:
[Phase 4 validation](PHASE4_VALIDATION.md),
[performance](EVIDENCE_EVALUATION_PERFORMANCE.md).
Frontend recheck: 456 tests, lint, TypeScript and isolated production build pass;
high-severity Bandit and tracked/new task-file secret guards pass.

28 October contextual progress: 456 frontend tests, lint/build and 12 focused
Chrome checks passed. Includes operation-local status/errors, correct DOM
ownership, held-stream cancellation while editing is disabled and retained
evidence-dialog accessibility. No backend logic changed in this UI increment.

Application-confirmation follow-up: 454 frontend tests, lint/build and 11 focused
Chrome checks passed. Includes app-modal Axe scan, Escape/focus restoration,
confirmed discard and saved-version action confirmation. Earlier UI counts
below are historical, not additive or replacements for full backend acceptance.

Latest scope/reload clarification: 451 frontend tests, lint/build and 10 focused
Chrome checks passed. Includes fresh version reads, dirty-form protection,
read-only no-popup reload and organization-wide evaluation independent of the
domain editor. These are focused UI results, not a new full backend run.

Later performance/progress increment: 447 frontend tests, 49 focused PostgreSQL
qualification tests, lint/build and 9 focused Chrome checks passed. A subsequent
3-test stream follow-up overlaps those backend results. This is not a new full
backend or full browser run. [Measurement scope, protocol and limitations](EVIDENCE_EVALUATION_PERFORMANCE.md).

Frontend: 437 tests passed, lint/TypeScript and production build passed. Nine
focused installed-Chrome checks passed, including inventory-bound draft save,
incomplete approval prevention and manual eligibility evaluation. These overlap
earlier login/dashboard checks and are not additive to the historical 71-check
full browser run. No inference calls; scoring activation remains unavailable.
Walkthrough: [evidence reviewer preview](EVIDENCE_USER_VERIFICATION.md).
