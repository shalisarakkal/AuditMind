# Durable absence review integration - 11 November 2026

## Verified delivery - 11 November 2026

The durable absence-review queue is delivered on `main` through `60d957b`.
All four hosted Linux jobs passed for exact commit
`60d957b4f9f03383e797a26677e31fb60fce2077` in
[run 43045746714](https://github.com/shalisarakkal/AuditMind/actions/runs/43045746714): backend, frontend, dependency/security
and browser acceptance (including evidence/scoring and worker recovery).
Local acceptance: 1,723 backend tests, 567 frontend tests and 99 Chrome checks.
Migration 0049 is active locally. CI uses preinstalled stable Chrome on Ubuntu
24.04; the earlier Chromium installer failure did not recur on this path.
This supersedes older pending/unmerged queue statements; dated checkpoints
remain historical. It does not approve a pilot, production deployment or SaaS load.

Next: [imported-finding suppression and restore design](IMPORTED_FINDING_SUPPRESSION.md).
Suppression, restore, reappearance handling, consolidation and payload publication
are not delivered by the review queue. PB-1.3 remains open.


## Integrated scope

The user authorized review and inclusion of both worktrees. The durable-review
implementation was copied from `feat/pb-1-3-absence-review-queue` at baseline
`43e61bb` into the current main workspace after the `50f9c3d` review closeout.
All 17 modified files and both new source/migration files were included. The
three documentation conflicts retain the prior release evidence and distinguish
this increment from the earlier read-only preview. The original Copilot worktree
is preserved; its old raw patch must not later overwrite these reviewed fixes.

Migration 0049 adds retained batch/context snapshots, bounded candidate rows and
append-only keep-active/reopen decisions. Authorized administrators and auditors
can save a reviewed batch and record a reasoned disposition. Members can read.
Neither operation changes finding workflow, archive state, severity, scoring,
qualification or saved reports. Suppression, consolidation, payload publication
and automatic reappearance handling remain separate work.

## Review findings and corrections

1. A preview could change before saving and the server silently persisted its
   replacement. The PostgreSQL regression reproduced HTTP 200 after a workflow
   edit. Saves now require a SHA-256 review token binding complete declarations,
   all reviewed identities and the full bounded candidate snapshot; a changed
   context returns 409 without writing a batch. Paging cannot append candidates
   from a different preview token.
2. A keep-active decision could be recorded after the finding workflow changed.
   The regression reproduced HTTP 200. The service now locks and reloads the
   finding, checks its captured workflow version and refuses stale or removed
   findings. Reopening a retained review remains a queue-only decision.
3. Close and filter/page navigation remained enabled during a decision save.
   A held-request UI regression failed on the enabled Close button. Submission
   now uses an immediate in-flight guard, freezes dismissal/navigation and
   prevents double submission. Version conflicts retain the rationale and
   require an explicit reload; successful edits return to page one.
4. Inventory publication must not strand workflow writes behind review requests.
   Queue saves attempt the inventory lock without waiting and return a clear
   conflict when busy. Keep-active/reopen notes do not take that lock. Real
   independent-session tests cover an active publisher and two concurrent
   administrators, with exactly one winner for a shared decision version.
5. Queue pages joined and returned the full scan declarations for every item.
   Batch contexts are now fetched once per page batch and the response contains
   compact historical summaries. Full declaration context is retained once in
   the ledger. Candidate descriptions are bounded to 2,000 characters. Actor
   foreign keys have indexes to avoid full ledger scans during user deletion.

Activity labels follow existing display conventions and decision events carry
the finding UUID for scoped navigation. Earlier review decisions are retained
in the append-only ledger/Activity; the queue displays the latest decision.

## Acceptance evidence

- Before-fix reproductions: both stale-save PostgreSQL cases failed as expected;
  the held-save UI case failed as expected.
- After fixes: all 56 focused PostgreSQL tests passed, including migration
  upgrade/rollback and schema parity, idempotence, retained source purge,
  independent concurrent admins, import-lock behavior and tenant isolation.
- All 567 frontend tests, complete lint and isolated production build passed.
- Full required-PostgreSQL backend regression: **1,723 passed** in 2,602.03 s
  (43m 22s), with warnings as errors and no skips. This includes the focused
  checks above; counts are overlapping, not additive.
- Installed Chrome workflow: **99 checks passed**, including long-filename
  mobile/Axe, held queue submission, fresh viewer login after the earlier
  password-reset test, explicit keep-active/reopen and unchanged finding state.
  Artifact: `phase3_browser_ea3eda7f7fdb`. The focused queue walkthrough also
  passed with an actual reset viewer account (`phase3_browser_0b5d06ccf756`).
- High-severity Bandit, dependency consistency, tracked-file secret guard and
  whitespace checks pass; all 315 relative documentation references checked
  before final closeout resolved.
- Normal local app upgraded to 0049 without schema drift after all six work
  queues were idle. Both actor indexes are present. Login, health and readiness
  return HTTP 200. Existing data/accounts/passwords were retained; no feature,
  scoring, provider or worker-capacity setting was changed.
- The original Copilot patch is byte-for-byte unchanged and the backend source
  remained unchanged throughout the full run. Private test databases were
  removed and their servers stopped.
- Hosted Linux CI must pass for the exact pushed commit. The delivery handoff
  links its authoritative run; earlier green runs do not certify this increment.

Tests use private PostgreSQL instances or isolated browser schemas. Normal
application data, credentials and the other worktree are preserved. This is
software acceptance, not customer-pilot, SaaS load or production approval.


## Hosted runner setup follow-up

The first exact-SHA run for `c6a3328` passed backend, frontend and dependency/
security jobs. Browser setup failed during `playwright install`, before build
or application acceptance; no browser test failed in that run. Evidence:
[run 43039395961](https://github.com/shalisarakkal/AuditMind/actions/runs/43039395961).
The public job metadata does not establish the precise installer root cause.

Browser CI is now pinned to supported Ubuntu 24.04 rather than a rolling
`ubuntu-latest` image, and setup permits at most three attempts. A final failed
installation still fails the job; no test or dependency check is bypassed. The
job's 30-minute ceiling bounds setup plus the full browser/evidence/worker
acceptance. Other Linux jobs retain their existing environment. Application
source is unchanged. Shell checks exercise first-attempt success, recovery on
the third attempt and three-failure exit behavior with a mocked installer.
A fresh exact-SHA hosted result is required at delivery.


The bounded installer retry also remained in setup for more than 15 minutes.
CI therefore uses the Ubuntu 24.04 image's preinstalled stable Google Chrome,
through the existing Playwright `chrome` channel, matching local acceptance.
A mandatory version/launch preflight replaces managed Chromium installation;
all application, evidence/pilot and worker checks remain mandatory. This avoids
that installation dependency without claiming its unknown root cause is fixed.
The exact pushed commit still requires a successful hosted run.
