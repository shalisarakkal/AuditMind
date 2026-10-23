# Release readiness and code review

## Latest presentation follow-up — 23 October 2026

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
Technical/mock acceptance does not replace the remaining development-tool advisory
decision, genuine provider/model/pricing/quality acceptance and explicit sign-off.
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
