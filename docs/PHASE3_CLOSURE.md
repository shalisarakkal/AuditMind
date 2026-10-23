# Phase 3 closure checklist

Latest post-milestone verification: **1,115 full PostgreSQL backend tests,312 frontend
tests,18 new-mode +17 legacy Chrome checks**, lint/TypeScript/build and test migration
round-trip/drift passed. [Final evidence](EVIDENCE_ASSESSMENT_VALIDATION.md). The new
evidence-aware mode is opt-in/off by default; qualification/adoption and live-model
acceptance are separate. Local milestone/risk exception remain unchanged.

Separate post-milestone work: [approved evidence-aware scoring contract](EVIDENCE_ASSESSMENT_DESIGN.md).
User approved23October2026 and authorized profiles/implementation. The new contract
is implemented opt-in, with [reviewed-coverage rules](EVIDENCE_COVERAGE_PROFILES.md).
Default and deterministic scoring/local milestone closure remain unchanged;
adoption and live-provider acceptance are separate decisions.

**23 October decision: local-testing milestone approved and closed**, with a
temporary development-tool risk exception restricted to that scope.
See [decision, controls and expiry](LOCAL_TESTING_MILESTONE.md).
Production/live-AI release remains unapproved; insufficient-evidence scoring is
separate, and Docker/report-date UI remain Future.

