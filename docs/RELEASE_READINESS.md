# Release readiness and code review

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


25 October multi-user follow-up: individual Findings Workflow/Archive/Undo are
disabled whenever selection exists; Clear selection restores them. Settings merge
uses a locked fresh Organization; profile mutations and consent creation/updates
are serialized per organization. Frontend 367 tests, lint and production builds
passed; 35 Chrome checks passed (`phase3_browser_ea1eb15a3a45`), plus live-demo
cancel-only smoke. Backend: **1,187 full tests passed in 563.87s**, then final
**7 focused concurrency tests passed in 4.34s** (four cases added after full-run
collection; overlapping results, not additive). PostgreSQL required, warnings as
errors. See [multi-user contract and remaining audit
boundaries](MULTIUSER_CONCURRENCY.md); this is not universal concurrency acceptance.


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


25 October unified Findings actions: **365 frontend tests, 67 focused PostgreSQL
archive/workflow tests and 35 installed Chrome checks**, lint/build passed.
Removed selection mode; shared selection supports workflow up to 100 and all-manual
archive up to 500. Sticky row Actions group Workflow/Archive; confirmations freeze
targets and cross-page eligibility is retained. No backend/schema/inference changes.
Earlier full backend and document-specific browser evidence remains historical.

25 October document-preview follow-up: **362 frontend tests, 6 focused PostgreSQL
document tests, 6 grouped Chrome checks across viewer/admin/platform**, lint and
build passed. Preview now expands below its row with local loading/error/retry,
single-version toggle, keyboard scrolling/focus restoration and mobile containment.
Chrome fixtures use intercepted responses; an additional live-demo saved-preview
smoke passed without writes. No backend/schema, consent or inference changes.
Earlier full backend and workflow Chrome evidence remains historical, not rerun here.

24 October notification/Settings follow-up: **357 frontend tests, 45 focused
PostgreSQL archive tests, 34 installed Chrome checks**, lint and build passed.
Routine successful job notices auto-dismiss after 10 visible seconds, with
interaction/visibility pauses and persisted background dismissal; failures and
warnings remain manual. Settings uses full content width with mobile wrapping.
No backend behavior/schema or production approval changed; earlier full backend
evidence remains historical rather than a new full run.

24 October Finding-ID traceability: **344 frontend tests, 39 focused PostgreSQL
tests, 32 installed Chrome checks**, lint and TypeScript/build passed. Expand/copy
Finding IDs, exact-ID search, report/workflow/Activity links and organization-access
resolution are implemented. No new migration, inference or production sign-off.
The earlier full 1,182-test backend run is historical, not rerun for this increment.

24 October assignee-search follow-up: **337 frontend tests, 38 focused PostgreSQL
tests, 28 installed Chrome checks**, lint and build passed. Assignee search now
matches name/email only; People search retains role/status matching. No migration.
The earlier 1,182-test full backend result remains historical, not rerun here.

Latest assignee-history/search correction: **337 frontend tests, 37 focused
PostgreSQL integration tests and 28 installed Chrome checks passed**, plus lint
and production build. Unchanged assignees/raw user IDs are omitted from history;
search, empty results, retained selection and explicit-save behavior are covered.
The 37-test run is focused, not a replacement for the earlier full 1,182-test run.

Latest compact-time/full-day-filter checkpoint: **1,182 full PostgreSQL tests,
334 frontend tests and 26 Chrome checks passed**, plus lint, TypeScript/build.
Shared date-only filters cover complete browser-local days without new controls;
zone/expiry metadata stays stored but detailed zone labels are removed from normal
UI. No migration or production/live-AI approval. Earlier checkpoints retain their scopes.

Latest browser-timezone correction: **1,173 full PostgreSQL backend tests, 331
frontend tests and 25 Chrome checks passed**, plus lint, TypeScript/build and
populated migration 0023 round trips. New deadlines require the author's IANA
timezone and retain a fixed expiry; Eastern is a legacy backfill rule only.
Prior counts below are historical. Reconciliation/suppression remains separately
approved but not yet implemented; no production/live-AI release is implied.

Latest manual-entry/Eastern-deadline checkpoint (23 October): **1,164 full
PostgreSQL backend tests, 330 frontend tests and 24 installed Chrome checks passed**;
lint, TypeScript and production build passed. This supersedes the full 1,153-test
checkpoint below. Imported-finding archive/reconciliation remains design only,
and mandatory rationale is unchanged by user choice. No production/live-AI release.

Latest saved-note/history follow-up: **327 frontend tests, 30 focused PostgreSQL
tests and 21 Chrome checks passed**, plus lint, TypeScript and production build.
No new full backend run is claimed; the checkpoints below retain their scopes.

