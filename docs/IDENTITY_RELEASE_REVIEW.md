# Finding identity release review - 7 November 2026

Scope: PB-1.3 identity candidate foundation and explicit reviewed bindings at
migration 0046. This is not approval of reconciliation, suppression, production
hosting or SaaS-scale operation. Earlier CI for 4e071af covers the preceding UI
increment; this identity increment needs its own exact-commit hosted CI.

## Confirmed findings and reproductions

Seven product defects were reproduced before fixes in
`FindingIdentityBinding.test.tsx` (the first four failures alongside four existing passing tests; a later modal
reproduction failed alongside eight passing tests):

1. Editing the scanner or canonical asset retained confirmation of the previous
   mapping. Changes and pagination now clear confirmation; save requires a new
   explicit confirmation.
2. Reopening a cancelled editor retained old mapping choices, rationale and
   confirmation. A fresh review now resets its draft choices and reads current
   context. Conflict reload retains the text draft but clears tool selection and
   confirmation before retrying.
3. Retirement confirmation did not name or freeze its target. It now captures the
   tool ID/version/name, disables mapping edits and saving while pending, and
   submits only the captured target.
4. A registered tool sorting beyond the first 100 namespaces disappeared from
   selection. The newly registered namespace remains an explicit available choice
   until it is included in a fetched page or the review is abandoned/reloaded.

5. Retirement remained an inline panel, allowing interaction with other workflow
   forms. It now opens a blocking application dialog, focuses Cancel and isolates
   Escape to the top dialog. The parent workflow/draft stays open on cancellation.

6. Real Chrome Axe found 4.49:1 contrast on the translucent destructive-action
   button in the active retirement modal. The shared danger fill is now solid
   red with navy text; the existing report-confirmation style check was updated
   and the real nested-modal accessibility check remains required.

7. Reviews did not capture their identity algorithm/mapping version. Two backend
   reproductions showed old reviews yielding new-contract candidates after a
   version change. Reviews now pin algorithm version, source mapping and normalized
   material; either contract change withholds candidates until explicit re-review.
   Both regression cases pass, including successful explicit re-review.

All nine binding UI tests and three shared-dialog tests pass after flow corrections. Chrome additionally
exercises changes to both scanner and canonical asset before saving. A browser
selector timeout was separately reproduced with a minimal native select: its
accessible combobox role works while an exact wrapped-label text locator does
not. The browser test now uses the semantic role; this was a test defect.

## Backend review boundaries

- All endpoints scope records by organization and membership; admin writes use
  transactional organization admission with live role/account/lifecycle checks.
- Version checks and organization admission serialize competing reviews;
  append-only decisions and Activity events commit together.
- Tool/asset namespaces are established by explicit administrator attestations,
  never uploaded IDs, hostname/IP deduplication or CVE/description alone.
- Candidates require supported native identity material and retained current
  referenced context. Revoke/retirement and missing/changed/archived references
  withhold candidates; new imports never inherit reviewed bindings silently.
- Candidate identity remains separate from canonical conflict resolution, scan
  comparability, absence, suppression, workflow and score exclusions. Multi-query
  diagnostics are not an atomic authorization snapshot for future operations.
- Observation pages use bounded lookups rather than inventory scans or per-row
  queries. Import matching/publication does not resolve bindings. New foreign-key
  indexes support retention/purge without scanning the decision ledger.
- Migration 0046 adds two tables, with rollback and metadata-drift coverage;
  existing asset/finding/report rows are not rewritten.

## Release verification

The initial full backend run passed **1,651 tests** (required PostgreSQL,
warnings-as-errors, 21m 31s). This run predates the final version-binding fix;
it is a historical checkpoint. Both added contract-version regressions pass.
A fresh complete backend run includes that fix and is in progress alongside the
mandatory exact-commit hosted Linux run. Do not claim the earlier run as final.

The complete frontend suite passes **548 tests**. Fresh Chrome acceptance passes
**94 checks**, including native registration/binding/revoke, scanner/asset
reconfirmation, long-name mobile layout, active-modal contrast/Axe and isolated
retirement Escape. The focused six-check Chrome probe passes too. Lint,
production build, high-severity Bandit, pip consistency and tracked-secret guard
pass. The real evidence pilot passes approval/expiry/requalification/scope mismatch
and default-off rollback with no AI calls; five worker-pool recovery checks pass.

Release approval still requires all four Linux jobs on the pushed commit. Hosted
Actions is the authoritative per-commit result; customer pilot, broader
reconciliation, SaaS capacity and production acceptance are separate gates.