22 October 2026. This separates technical completion from release approval.
**No production/live-AI release sign-off is recorded.** Docker deployment and
browser date fields are user-approved [Future-phase](../PLAN.md#future-phase--deferred-delivery)
items, not core Phase 3 blockers. Phase 3a local generation remains separate and
paused; Phase 3b OpenAI generation is a proposal.

## Technical scope

| Requirement | Evidence/status |
| --- | --- |
| Deterministic dashboard/API scores; separate AI baseline | Implemented; shared tiers, snapshot and scoring regression tests. |
| Versioned documents, tenant isolation, indexing, retirement and citations | Implemented; real PostgreSQL tests and native Chrome acceptance. Official NIST content is distinct from reference-only CIS/ISO placeholders. |
| Consistent evidence capture and immutable report snapshots | Repeatable-read capture, atomic selected-source pins, UUID allowlists; PostgreSQL concurrency/evidence tests. |
| Remediation priority, rationale, confidence and asset/finding references | Implemented and schema/reference validated. Confidence is not calibrated probability. |
| Worker jobs, failures, cancellation, recovery and idempotency | Implemented; provider mocks, PostgreSQL concurrency and Chrome lifecycle tests. Cancellation cannot abort an issued request. |
| Durable quota/cost ledger, retention, HTML/PDF access controls | Implemented; persistent PostgreSQL and browser download verification. Estimates are not provider-enforced billing ceilings. |
| Explicit input/context/output budgets | Implemented in `audit-evidence-v3`; full text/schema/system byte guard, bounded finding excerpts, recorded omissions, post-selection reference validation. Current validation record below. |
| Native browser/API acceptance | Recorded in [PHASE3_ACCEPTANCE.md](PHASE3_ACCEPTANCE.md); embeddings/inference mocked, not semantic/model-quality acceptance. |
| Migration readiness on test target | Prior empty→0021→0020→0021 round-trip passed; restore/check after every DB-backed suite. Ordinary/demo targets require their own preflight before any authorized migration. |

## Budget contract

- Default complete model input limit: **65,536 UTF-8 bytes**, including rendered
  prompt, appended response schema and system text. Configurable 16,384–262,144
  via `REPORT_AI_MAX_INPUT_BYTES`. This is a byte budget, not an exact token count
  or a guarantee that every selected model supports that context window.
- Each sampled description defaults to **2,048 UTF-8 bytes** (configurable
  128–8,192 via `REPORT_AI_FINDING_TEXT_BYTES`); category/title use a 256-byte
  prefix. PostgreSQL returns bounded description text plus original byte length
  and SHA-256 from the same captured view. Source records are never overwritten.
- Prefixes preserve valid UTF-8. `text_limits` records original/included byte
  counts and original SHA-256. New source text is never substituted or summarized.
- Keep the existing severity/newest/UUID sample ordering. If total input is too
  large, omit sample tails while retaining one finding, then whole citation tails,
  then the last finding if necessary. Record omitted IDs, original candidate
  counts, sampling exclusions and the policy version `utf8-context-v1`.
- Citation content, spans and hashes are never partially clipped. Register source
  pins only after selection, within the same capture transaction. Model reference
  allowlists use only included evidence. Counts/baseline remain whole-dataset values.
- If fixed instructions/metadata cannot fit, fail before report-provider quota
  reservation or inference. RAG query embedding remains an independently
  authorized, bounded operation. Final request guard independently rechecks the
  appended schema/system text. Existing output ceiling remains **4,096 tokens**.
- `provenance.input_budget` and `sampled_findings[].text_limits` retain these facts
  in API snapshots and existing provenance viewers/HTML/PDF exports. The exact
  prompt hash continues to identify the rendered request text.
- Prompt version **audit-evidence-v3** and budget-setting hashes change consent
  and queued-job targets. Fresh organization approval is required for new AI work;
  old pinned jobs fail closed rather than rerouting. Retained reports are unchanged.

## Still required for release closure

Earlier23October presentation checkpoint: **307 frontend /71 focused backend tests,
17 Chrome checks**, lint/TypeScript/build passed; test DB restored with clean drift.
This is not a fresh full backend suite/coverage run. The full verification section
below retains22October results; see [latest evidence](REPORT_SCORING_UI_REVIEW.md).

23 October follow-up: the [scoring/confidence UI review](REPORT_SCORING_UI_REVIEW.md)
records five user-supplied manual ChatGPT responses (same GPT-6 label reported).
Structural/reference checks passed, but repeated NORMAL evidence changed four
domain tiers. This is preliminary quality evidence only; it does not close the
real provider/model/pricing gate below or authorize proposed UI/schema changes.

The user subsequently approved presentation-only changes, implemented and tested
as recorded in that review. Advisory score labels, baseline visibility, confidence
explanations and evidence references are improved without changing saved scores
or the assessment schema. Evidence-aware scoring was separate at that checkpoint;
the subsequent opt-in implementation is described above. Real provider/quality
acceptance remains open.

- [x] **Local-testing development-tool advisory disposition:** explicitly accepted
  by the user on23October, scoped controls and review/expiry22November2026 recorded
  in the decision above. Vulnerability is not fixed; no production acceptance.
- [ ] **Genuine provider/model/pricing and assessment-quality acceptance:** verify
  configured model/account access, model-specific pricing, context capacity and
  actual supported outputs. Any inference/budget requires separate approval.
  Mock reports are not evidence that real Claude produces acceptable audits.
- [x] **Local-testing milestone sign-off:** user approved closure on23October2026.
- [ ] **Production/live-AI sign-off:** not granted; provider acceptance and broader
  deployment risk disposition remain required. Local commits are not a release.

Coverage gaps and load/soak work remain visible in [TESTING.md](TESTING.md). They
must be assessed by risk, not hidden by a blanket "100% tested" statement. No
additional framework licenses, native scanner formats or local model capabilities
are implied by this milestone. No Docker deployment or external inference is
authorized by this checklist.

Current verification results: [BACKEND_VALIDATION.md](BACKEND_VALIDATION.md).

## Verification for this implementation

- Clean full run: **1,035 passed in 614.96s**, PostgreSQL required, warnings as
  errors, zero failures/errors/skips. Earlier overlapping-schema run was stopped
  and excluded, then rerun from a clean fixture state. No SQLite fallback.
- Backend line coverage **94.24%**, branch coverage **85.53%**, combined metric
  **92.59%**; context-budget module **100% lines and branches**.
- Targeted budget/export regressions: **23 passed** before the full run. Tests
  cover UTF-8 boundaries, whole-record omission, source hashes, exact request
  limits including schema/system text, no client/reservation on oversize,
  budget-target invalidation and post-selection UUID allowlists.
- PDF pagination risk independently reproduced with synthetic long provenance:
  old unsplittable rows raise `LayoutError`; row splitting renders a valid PDF.
- Frontend **300 passed**, lint/TypeScript and fresh production build passed.
  A Documents test was changed to await asynchronously loaded hash text after a
  premature assertion surfaced; application UI behavior was not changed.
- Detailed machine-readable backend evidence:
  `temp/testing/backend-budget-junit.xml`, `backend-budget-coverage.json`,
  `backend-budget-html/index.html`. Native Chrome/migration follow-up is in
  [validation](BACKEND_VALIDATION.md). No paid or real model calls.
- Final v3 native Chrome run: **16/16 passed**, Chrome 155.0.8059.85,
  `phase3_browser_87c7b5fb0631`, zero page errors and schema cleaned. Embeddings
  and inference mocked, API/worker/PostgreSQL real. Existing preview was rebuilt
  and restarted; no passwords reset.
- After all DB-backed runs, test schema restored through empty→0021→0020→0021;
  Alembic check clean, repeated upgrade a no-op, 29 tables restored and zero
  Phase 2e/3 browser schemas left. Verified test database encoding UTF8.
- Production npm audit: zero vulnerabilities. Seven known development-only
  braces entries remain subject to the explicit decision above.
