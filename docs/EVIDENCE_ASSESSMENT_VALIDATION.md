# Evidence-aware assessment implementation and validation

Check-in preparation follow-up: review found that an untrusted `TASK INSTRUCTIONS:`
marker could truncate the new prompt when using a first-marker split. Changed to
the final fixed instruction delimiter and added a title/finding/source-marker
preservation regression. **130 focused PostgreSQL-required regressions passed**,
warnings as errors, after that narrow fix; test DB restored with clean drift.
The1,115-test full run below precedes this fix; a1,116-test full rerun is not claimed.
New-mode native Chrome rerun after this fix: **18/18 passed**, zero page errors,
cleanup verified, evidence `temp/auditmind-demo/browser/phase3/phase3_browser_50059684831c/`.
See [user verification instructions](EVIDENCE_USER_VERIFICATION.md).

23 October 2026. Implements the [approved contract](EVIDENCE_ASSESSMENT_DESIGN.md)
with seven [coverage profiles and qualification rules](EVIDENCE_COVERAGE_PROFILES.md).
This is post-local-milestone implementation, not production/live-AI acceptance.

## Delivered scope

- New provider contract (`EvidenceAssessment`) forbids server-owned fields.
  Each domain explicitly states sufficient/limited/insufficient/conflicting evidence,
  reason and references. Strict score/tier invariants;0–10 distinct actions,
  reference allowlists, non-null bounded confidence; exact duplicate actions rejected.
- New server snapshot schema3 derives overall score/status. Only all-seven-sufficient
  reports score overall; fixed20/15/15/15/15/10/10 weights, integer half-up rounding,
  shared80/60/40 tiers. Partial means successful completion with null overall score/
  tier, not a failed job or zero. Deterministic baseline remains separate.
- Sufficiency needs operator-reviewed, scoped and source-hash-bound objective
  coverage.90day recency/validity policy; wrong organization, source exclusion,
  clipping, changed hashes and stale observations fail closed. Guidance-only
  references cannot establish limited/conflicting organizational observations.
  Budget omissions revalidate qualification before reporting-provider I/O.
- Policy/profile/aggregation and exact qualification-pack bytes participate in
  consent/queued-target identity. Switching mode or pack needs fresh approval.
- APIs project/filter assessment status, sort null scores last both ways, and keep
  numeric score search from treating null as zero. UI shows evidence reasons and
  references, null-score partial state and explicit completeness filter. HTML/PDF
  include status/reasons without fabricated numeric tiers; unsupported future
  versions show an explicit notice rather than guessed scores.
- Retained schema1/2 and rule-based snapshots remain readable without rewriting.
  No DDL migration introduced; persisted JSONB supports both contracts.

## Rollout boundary

`REPORT_EVIDENCE_V3_ENABLED` defaults false. No `.env` credentials, consent or
ordinary/demo reports were altered. The new mode was exercised only in isolated
mocked tests, not enabled in the normal demo. Qualification file defaults blank;
therefore no domain can claim sufficient coverage on that path. The file workflow
is a privileged, single-organization operator pilot; it is not a new admin approval
UI and cannot establish the truth of reviewer assertions. Review profiles/OS file
permissions before adopting it. No real inference, paid calls or model downloads.

## Verification record

The initial full implementation run passed 1,106 tests. Final review then added
organizational-reference checks, strict derived snapshots, exact-action duplicate
rejection and unsupported-version export handling. That earlier full run is not
the final acceptance checkpoint; final results are appended below after completion.

Frontend final run: **312 tests across 27 files passed**, lint, TypeScript no-emit
and production build passed. Existing jsdom navigation diagnostic remains nonfatal.
The added completeness-filter check exposed an accessible-label mismatch; explicit
aria-label and regression coverage were added. A test-only invalid Testing Library
option caused one intermediate type-check/build failure and was corrected before
the successful final runs. Initial PostgreSQL harness used the wrong drain signature;
corrected to the real session-based worker call before passing integration checks.

New contract/policy unit checks cover all21 partial-domain combinations, boundary
scores, half-up aggregation, null/strict-value rules, invalid refs/qualifications,
guidance-only evidence and remediation bounds. New PostgreSQL scenarios cover
partial generation/export/list/filter/sort, tenant isolation, forged sufficiency,
stale target and source-bound complete aggregation with a valid zero score.
All model responses mocked; tests forbid real provider HTTP.

No new whole-project coverage measurement was taken. Prior 94.24% line/85.53%
branch figures belong to the earlier measured run, not these new modules.

## Final acceptance checkpoint

- Full backend: **1,115 passed in560.82s**, PostgreSQL required, warnings as errors;
  JUnit confirms zero failures/errors/skips. Command:
  `python -m pytest -q -ra -W error --require-postgres --junitxml=../temp/testing/evidence-v3-final-junit.xml`
  from backend. The earlier1,106-test run is superseded, not combined with this run.
- Frontend: **312 passed**,27files; lint, TypeScript and final production build pass.
- Native installed Chrome: **18/18 new-contract checks**, evidence directory
  `temp/auditmind-demo/browser/phase3/phase3_browser_918c9c81d764/`; **17/17 legacy
  checks**, `phase3_browser_f4f98dc451ce/` under the same parent. These are35 scenario
  executions across two modes, not35 distinct capabilities. Zero page errors and
  cleanup verified for both. Complete/partial filter, mobile/print/source navigation,
  real downloads and existing lifecycle/permission/retry/cancellation checks covered.
- Final-code earlier18-check attempt failed on the filter's accessible label; its
  fixture was cleaned and only the corrected complete rerun counted above.
- After all runs, validated local `auditmind_test` restored through empty→0021→0020
  →0021; drift check clean, repeat head upgrade no-op,29 public tables and zero
  isolated browser schemas remain. No ordinary application schema migration.
- Demo rebuilt/restarted with existing credentials/data retained, loopback only.
  New flag remains off in normal configuration; no qualification pack installed.
  No new commit/push or production release performed by this implementation task.
