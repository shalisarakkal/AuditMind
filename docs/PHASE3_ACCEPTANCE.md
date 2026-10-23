# Phase 3 native browser acceptance — 22 October 2026

## Latest presentation acceptance — 23 October 2026

**17/17 passed**, including advisory score/baseline/confidence explanations,
keyboard citation navigation, mobile/print presentation, downloads and lifecycle
permissions. Zero page errors, fixture cleanup verified. Evidence:
`temp/auditmind-demo/browser/phase3/phase3_browser_c9c0c3bdc033/`.
First attempt failed because its mock lacked citation IDs; fixture corrected to
use captured IDs, then full checklist passed. Both schemas cleaned. Chrome/API/
worker/PostgreSQL real; embeddings/inference mocked, external provider HTTP blocked.
[Scope and regressions](REPORT_SCORING_UI_REVIEW.md). Prior16-check runs below
are historical, not latest acceptance. No real-provider/release approval implied.

Latest prompt-budget/v3 rerun: **16/16 passed**, Chrome 155.0.8059.85, real isolated
PostgreSQL/API/worker with mocked embeddings/inference. Latest artifacts:
`temp/auditmind-demo/browser/phase3/phase3_browser_87c7b5fb0631/` (`result.json`,
report screenshot/HTML/PDF and logs). Zero page errors, cleanup verified.
Prior run details below remain historical. See [closure verification](PHASE3_CLOSURE.md#verification-for-this-implementation)
for full backend tests, byte limits and the updated consent target.

Result: **PASS for the native-local, mocked-provider checklist below**. This is
not genuine model-quality acceptance, production deployment certification or
automatic release sign-off. Docker deployment is user-deferred to
[Future phase](../PLAN.md#future-phase--deferred-delivery); browser reporting-date
fields are also deferred enhancements, not core release blockers.

## Environment and evidence

- Installed **Chrome 155.0.8059.85**, headless, production Next 16.4.2 frontend.
- Real FastAPI, worker, PostgreSQL/pgvector in a random, disposable
  `phase3_browser_<12 hex>` schema inside local `auditmind_test`.
- Inference and embedding implementations are **mocked**. API, authorization,
  consent, indexing, vector storage/retrieval, job transitions, output validation,
  accounting, snapshot persistence and downloads are real.
- No paid inference, model downloads, demo password resets or Docker commands.
  Existing demo/ordinary data were not changed. All disposable schemas from
  harness iterations were cleaned up; only ignored evidence artifacts remain.
- UI-only scripts separately intercept API fixtures; those passes are not
  represented as backend/worker acceptance.

Final real-stack evidence (ignored runtime artifacts):
`temp/auditmind-demo/browser/phase3/phase3_browser_ff40431384d2/result.json`,
`report.png`, `report.html`, `report.pdf`, `api.log`, `worker.log`.
Result records **16 passed checks**, **zero page errors**, `cleanedUp: true`.
Earlier harness iterations exposed selector/casing errors in the test script;
they were corrected and rerun, not counted as application passes.

## Native end-to-end checklist

| Check | Result |
| --- | --- |
| Unapproved organization cannot submit AI generation | Pass |
| Upload policy through UI; worker indexes/publishes using mocked embeddings | Pass |
| Published policy retrievable from tenant-filtered vector storage | Pass |
| Admin explicitly approves current report-processing target through UI | Pass |
| Viewer has no upload controls; real API refuses consent/report writes | Pass |
| Other organization cannot list or retrieve the policy | Pass |
| UI generation reaches worker; mock output validated, citations/provenance retained; rule baseline 100 remains separate from AI score 60 | Pass |
| Completed viewer and actual HTML/PDF browser downloads work | Pass |
| Viewer can download an authorized completed report | Pass |
| Auditor can open approved generation but cannot alter consent | Pass |
| Other organization cannot read completed report | Pass |
| Mock 429 retry succeeds through real worker/accounting | Pass |
| Malformed output yields a visible failed job with no audit snapshot | Pass |
| UI cancellation during in-flight timeout prevents another reservation/result | Pass |
| Retirement excludes future retrieval; completed snapshot remains identical | Pass |
| UI consent revocation blocks subsequent generation through real API | Pass |

Cancellation run verifies five total reservations: success 1, retry 2, invalid
output 1, cancelled 1. Real requests already issued cannot be aborted. Mock
embeddings prove lifecycle/filtering, not semantic retrieval quality. Synthetic
model output proves orchestration/validation, not assessment accuracy.

## Additional UI checks

`browser-documents-ui.cjs`: **3 role scenarios passed** (viewer, admin, platform),
including lifecycle labels, shared read-only controls, relevant forms/consent and
zero scoped main-region Axe WCAG AA violations.

`browser-report-dialog.cjs`: **2 viewport scenarios passed** (1440×900, 390×640),
including consent gating/link/retry, focus containment, Escape/focus return,
viewport fit, reachable actions, non-AI mode and zero scoped dialog Axe AA violations.
These use intercepted synthetic APIs and submit no real generation requests.
Scoped Axe passes do not imply application-wide accessibility certification.

## Reproduce

Run the native demo first (`start-demo.ps1`); it keeps real inference disabled.
From the repository root:

```powershell
node scripts/browser-documents-ui.cjs
node scripts/browser-report-dialog.cjs
node scripts/browser-phase3.cjs
```

The last script refuses an occupied fixture port 8012, creates its own synthetic
accounts, redirects only browser API transport to the isolated real backend,
and stops owned processes/drops only its validated schema in cleanup. It never
uses credentials from `SIGN_IN.txt`. Fixture guard unit tests reject broad
schemas, nonlocal hosts and non-test database targets: **8 passed**.

Related backend regressions and restored migration status are recorded in
[backend validation](BACKEND_VALIDATION.md): **54 passed in 41.93s**, warnings as
errors; fixture guard tests **8 passed**. Test public schema restored to 0021,
metadata drift clean; zero remaining Phase 3 fixture schemas verified. Current remaining release items are
tracked in [release readiness](RELEASE_READINESS.md); this checklist does not
silently accept the development-tool advisory or authorize external AI processing.