Phase 4 remediation checkpoint (23 October): **1,153 full PostgreSQL backend tests,
323 frontend tests, lint, TypeScript and isolated production build passed**.
Migration 0022 empty/populated round trips and drift checks passed on the disposable
test target only. [Scope and evidence](PHASE4_VALIDATION.md). Remediation UI/filter
delivery passed 19 installed Chrome checks and scoped automated accessibility checks;
other Phase 4 work remains pending. No Phase 4 closure or
production/live-provider approval is implied. Historical Phase 3 checkpoints below
remain unchanged.

Presentation follow-up: **326 frontend tests**, lint, TypeScript, isolated build,
**21 installed Chrome checks** and **29 focused PostgreSQL backend tests** passed.
The 1,153-test full backend run above is earlier evidence, not rerun for this
frontend-only follow-up. Saved-note navigation and mixed-selection risk-date
guidance are improved; mandatory-rationale policy remains unchanged. Approved
demo schema rollout to 0022 is separate from test round trips; normal schema untouched.

## Latest implementation checkpoint — 23 October 2026

Check-in review added a prompt-marker preservation fix/regression;130 focused
tests passed afterward. The full1,115-test result below is the earlier checkpoint,
not a fresh full run of the marker fix. [Verification guide](EVIDENCE_USER_VERIFICATION.md).

Evidence-aware contract implemented **opt-in/off by default**: seven coverage
profiles, trusted operator qualification, explicit unscored states, server overall
aggregation, APIs, UI and exports. **1,115 full PostgreSQL backend tests**, **312
frontend tests**, lint/TypeScript/build and **18 new-mode +17 legacy Chrome checks**
passed; test DB restore/round-trip/drift clean. [Final verification](EVIDENCE_ASSESSMENT_VALIDATION.md).
No new coverage measurement. Local milestone remains closed; scoped risk exception
unchanged. New policy adoption is an operator decision, not live-provider acceptance.
No real inference, paid calls, qualification file installation or release sign-off.

## Approved local milestone — 23 October 2026

**Local-testing milestone closed by explicit user approval**, with a scoped,
temporary development-tool risk exception. Controls and22November2026 review/expiry:
[decision record](LOCAL_TESTING_MILESTONE.md). No production/live-AI release approval,
no inference/paid calls. Insufficient-evidence scoring remains separate; Docker
and report-date UI remain Future. Historical open-advisory statements below are
superseded only for this local scope, not a fix or production risk acceptance.

## Earlier presentation follow-up — 23 October 2026

Presentation-only improvements are complete; scores, schemas and saved snapshots
are unchanged. [Implementation evidence](REPORT_SCORING_UI_REVIEW.md): **307 frontend
tests**, **71 focused backend tests** (43 unit/export, 20 PostgreSQL integration,
8 browser-fixture), lint/TypeScript/production build and **17 native Chrome checks**
passed. Test database restored to 0021 with clean drift check; browser schema cleaned.
No fresh full backend run or coverage measurement: the 1,035-test checkpoint below
remains the latest full run. No inference/paid calls. Insufficient-evidence scoring
remains a separate design decision; check-in is not release approval.

Reviewed: 22 October 2026. Current status authority; historical evaluations and
design proposals are not release approval. **Phase 3 is not release-ready.**
The synthetic browser demo remains usable with real inference disabled.

Current closure authority: [Phase 3 closure checklist](PHASE3_CLOSURE.md).
Explicit prompt/context budgets are implemented under **audit-evidence-v3**;
the original P2 prompt-size finding below is remediated, not still unbuilt.
Technical/mock acceptance and the local exception do not replace genuine provider/
model/pricing/quality acceptance or explicit production/live-AI sign-off.
Budget implementation verification: **1,035 full-run PostgreSQL tests passed**,
zero skips/failures/errors; 94.24% backend lines and 85.53% branches. Frontend
300 tests, lint/TypeScript and production build passed. Prior run counts below
are historical; see the closure record for current evidence.
The v3 native/mock Chrome checklist passed 16/16 after that suite; migration
round-trip and drift checks passed with the test database restored to 0021.

Expanded verification: [testing strategy and measured coverage](TESTING.md)
documents mandatory PostgreSQL acceptance mode, no-real-HTTP test guards and
coverage including unimported application files. Frontend now has 300 passing
tests, 91.98% lines and 84.85% branches. Earlier dated counts below are historical,
not the newest run. Backend: 1,005 full-run tests plus 19 final focused tests,
including 11 added afterwards; zero skips/errors/failures. Cumulative coverage
94.19% lines/85.34% branches. Fresh Chrome Phase 2e/3 checks and the PostgreSQL
migration round-trip passed; exact scope/results are in [validation](BACKEND_VALIDATION.md).

## User-approved scope adjustment — 22 October 2026

Reporting-period browser fields are deferred enhancement work, not a release
blocker. Docker deployment and container build/startup/cache persistence/recovery
validation move to [Future phase](../PLAN.md#future-phase--deferred-delivery).
Current acceptance is native-local and mocked-provider only; no container/cloud
deployment or genuine AI/provider acceptance is claimed.

## Native browser acceptance follow-up

[Phase 3 acceptance](PHASE3_ACCEPTANCE.md): **16 real-stack Chrome checks passed**
with mocked inference/embeddings, zero page errors and disposable schema cleanup.
Additional intercepted-API UI checks passed for 3 document roles and 2 report-dialog
viewports with zero scoped Axe AA violations. Native browser checklist is complete
for this explicit scope; production, semantic/model quality and live-provider
acceptance are not implied. Related guard tests: 8 passed.

## Remediation follow-up — 22 October 2026

The user subsequently authorized fixes. Retry authorization now refreshes the
report from PostgreSQL before every application-level provider attempt and rejects
missing, foreign-organization, cancelled or non-running jobs before reservation.
Publication guards remain. An already-issued request cannot be aborted, and a
cancellation racing after the check can still overlap that request.

Next and eslint-config-next are pinned to 16.4.2. Lockfile updates install sharp
0.35.5, source-map-js 1.2.2, Vitest 5.0.5 and Vite 8.3.5. An explicit
postcss-selector-parser 7.1.7 override removes the older build-time parser; lint,
component tests and the complete production build validate current compatibility.
`npm audit --omit=dev --json` now exits successfully with **zero vulnerabilities**.

The unrestricted audit still exits unsuccessfully: **seven high-severity
development-only entries**, rooted in braces 3.0.3 and propagated through
chokidar/micromatch/fast-glob/Tailwind/Next lint tooling. This is one root advisory,
not seven independent exploits. The [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
lists no patched release; registry latest is 3.0.3. No runtime exposure was
established: these tools process repository-controlled build/lint patterns.
Do not process untrusted repositories/glob configuration with these tools or
expose development servers. Full dependency clearance remains open pending an
upstream patch or separately reviewed tooling migration; no risk acceptance is
implied. Forced upgrades/downgrades do not establish a clean supported toolchain.

Frontend verification: **274 tests**, lint, TypeScript no-emit and production
build passed. The demo was stopped for installation/build, then rebuilt/restarted
with existing accounts/data and real inference disabled. Chrome 155.0.8059.85
login smoke: HTTP 200, required controls visible, zero page errors. This is not
complete Phase 3 browser acceptance. Backend: **987 passed in 526.62s** with
warnings as errors. After expanding/strengthening provider regressions, the final
focused run passed **24 tests in 16.62s**, including two new direct-Anthropic cases
not collected by the preceding full run. No live inference. See
[validation](BACKEND_VALIDATION.md) for exact scope and test database restoration.
After all tests, disposable `auditmind_test.public` is restored to revision 0021
with 29 tables; Alembic drift check clean and repeated upgrade a no-op.

## Original review findings (remediation status above)

| Priority | Evidence | Required action |
| --- | --- | --- |
| P1 | Production dependency audit finds three high-severity packages: Next 16.3.6, sharp 0.35.4, source-map-js 1.2.1. Package exposure is not a demonstrated application exploit. | Select compatible patched versions, update lockfile, rerun audit/tests/lint/build and Chrome regression. |
| P1 | `report_ai_service.generate_ai_audit_snapshot`'s `authorize_attempt` checks target/consent, not live cancellation/status. A mock-only reproduction authorized another attempt after cancellation and failed status. Worker publication checks prevent saving, not another potentially billable retry. | Reload and verify job organization, running status and cancellation before every attempt/reservation. Test timeout → cancel → retry: no second request/reservation. An issued request can still finish. |
| P2 | `GenerateReportModal` submits only title/frameworks; API date filtering exists but users cannot select a period. | Add accessible date controls, propagation and regression tests. Dates select active findings created within inclusive UTC dates; inventory is current, not historical. |
| P2 | Direct Anthropic `estimate_cost_usd` matches model families to legacy fixed rates, rather than verified model-specific prices. | Verify configured model/prices before live use. Estimated ledger limits are not authoritative billing ceilings. OpenRouter separately uses explicit caps and reported costs. |
| P2 hardening | Finding sample count is bounded but description bytes/tokens are not explicitly bounded before prompt construction. | Define deterministic context budgets and recorded omissions; test oversized input. No oversized-input exploit was performed. |

Sources: [Next advisory](https://github.com/advisories/GHSA-cjq9-62q9-8jv4),
[sharp advisory](https://github.com/advisories/GHSA-wq5f-xc86-pv6w),
[source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
Three is the vulnerable-package count, not total advisory count. No dependency
upgrade or production-code fix was made under this review/documentation request.

Applicability qualification: `frontend/next.config.ts` has no `images.remotePatterns`;
the cited Next SSRF advisory says that configuration is unaffected. Other Next
advisories in the audit still need individual review. The sharp advisory concerns
certain glibc Linux runtime conditions, not a demonstrated Windows-demo exploit.
No untrusted indexed-source-map processing path was established. Treat this as a
dependency release-gate failure requiring patches or documented applicability,
not three proven exploitable application vulnerabilities. These advisory fixes
start at Next 16.3.8, sharp 0.35.5 and source-map-js 1.2.2 respectively; a final
upgrade must resolve all applicable advisories, not just these three examples.

Source locations: [retry authorization](../backend/app/services/report_ai_service.py),
[provider attempts/accounting](../backend/app/services/claude_service.py),
[worker publication guard](../backend/app/services/report_service.py),
[report dialog](../frontend/src/components/GenerateReportModal.tsx).

## Coverage and gates

| Area | Status |
| --- | --- |
| Scoring | Deterministic dashboard/API; separate AI report scores and captured baseline; shared 80/60/40 tiers implemented. |
| Documents/RAG | Versioned ingestion, embedding, tenant filtering, citations and worker lifecycle implemented/tested. Installed NIST baseline is not equivalent to full licensed CIS/ISO texts. |
| Evidence/remediation | Repeatable-read capture, provenance, UUID allowlists, model-estimated confidence and snapshot exports implemented/tested. Confidence is not calibrated probability. |
| Operations | Durable quotas/usage ledger, keyed organization idempotency, retention, failure tests and embedding/cache packaging implemented. Cancellation retry authorization repaired; verification recorded in follow-up. |
| Migrations | Head 0021. Restore/check disposable test schema after suite; ordinary/demo targets require separate preflight before any authorized migration. |
| Providers | Direct Anthropic and optional Claude-through-OpenRouter adapters exist. OpenRouter is mock-tested, disabled by default. No genuine completed Claude report acceptance established by this review. |
| Browser | Phase 3 native/mock checklist passed: 16 real-stack Chrome checks, 3 intercepted document roles and 2 report-dialog viewports. See dedicated acceptance record for limits. |
| Deployment | Docker/container build/startup, cache persistence and restart/recovery deferred to Future by user. `/health` remains liveness, not dependency readiness. |
| Release | Production audit clean; cancellation repaired; scoped native/mock Chrome checklist passed. Development-tool audit disposition, other documented hardening/readiness and explicit sign-off remain open. Date UI and Docker validation are Future scope. |

Phase 3a local generation is separately delivered and paused: hardware/Ollama/model
experiments exist, but no model/local report adapter was accepted. BGE-M3 embeds;
it does not generate reports. Phase 3b remains a proposal. Native Qualys expansion
and more free-provider experiments are deferred. Generated remediation and
HTML/PDF snapshots remain core Phase 3; future workflow refinements are Phase 4.

## Original review verification (before authorized fixes)

- Frontend: 274 tests passed, 24 files; lint passed. Non-failing React `act(...)`
  diagnostics remain; this is not a warning-free claim.
- Python `pip check` passed; dependency consistency is not a security audit.
- Production frontend dependency audit failed: three high-severity packages.
- Full backend: **979 passed in 503.35s**, warnings treated as errors.
  TypeScript no-emit passed. Disposable test database restored to 0021;
  Alembic metadata check clean. Details: [backend validation](BACKEND_VALIDATION.md).
- Offline evaluation tooling: 15 self-tests passed (10 benchmark, 1 local CLI,
  4 free-probe safety); no model execution or inference HTTP requests.
- No live inference, paid call, ordinary/demo migration or production penetration test.
- No fresh in-place frontend build against the running demo during this review;
  previous build/browser evidence remains historical, not a fresh gate.

## Documentation scope

Read the [plan](../PLAN.md), [Phase 3 checklist](../Phase3.md),
[operations](PHASE3_OPERATIONS.md) and [manual](USER_MANUAL.md) with this status.
Scoring/UI flows describe runtime boundaries. Architecture, Blueprint, data model
and connector specifications contain design context; code/migrations govern exact
routes, columns and permissions. Original standalone AI/connector examples are not
proof of runtime support. Server provider configuration is not a browser setting.

Local-model, OpenRouter/free-provider, Phase 2e and database-performance records
retain original dates/results. Original CoPilot reviews, MasterPrompt and prompt
examples remain historical/design inputs. UI conventions and frontend agent
instructions remain normative in their scope. Vendored NIST license is unchanged;
its upstream-relative links are not local product documentation requirements.

Original review set: 33 Markdown files; the Phase 3 acceptance record was added
subsequently. Current
guides/roadmap were synchronized; dated experiments/reviews received explicit
historical-status links without altering results. Frontend agent instructions and
vendored legal text were intentionally left unchanged. Local link checks found
only the known upstream-relative NIST license `CONTRIBUTING.md` reference.
