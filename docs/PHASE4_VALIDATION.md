# Phase 4 remediation workflow validation

## Background evidence evaluation and Dashboard pilot — 28 October 2026

Hosted prerequisite verified before implementation: exact SHA
`c7ee354d8fe4331dd80e479889615ab2cf2ab8dd`,
[run 40706817185](https://github.com/shalisarakkal/AuditMind/actions/runs/40706817185),
conclusion **success** across frontend/browser/backend/backend-dependency-audit.
The background/Dashboard increment was subsequently reviewed, committed and pushed
as **`5ce836ba6dd00f026eb5490f37da8b4e8f249a27`** (48 scoped files). Its own hosted
Ubuntu [run 40749424003](https://github.com/shalisarakkal/AuditMind/actions/runs/40749424003)
completed **successfully** on 28 October 2026: backend, frontend, browser and
backend-dependency-audit all passed. The browser job executed both the full workflow
suite and the new durable-evidence/opt-in-scoring suite successfully. This closes
the feature's hosted verification gate. Subsequent closure documentation does not
alter runtime/CI code; production, sustained-load and default-on rollout remain unapproved.

Implemented migration 0031 with statement-trigger invalidation, durable worker jobs,
cancel/recovery/deduplication/tenant guards, guarded cached eligibility, default-off
admin opt-in, mode-aware Dashboard null/partial/complete aggregation and cheap
browser state polling. No automated full scans on page load; no report/snapshot,
weight or external-processing changes. [Detailed contract](BACKGROUND_EVIDENCE_EVALUATION.md).

Final local results (earlier focused suites overlap and are not additive):

- **1,366 full PostgreSQL tests passed in 849.31 s**, warnings as errors, zero
  failures/errors/skips. Command from `backend`: `python -m pytest
  --require-postgres -W error -q --tb=short
  --junitxml=../temp/testing/background-evidence-backend-final-20261028.xml`.
  Includes the exact terminal lifecycle count, cache/expiry/policy/source invalidation,
  complete/partial/scope-mismatch/real-zero aggregation, default-off rollback,
  worker metrics/recovery/cancel, tenant/write-admission and populated migration tests.
  Disposable `auditmind_test/public` restored to **0031**, **35 tables**, repeated
  upgrade no-op and clean Alembic drift.
- 113 focused PostgreSQL tests passed in 120.14 s before final invalidation review;
  subsequent migration/trigger/platform/admission focus: 66 passed in 94.74 s.
- 465 frontend tests passed; lint/TypeScript and isolated production build passed.
  Normal production build also passed; generated next-env paths restored normally.
- Seven dedicated real-worker/two-admin Chrome scenarios passed (latest rebuild):
  `temp/testing/evidence-review/phase3_browser_7d99f99efb76/results.json`.
  Covers queued evaluation surviving navigation, explicit mode confirmation/cancel,
  1-of-7 partial Dashboard scoring, concurrent review 200/409, source mutation and
  revocation invalidating cached eligibility, and role/tenant restrictions.
  100,000 isolated synthetic assets; setting rolled back off before teardown.
- Full existing installed-Chrome regression: 71 checks passed (latest rebuild),
  `temp/testing/finding-workflow/phase3_browser_56650f93d1a6`;
  no page/native-dialog errors or AI usage. Includes mobile/Axe/selection/archive.
  The browser CI configuration now runs the dedicated evidence suite after the
  full workflow suite and uploads both artifact folders. This new step is not
  covered by the successful earlier `c7ee354` run; it is now verified by the
  successful `5ce836b` run linked above.
- Isolated production build passed. Scoped high-severity Bandit passed; its static,
  schema-quoted trigger installer has a medium/low-confidence SQL-formatting finding,
  reviewed as identifier quoting over fixed DDL, not user-supplied SQL.
  Final full-app high-severity Bandit, `pip check`, tracked/new task-file secret
  guards, script syntax, parsed CI YAML and whitespace checks pass. This was a
  scoped implementation review, not an independent security audit or load certification.

Normal demo was checked idle (zero active jobs/cursors and zero enabled scoring
settings), upgraded to **0031** and restarted with the production build. Existing
inventory/accounts/passwords retained; all settings remain off. All **28 evidence
triggers** are present in `auditmind_demo`; `/health` and `/ready` are green.
After the final green suite, the idle stack was restarted with the unchanged
frontend build to load the final API cache headers. Authenticated live Dashboard
check returned HTTP 200, `Cache-Control: no-store`, findings-based mode and the
retained 2,798,320 assets. Settings remained off; temporary check accounts were
removed. Refresh Chrome with Ctrl+Shift+R after this production-build restart.

Initial full backend run: **1,364 passed, one failed** in 818.14 s. The failure was
the existing exact queue-metrics assertion not expecting `queue_evidence_pending`.
Updated it to verify both zero and one queued evaluation and proper session cleanup.
Fresh worker/background/platform focus then passed **67 tests in 95.78 s**.
The fresh 1,366-pass full rerun above supersedes that initial failed run; no
failures were waived. Historical sections below refer
to the boundaries and test totals at those checkpoints, not the current contract.

The first durable full-size attempt exposed a reporting defect: the final 44
lifecycle rows were fingerprinted, but the half-second progress throttle suppressed
their short final batch (displayed 6,374,161 / 6,374,205). Completion now force-flushes
the exact terminal count. A deterministic service-clock regression covers 44 rapid
lifecycle records; after correcting its synthetic event setup, it passed. The idle
demo API/worker were restarted without rebuilding the unchanged frontend, and the
real full-size measurement was repeated successfully. The failed attempt is retained at
`temp/testing/evidence-http/3c8fb3799082cb772f9b45be/results.json`; it is not claimed
as successful performance acceptance.

The repeated real Chrome/proxy/API/worker check passed all five measurement checks:
`temp/testing/evidence-http/9848f5c3a47cc455fd194e33/results.json`. Both scans reached
**6,374,205 records** with identical fingerprints: browser completion **115.353 /
111.645 s**, worker **112.8 / 110.2 s**, 202 acknowledgement **70.5 / 115 ms**.
The second viewer shared the existing job; navigation did not stop it. Concurrent
cheap state read: 64.5 ms. Cancellation acknowledgement 68.4 ms; database drain
25.756 s, no partial result. No active jobs/cursors remained; inventory/AI usage
unchanged; both temporary viewers removed. No cache flush, builds or regression
suites overlapped timed processing. These are local first/repeated measurements,
not controlled cold/warm or production capacity acceptance. Final full backend
rerun started after timed processing finished.

## Evidence qualification review — stage two, 27 October 2026

Backend-only, not activated in demo: migration 0030, current organization operational
document sources, organization-wide inventory/material-history fingerprints, admin
review/revocation, complete-objective attestations and expiry/conflict evaluation.
Scope provenance retains the fingerprint/version and population counts, not a full
historical inventory manifest. Missing/stale/changed/foreign evidence fails closed.
Evaluation reads one repeatable-read snapshot; review locks inventory publication
and follows document-parent-before-version worker ordering. Review validity is
90 elapsed days (2,160 hours), with a DST database-boundary regression.

Full PostgreSQL regression: **1,327 passed** in 699.32 seconds. Final review then
hardened document lock ordering, retained scope-summary provenance and downgrade
handling; fresh combined draft/review/dashboard/migration regression passed
**55 tests**, including the new lock-order test (overlapping, not additive).
High-severity Bandit, whitespace and secret checks passed. Mode remains unavailable/off;
UI, dashboard aggregation and large-inventory optimization remain pending. No
inference, demo migration, restart, commit or push is part of this stage.
Existing-UI Chrome regression with the new backend: **71 checks passed**, including
new default-off/unavailable and empty-coverage API checks; no AI usage or page errors.
Artifacts: `temp/testing/finding-workflow/phase3_browser_e493ebae1bcc`.
Disposable auditmind_test/public restored to **0030**, 33 tables; repeated upgrade
is a no-op and Alembic drift check passed. Demo remains at 0028 and was not restarted.
This is not acceptance of a reviewer UI, which remains unimplemented. No frontend
source changes; prior 434 frontend-unit results remain historical, not rerun here.

## Evidence scoring registry — stage one, 27 October 2026

Local backend foundation, not activated in demo: migration 0029, default-off and
unavailable settings API, versioned/admin-only qualification drafts, member reads,
source-finding hashes and tenant/lifecycle admission fences. No approval route,
live evaluator, qualified dashboard scores, Settings switch or inference enabled.
Draft sources currently support findings only; document evidence and immutable
inventory scope are subsequent work. No existing report schema/score was changed.

Initial focused PostgreSQL dashboard/draft/migration run: 21 passed, including
upgrade/downgrade/re-upgrade, legacy report preservation and Alembic drift check.
Additional foreign-source/concurrent-creation tests are included in the ensuing
full run. A timestamp-format comparison initially failed because PostgreSQL used
a session-local offset; API updated_at output now normalizes the same instant to
UTC and the focused rerun passed. High-severity Bandit gate and secret guard pass.
Full PostgreSQL suite: **1,296 passed** in 653.25 seconds. Code review then added
fail-safe disabling for a pre-existing enabled settings row and a regression case;
the final focused draft/dashboard/migration run passed **24 tests**, including that
addition and concurrent creation. These focused results overlap the full run and
are not additive. High-severity Bandit, whitespace and secret checks passed again.
Disposable auditmind_test/public restored to Alembic head **0029**, 33 tables;
repeated upgrade is a no-op and drift check passed. Demo/normal databases were
not migrated or reset, and no inference/paid calls were made.
Earlier hosted 1,284 backend, 434 frontend and 70 Chromium results below apply to
ceef079, not this new registry. No frontend code changed or new browser-visible
workflow was delivered in this stage; reviewer UI/Chrome acceptance remain pending.

## Hosted mobile-overflow follow-up — 27 October 2026

**Closed with hosted evidence:** fix `ceef07984a04935b6d78e473699ef08a8f3fadb1`
was reviewed, committed and pushed. [Run 40559697870](https://github.com/shalisarakkal/AuditMind/actions/runs/40559697870)
completed successfully; all four jobs ran on ubuntu-latest and passed:

- Full PostgreSQL backend suite: **1,284 passed** in 478.63 seconds.
- Frontend: **434 passed** across 44 files; lint, production build and audit passed.
- Chromium browser acceptance: **70 checks passed**, including 320/390px dashboard
  document-width and wrapping checks. Hosted artifact schema:
  `phase3_browser_76a60651b286` (browser-acceptance artifact in the linked run).
- Backend dependency audit: passed; backend dependency consistency check passed.

These are fresh hosted totals for this SHA, distinct from earlier 61 focused or
1,281 historical backend results and local Chrome runs. Counts are not additive.
Mobile-fix verification is closed; no production deployment or live-AI sign-off.

Hosted run `40553450269` for `387f72c` failed the browser job's dashboard mobile
width assertion on ubuntu-latest; frontend and backend dependency-audit jobs passed.
This does not invalidate recorded Windows local passes, nor establish Linux success.

Fix: explicit one-column shrinkable tracks for dashboard overview, lower panels
and Security summary; min-width zero on score cards; dashboard text may wrap
anywhere for narrow available content; smaller mobile padding retains desktop
spacing. No overflow-x hiding, scoring change or sidebar redesign. The fixed-width
sidebar makes available main-content width smaller than the viewport; implicit
minimum-content grid sizing and font metrics must not dictate the page width.

Browser regression now checks 320px and 390px, reports offending elements when
document width fails and checks visible-overflow content rather than accepting
clipping. Targeted runs may set AUDITMIND_BROWSER_DASHBOARD_ONLY=1 with bundled
Chromium; they still prepare/clean isolated PostgreSQL/API/worker fixtures.

Fresh local validation: 434 frontend tests passed (29 focused tests overlap),
ESLint and isolated production build passed; full Chrome 70 checks passed.
Artifacts: `temp/testing/finding-workflow/phase3_browser_6377fef7e550`.
Bundled Chromium focused run: 7 checks passed including 320/390px document/content
width checks; `temp/testing/finding-workflow/phase3_browser_0bb4a8d62c13`.
Normal production build and idle demo restart passed; no data/password resets.
An initial baseline diagnostic run later failed an unrelated password-toggle
assertion; the rebuilt complete Chrome rerun passed. Hosted Linux verification
subsequently passed for `ceef079`, as recorded above.

## Empty-organization dashboard safeguard — 27 October 2026

Dashboard API returns `assessment_status=not_assessed`, null score/tier for overall
and seven domains when active asset and finding counts are both zero. Otherwise
status is `findings_based`, without claiming qualified evidence coverage. Existing
scoring calculation is unchanged for nonempty organizations. Archived records and
other tenants cannot make an empty organization assessed. UI preserves the layout
and displays neutral Not assessed, without risk labels or coercing null to zero.
No migration; risk snapshots and saved report contracts are unchanged.

Validation: 434 frontend tests, ESLint and isolated production build passed.
Focused PostgreSQL scoring/dashboard/archive regression: 61 passed (includes the
initial 9 dashboard tests; do not add the counts). These focused results are not
a new full-backend-suite run. Partial-domain evidence rules remain pending.
Normal production build and idle demo restart passed; data/accounts retained.
Chrome: 70 checks passed against isolated PostgreSQL/API/worker, including null
API contracts and eight Not assessed cards with no risk tier.
Artifacts: `temp/testing/finding-workflow/phase3_browser_61c079037c36`.
Earlier attempts exposed an obsolete tier assertion and a missing authentication
header in the new test; both corrected before the successful complete rerun.

## Resilience risk-tier presentation — 27 October 2026

**Current design correction:** user requested the former appearance with text
colors only. The new bordered badges, tinted domain cards, added dashboard /100
and guidance blocks have been removed; original dashboard gradient and compact
domain layout restored. Critical/red, High/orange, Medium/amber and Low/green
score/tier text remains shared. Report evidence and scoring contracts unchanged.
433 frontend tests, ESLint and both builds pass after this correction.
Chrome: 69 checks passed, including original gradient/layout preservation;
artifacts `temp/testing/finding-workflow/phase3_browser_0173fd6c38cf`.
The first attempt used the stale acceptance build; rebuilt it and reran fully.
Demo was
idle before restart; the corrected version is active, with readiness all true
and frontend login HTTP 200. The description below records the earlier design,
not the current presentation.

Dashboard and browser Reports share red Critical, orange High, amber Medium and
green Low risk badges, subtle tier-tinted surfaces and / 100 score labels.
The existing assessment tier is authoritative; no thresholds or scoring changed.
Missing report scores remain neutral, and evidence/confidence remain separate.
Downloaded HTML/PDF templates were not modified in this increment.

Validation: 433 frontend tests passed, including all four tier mappings and
neutral fallback; ESLint, isolated build and normal production build passed.
Chrome: 69 checks passed against isolated PostgreSQL/API/worker, including the
dashboard text badge, denominator, tier surface, layout and accessibility suite.
Artifacts: `temp/testing/finding-workflow/phase3_browser_ae7fd600ed16`.
After confirming zero active demo jobs, restarted without resetting data or
credentials. API database/uploads/worker readiness all passed; frontend login 200.
This also activates the earlier shared upload wording and Show/Hide changes.

## Upload wording and disclosure follow-up — 27 October 2026

Shared upload controls now distinguish incompatible selected sources from files
with no supported profile, use visibly disabled Upload buttons and per-file Remove,
and confirm Close/Escape before discarding queued files. Keep reviewing preserves
the queue; submitted imports are never cancelled by closing. Summaries no longer
refer to groups "below". Disclosure action labels switch Show/Hide through native
open-state styling, with shorter reports-only labels after processing.

Validation: 428 frontend tests passed; ESLint and isolated production build passed.
Chrome acceptance: 68 checks passed against isolated PostgreSQL/API/worker;
artifacts: `temp/testing/finding-workflow/phase3_browser_a72f892930a7`.
An initial browser startup timeout ran zero checks; the subsequent full run passed.
The earlier full PostgreSQL backend run is unchanged evidence, not rerun for this
frontend-only increment. Activation is deferred while demo imports are active.

## Drag/drop navigation regression — 27 October 2026

Cause: the upload-dialog refactor left drag/drop handlers on the small header
control only. A file dropped on the surrounding page could reach Chrome's default
local-file navigation. Fix: shared Assets/Findings document-level intake, with a
signed-in layout capture guard preventing file-open default on other pages.
Local drop targets stop propagation; listeners clean up on unmount and maintain
current queue/org state via a ref. Busy queues and unrelated modals do not receive
files. Native file inputs and text drags retain their defaults. No auto-submit.

Fresh **428 frontend tests passed** (70.39s), including body multi-file drops,
single delivery, guard cleanup, text and native file-input cases. Lint and isolated
production build/TypeScript passed. No backend code/schema changed in this fix;
the **1,281 backend tests below are the previous full policy run**, not rerun here.
Chrome acceptance uses real Input.dispatchDragEvent OS-file payloads, asserts two
actual filenames and unchanged app URLs, then exercises the existing real API/
PostgreSQL workflow. The first attempt dispatched before the uploader was ready;
waiting for visible authenticated controls corrected the test timing. Final
**68 Chrome check executions passed** (`phase3_browser_3052352df4b8`) against real
isolated API/PostgreSQL/worker, including the native two-file drop and existing
policy/workflow regressions. Grouped/repeated checks are not independent scenarios.
No browser page errors or AI usage. Secret/whitespace guards passed.
Local activation: read-only live checks found zero pending/running scans, archive
jobs and reports. Rebuilt the normal production frontend and restarted the local
demo successfully; existing data/accounts/settings retained. Database/uploads/
worker readiness and login HTTP 200 passed. No active jobs were interrupted.

## Exact duplicate file policy — 27 October 2026

Local activation: on the user's later restart approval, read-only admission check
found zero pending/running demo imports. start-demo.ps1 stopped only its recorded
processes, retained demo data/accounts/settings, passed the normal production
build and restarted API/worker/frontend. /ready confirmed database/uploads/worker,
/login returned HTTP 200 and live OpenAPI exposed ask/skip/reimport. No credentials
were reset, no organization policy was changed and no inference call was made.

Organization admins can select Settings → Ingestion → Exact duplicate files:
Ask (default), Skip or Reimport. The backend enforces the effective organization
override/server EXACT_DUPLICATE_FILE_POLICY on generic assets, generic findings
and profile imports. All use the same org/SHA-256 comparison; filenames/profile
changes alone do not change identity. Ask preserves grouped decisions. Skip
returns HTTP 200 with skipped=true and the matched scan ID, no new job/report;
it records upload_skipped with actor, filename, matched scan/hash, reason/policy.
Reimport admits another job without asking, while existing row-handling settings
remain independent. confirm=true cannot override Skip. Queued/running matches
always skip, including Reimport and confirmed Ask. Failed/archived matches are
excluded; explicit worker retry remains a different operation.

Review: PostgreSQL transaction advisory locks serialize org/hash admission; the
existing shared organization lifecycle lock keeps settings/archive changes out
of admission. Skip responses do not return the matching uploader's report and
the frontend never adds their scan to its tracker. Skip counts and single-file
reasons are shown; Activity has a labelled/searchable event. Settings retain
admin-only writes, enum validation and reset-to-server-default. No schema change:
the policy uses existing ingestion_overrides JSON. No new dependency or paid AI.

Focused PostgreSQL passes: 33 new-policy/settings unit/integration tests and
101 broader import/archive/worker/activity regressions. Full frontend rerun:
**425 tests passed** (73.87s, two workers), lint and isolated build/TypeScript
passed. These focused counts are not substitutes for, or additive to, a full
backend result. Fresh **full PostgreSQL suite passed 1,281 tests** in 691.72s,
with --require-postgres -W error. It includes real migration round-trip checks;
this replaces (does not add to) the older 1,268-test baseline below. After pytest,
auditmind_test public was restored to **0028 / 31 tables**, repeated upgrade was
a no-op and autogenerate detected no drift. The restore helper's first launch
from repo root had no TEST_DATABASE_URL loaded and stopped before connecting;
running it from backend loaded the intended configuration and passed.
Final **67 Chrome check executions passed** against real isolated PostgreSQL/API/
worker (`temp/testing/finding-workflow/phase3_browser_2b4dd2510d0c`): Ask grouped
approval, Settings-persisted Skip/Reimport with real files and no prompts, Activity
skip rows and reset to Ask, plus existing roles/concurrency/layout/accessibility
regressions. Initial acceptance stopped at a selector matching a hidden Activity
filter label; scoping it to table rows fixed the test and the full rerun passed.
Grouped/repeated executions are not independent scenarios. No browser errors or
AI usage. Static high-severity, secret and whitespace guards passed.
During implementation/testing no running application/worker restart or live
configuration change was made; the subsequently approved activation is recorded above.
The high-severity Bandit gate passed; this is not a blanket clearance of the
previously documented lower-severity static-analysis backlog.

## Grouped upload decisions — 27 October 2026

All shared Assets/Findings import formats/sources now submit every ready file
sequentially, continuing after duplicates as well as errors. Duplicates collect
in Already uploaded with prior uploader/date, initially unselected, for Skip
selected or explicit Upload selected anyway. Known accepted files leave the
queue; failed submissions and source problems have separate groups. Retry failed
targets failures only. Reimport is not a guarantee to update records: existing
import settings still govern asset handling. Single-document versions and logo
replacements retain their different single-item lifecycle contracts.

Review preserved fixed targets, explicit confirmations, stop/double-start guards
and the no-restart boundary. Queue cancellation and grouped skipping also check
the active ref to guard the pre-render interval. Drops are blocked during an
active submission; stale selections are cleared when their files are removed.
Zero-ready primary buttons are hidden outside submission, and progress is labelled
Last pass so its historical counts are distinct from current group counts.

Tests cover mixed duplicates/failures/unreadable sources, later ready-file
submission, explicit group selection/reimport, skipping without POST, independent
sources, double clicks, stop and failure-only retry. Existing single-duplicate
regressions now use the same group flow. Full/backend historical results below
are not additive and no new full backend run is claimed: backend/schema unchanged.
Final frontend suite: **422 tests passed** (80.90s, two workers). Lint and isolated
production build/TypeScript passed. A focused post-review pass also passed 62
tests; focused/full counts overlap and are not additive. **64 final-build Chrome
check executions passed** against real isolated PostgreSQL/API/worker
(`temp/testing/finding-workflow/phase3_browser_63afc981a1bf`), including two actual
duplicates followed by a new file, selected skip and explicit selected reimport,
dialog focus/mobile layout and scoped Axe. Screenshot visually reviewed. Grouped/
repeated executions are not independent scenarios. No browser page errors or AI
usage. Secret/whitespace guards passed; unrelated local/branding files preserved.
No demo/worker restart, production migration, paid/inference call, commit or push.

## Upload presentation follow-up — 26 October 2026

Upload selection now opens a named native dialog shared by Assets/Findings, with
secondary row actions and one primary batch action. Header actions stay 40px high;
Detected badges replace repeated explanations. Empty accepted queues close;
submission confirmation expires after 3 seconds. Background progress/reports use
one expandable disclosure, automatically opened for failures/interruption/failed
rows. Errors and reports are not timed away. Idle dialog cancellation discards
only unsent files; active submission continues to block dismissal.

Fresh **420 frontend tests passed** (82.77s, limited to two workers to reduce load),
lint and isolated production build/TypeScript passed. Three additional regressions
cover named dialog cancellation/no POST, collapsed grouped progress and failure
auto-expansion. Existing tests were updated for short badges and explicit dialog
cancellation before replacing a failed queue. Initial fixture selector/type
failures were corrected before the successful run. Backend source/schema is
unchanged; no new full backend run is claimed. **63 Chrome check executions
passed** (`temp/testing/finding-workflow/phase3_browser_eb4fecbe009f`), including
real PostgreSQL/API/worker submission, dialog focus, desktop/mobile overflow,
scoped Axe and grouped progress/report disclosure. Desktop/mobile screenshots
were visually reviewed. Grouped/repeated checks are not independent scenarios.
No browser page errors or AI usage. Tracked-secret/whitespace guards passed.

No normal frontend build, demo restart, worker stop or migration was performed.
The running demo remains on its previous build so user imports are undisturbed;
activation is a separate controlled restart after processing. The isolated
acceptance server uses different ports/schema and no inference calls.

## Shared batch-upload increment — 26 October 2026

Assets and Findings share one-click sequential Upload all ready files, per-file
source/report preservation, locked queue edits, double-start prevention, stop
after the current submission, failed-file retry and explicit duplicate pauses.
Review also preserves duplicate confirmation after a failed explicit retry and
prevents tracking errors from making accepted jobs uploadable again.

Fresh frontend suite: **417 tests passed** (25.00s); lint, TypeScript and isolated
plus local-demo production builds passed. Four added component regressions cover
sequential/stop/double-start behavior, failure continuation/retry, duplicate pause
and independent source routing. A preliminary retry assertion ran before React's
queue-state effect committed; the test now awaits the enabled Retry control.
The final complete rerun passed. No backend source/schema changes: **1,268 backend
tests below remain the earlier full run**, not a new result for this increment.
The final **61 Chrome check executions passed** against real API/worker/PostgreSQL
(`temp/testing/finding-workflow/phase3_browser_2cf4a9d36ca5`). The shared-control
check submits both files with one click. Grouped/repeated checks are not 61
independent scenarios. No browser page errors or AI usage were recorded.
Demo rebuilt/restarted successfully; database/uploads/worker readiness passed.
Tracked-secret and whitespace guards passed; unrelated branding originals and
local configuration remain excluded. No inference, paid calls, commit or push.

## Final combined-tree check-in review — 26 October 2026

Scope: migrations 0025–0028, organization and platform branding, approved active
SVG assets, auth presentation and shared password visibility. Review corrected
two issues before handoff: logo transport bounds now honor configured API prefixes
(regressions cover default/custom prefixes), and temporary-password clipboard
failures have a safe fallback while copy status resets for a new handover.

Fresh **413 frontend tests passed** (25.09s final rerun), lint/TypeScript/isolated production
build passed; **61 Chrome check executions passed** (`phase3_browser_526fedeba757`)
against real isolated PostgreSQL/API/worker, including synthetic password reset/
change, platform/organization role separation, stale writes, layout and Axe.
Grouped/repeated executions are not independent scenarios. npm audit found zero
vulnerabilities; core/dev and optional-embedding pip-audit manifests found none;
pip check passed. Bandit's high-severity gate passed; 12 low/16 medium findings
remain triage work, not a blanket security clearance. No live AI calls.

The preliminary backend run was intentionally stopped after the configurable-
prefix finding. The restarted **full PostgreSQL suite passed 1,268 tests in
668.14s**, with `--require-postgres -W error`. It includes real migration upgrade/
rollback/no-op/drift checks through 0028. Earlier focused/full counts below are
historical and must not be added to this run.

After pytest, the disposable auditmind_test public schema was restored to **0028**
(31 tables), repeated upgrade was a no-op and autogenerate check found no drift.
The temporary restore helper's first check used an explicitly qualified version
table while comparing the default schema; removing that helper-only schema hint
resolved the false alembic_version remove-table diff. No application schema fix
or stamping was needed; real round-trip tests had already passed.

Reviewed code commits: backend **d08b0fe**, organization UI **1cf9923**, product/
auth/password UI **4f153f9**. The acceptance/docs commit contains this record.
Acceptance/docs commit **b91ade6** was pushed with those three code commits to
origin/main. Remote main had been unchanged at c008efc before preparation.
GitHub's [per-SHA validation run for b91ade6](https://github.com/shalisarakkal/AuditMind/actions/runs/40431697376)
is the authoritative hosted result for the accepted code, not the old baseline.
The documentation-only handoff follow-up leaves application/test code unchanged;
its own [latest main workflow result](https://github.com/shalisarakkal/AuditMind/actions/workflows/ci.yml?query=branch%3Amain)
must also be checked. Local results above do not imply a hosted conclusion.

Commit scope excludes unrelated cline.json, credentials, temp evidence/process
state, alternate/reference branding originals, installed packages and builds.
Only active product-logo.svg/favicon.svg and their README are staged as public
assets. Hosted results must be tied to the actual pushed SHA, not c008efc history.

## Historical implementation checkpoints

## Shared password visibility — 26 October 2026

Shared PasswordInput now covers login/register, every current/new/confirmation
field and admin temporary-password handovers (People/platform Accounts/organization
creation). Hidden by default; independent Show/Hide actions use type=button,
field-specific accessible labels, aria-controls, visible keyboard focus and 44px
controls. Values/name/autocomplete/required state and paste are retained. A new
handover resets visibility; explicit Copy works while masked. Visibility is local
state, not stored or sent. Change-password native form now uses POST, preventing
password query strings before hydration; footer links are permanently underlined.

**411 frontend tests passed** (24.16s), lint, TypeScript and production build
passed. Tests cover keyboard activation/no form submission, hidden remounts,
independent fields, preserved metadata/value, disabled controls, masked handover
copy/reset, and existing auth/change-password/People/platform submissions. An
initial test matched both the handover group and field label; the field now has
the distinct accessible name “Temporary password value.” Backend unchanged; the
earlier 54 focused and 1,260 full backend results are not reruns for this UI-only
follow-up. **61 Chrome check executions passed** (`phase3_browser_438b4af892ce`),
covering keyboard login reveal/hide/no-submit/remount, registration presentation,
real synthetic-user reset handover, independent change-password toggles and a
successful real test-API password change, plus existing regressions/Axe checks.
Auth groups repeat across two contexts; counts are executions, not independent
scenarios. Mobile sign-in screenshot visually reviewed. A final stronger Done-
removal assertion passed all **13 focused People tests** (3.09s), overlapping the
411 total, not additive. No actual demo-account password changes or AI calls.
Changes remain local, uncommitted/unpushed; hosted CI has not run this tree.

## Platform-admin product-logo size — 26 October 2026

New **Platform → Product branding** page controls only the shared sidebar product
logo: Small 144×40, Medium 180×48 (default), Large 192×64px, bounded by sidebar
width and preserving proportions. Auth stays 240×72; company branding is unchanged.
Signed-in users can read display size/version; only active platform admins can
write. Stored in existing platform_settings (no new migration). Version checks,
transaction advisory locking for concurrent first saves, fresh actor-role checks
and Platform activity auditing protect writes. No-op saves leave version/audit
unchanged; stale UI requires explicit reload.

**406 frontend tests passed** (24.69s), lint, TypeScript and production build
passed. **29 focused PostgreSQL tests passed** (25.59s, warnings as errors),
including branding/logo/settings and two migration checks; **25 separate platform
API regression tests passed** (46.95s). These are 54 checks across disjoint files,
not a new full backend run. Head remains 0028. **55 Chrome check executions passed**
(`phase3_browser_b2627365248d`), including all size choices, platform-admin editing,
organization-admin UI/API denial, cross-user persistence, two-tab conflict/reload,
Axe and existing regressions. Initial conflict assertion also matched Next.js's
route-announcer alert; scoping it to the settings panel corrected the test without
weakening the expected error. Product-branding screenshot visually reviewed.
These are grouped executions, not 55 independent scenarios. No external inference
or provider credentials used; local changes are uncommitted/unpushed and hosted
CI has not run this tree.

## Company-name typography — 26 October 2026

New admin-only **Header company name size** setting: Small 16px, Medium 20px
(larger default), Large 24px. Organization-wide persistence, same-window header
refresh and other-session refresh behavior match logo sizing. Selector, product
logo and other typography are unchanged; visibility/fallback rules are retained.
Migration **0028** adds a constrained size defaulting to medium, retaining existing
logos and branding preferences. Optional expected/value size pairs maintain old
client compatibility; all requested fields validate before any mutation. Actual
changes are audited under the existing organization lock/lifecycle fences.

**399 frontend tests passed** (37.68s), lint, TypeScript and production build
passed. **28 PostgreSQL tests passed** (34.73s, warnings as errors): 26 focused
branding/logo/settings checks and two real upgrade/rollback/no-op/drift tests,
including existing-organization defaults at 0028. These are not a rerun of the
earlier 1,260-test full backend suite. **52 Chrome check executions passed**
(`phase3_browser_da2795906ee4`), including actual 16/20/24px computed font sizes,
cross-member persistence, viewer read-only access, stale-name-size reload and the
existing workflow/auth/accessibility regressions. These are grouped executions,
not independent scenarios. No live inference calls. Local changes remain
uncommitted/unpushed; hosted CI has not run this tree.

## Configurable organization-logo size — 26 October 2026

Admin-only Small/Medium/Large preference changes header and Settings preview,
preserving aspect ratio. Medium 160×64px is the default; Small is 96×48px and
Large 224×80px. No square backdrop, automatic cropping or product-logo changes.
Header identity wraps within mobile widths. Transparent source padding remains.
Migration **0027** retains images/name preferences and adds a constrained size
with default medium. Writes validate values, lock the organization, audit actual
changes and reject stale expected size/name values; viewers remain read-only.

Final **395 frontend tests passed** (23.96s), lint, production build and TypeScript
passed. **27 PostgreSQL tests passed** (34.38s, warnings as errors): 25 focused
branding/logo/settings checks and two real migration upgrade/rollback/no-op/drift
checks, including the default for an existing organization. This is not a rerun
of the earlier 1,260-test full backend suite. Chrome initially found an ambiguous
wrapping-select label; explicit label/control association corrected it without
weakening the browser assertions. Final **50 Chrome check executions passed**
(`phase3_browser_428780bc0bd5`), including all three sizes, cross-member persistence,
mobile overflow checks/screenshots, two-admin stale-size conflict/reload and all
existing workflow/auth/accessibility regressions. These are grouped executions,
not 50 independent scenarios. No external inference calls or browser page errors.
Changes remain local, uncommitted/unpushed; hosted CI has not run this tree.

## Branding sizing and header-name preference — 26 October 2026

Sidebar product logo uses a 180×48px box with existing artwork; authentication
remains 240×72px. Organization header names use 16px medium-weight text. New
admin-only organization-wide visibility preference defaults on; absent/broken
logos always fall back to the name. The organization selector is unchanged.
Preference edits are locked, audited and reject stale expected values (409).

**391 frontend tests passed** (24.65s), lint and production build/TypeScript
passed. **24 focused PostgreSQL backend tests passed** (19.78s, warnings as
errors), covering branding, logos and organization settings. **Two migration
tests passed** (2.65s): real upgrade/rollback/no-op/drift at **0026**, including
the true default for existing organizations. These focused results are not a
rerun of the earlier 1,260-test full backend suite.

**48 Chrome check executions passed** (`phase3_browser_1d7f845e51c6`), including
persisted admin/viewer preference, read-only access, accessibility and existing
workflow regressions. Initial checkbox automation assumed synchronous saving;
it was corrected to click and await persisted state, with assertions retained.
No inference calls. Local changes remain uncommitted/unpushed; no new hosted CI.

## Signed-in branding separation — 26 October 2026

Product branding now appears once in the sidebar; the application header retains
only the selected organization name/company logo (or Platform). Authentication
branding remains unchanged. Header regression tests cover organization identity
with and without a saved company logo.

Fresh **387 frontend tests passed** (28.95s), lint, production build and TypeScript
passed. **47 Chrome check executions** passed (`phase3_browser_547a228290fa`),
including the single sidebar product logo, organization-logo lifecycle, auth
accessibility and existing workflow regressions. Repeated authentication groups
are executions, not distinct scenarios. No AI calls were made. Backend unchanged;
the earlier 1,260 full PostgreSQL tests were not rerun for this UI-only follow-up.
These local changes remain uncommitted/unpushed; hosted CI has not run this tree.

## Authentication presentation — 26 October 2026

One 240×72 product-logo box above a 400px-max card; duplicate text/inner logo
removed. Shared login/register/signup-closed shell, subtitles, 44px controls,
visible focus and underlined footer links. User-supplied SVG artwork unchanged;
compact sidebar/header sizing unchanged. Password/session/signup logic unchanged.

Fresh **385 frontend tests passed** (21.99s), lint, isolated production build and
TypeScript passed. **47 Chrome check executions** passed
(`phase3_browser_fb68af7170c4`), including full-page Axe WCAG A/AA, keyboard entry,
desktop/mobile screenshots and existing app regressions. The two authentication
groups repeat for two admin contexts; these are grouped executions, not 47 unique
independent scenarios. Open-registration presentation uses an intercepted signup-
options fixture only; real signup remains disabled and its closed state is checked.
No account is created by the presentation fixture. Initial Axe failure on a
color-only footer link was corrected with a permanent underline; final run passed
without weakening assertions. Desktop/mobile screenshots were visually reviewed.

No backend changes in this follow-up; prior 1,260 full PostgreSQL tests remain
earlier evidence, not rerun. Demo rebuilt/restarted, retaining data/passwords.
Changes remain uncommitted/unpushed and have not run in hosted CI.

## Replaceable product assets — 26 October 2026

Shared product placements now read `public/branding/product-logo.svg`; root
metadata uses `public/branding/favicon.svg`. The complete wordmark is replaceable
without source edits; aspect ratio/available width and accessible name are retained.
Defaults remain provisional until an approved SVG is supplied. Company logos are
unchanged. Fresh **383 frontend tests** (32.88s), lint and isolated production
build/TypeScript passed. **43 installed-Chrome checks** passed
(`phase3_browser_fb3a96bca5ad`), checking sign-in/sidebar/header image loading,
favicon metadata/serving and the existing organization/workflow/accessibility suite.
SVG structure and tracked-file secret/whitespace/script checks passed.
No backend code changed in this follow-up; the prior 1,260-test backend result
below is retained evidence, not a newly rerun backend suite. Local demo rebuilt;
this uncommitted/unpushed work has not run on hosted CI.
[Asset replacement instructions](PRODUCT_BRANDING.md).

## Organization logos / roadmap cleanup — 26 October 2026

Final local tree: **1,260 full PostgreSQL tests passed in 629.34s**, required
PostgreSQL and warnings as errors. **382 frontend tests passed** (26.05s), lint,
TypeScript and isolated production build passed. **42 installed-Chrome checks**
passed (`phase3_browser_e4adfd001408`), adding real logo persistence/header/viewer,
two-tab stale-write and confirmed-removal flows to the existing suite. The 26
focused checks were an earlier overlapping checkpoint, not an additive total.
Interrupted intermediate runs are not acceptance evidence; final full collection
includes all transport guards and the post-commit response-race regression.

Migration 0025 adds one DB-bounded logo per organization. Test DB round-trip
(head → 0020 → head), metadata drift and no-op checks passed; restored to **0025**,
31 public tables and zero browser schemas. Demo migration/rebuild uses the guarded
`auditmind_demo` preparation workflow, retaining data/passwords. High-severity
Bandit, tracked-file secret guard, explicit new-file pattern review, script syntax
and whitespace checks passed; no further blocking review finding. No dependency
pins, live inference, scoring or saved reports changed in this increment.

This increment is **uncommitted/unpushed**; the previously green hosted baseline
at `c008efc` is not a hosted test of these new changes. Broader Phase 4 hardening
and performance remain pending. [Branding contract / Chrome steps](ORGANIZATION_LOGOS.md).

Latest clean-install/Linux correction: old `httpx` fallback, missing browser
`vector` extension, deprecated Unix `crypt` import and upload-result mobile
overflow corrected without warning ignores or relaxed assertions. Linux backend
**1,244 passed** (331.37s at `4ffee34`); final frontend **377 passed** (58.16s),
lint/TypeScript/production builds and **39 local Chrome checks**
(`phase3_browser_d3a197287cee`). Hosted browser/frontend/security jobs passed at
`f8959ad`; final backend status is tracked in
[run 40376551395](https://github.com/shalisarakkal/AuditMind/actions/runs/40376551395).
Historical 1,241/1,238 and focused results below overlap, not additive totals.
[Compatibility details](BACKEND_DEPENDENCY_REMEDIATION.md).

Hosted CI follow-up: first run at `9720777` passed frontend and security/audit
jobs, but exposed missing dev-only `httpx2` and missing browser database `vector`
extension. Explicit dependency/extension setup and both-client offline guards
correct these clean-install gaps; warnings remain errors. Fresh isolated dev-only
installation passes `pip check` and TestClient import with no optional OpenAI SDK;
39 installed-Chrome checks passed using that environment
(`phase3_browser_0a574e56247f`). Final full-suite/hosted results follow separately;
these initial failures are not treated as hosted acceptance.

26 October final dependency compatibility checkpoint: **1,238 full PostgreSQL
tests passed** in 628.60s with warnings as errors. Earlier **73 focused** and
**14 JWT** results overlap this full run. Fresh **376 frontend tests** (29.03s),
lint, production build and TypeScript passed. **39 installed-Chrome workflow
checks** passed (`phase3_browser_df711584fa08`); **6 Documents grouped checks**
passed separately using intercepted fixtures, not 45 equivalent checks. Core/dev,
optional embeddings and installed-environment audits are clean; `pip check`,
tracked-file secret guard and high-severity Bandit passed. Test database restored
to 0024 with migration round-trip/drift checks clean; demo readiness is healthy.
Hosted CI and live model/vector quality are not certified. This supersedes the
initial dependency blocker in the historical checkpoint below.
[Versions, compatibility and evidence](BACKEND_DEPENDENCY_REMEDIATION.md).

26 October local operations increment: **1,229 full PostgreSQL tests** (651.52s,
warnings as errors), final **20 focused tests** (7.08s), **376 frontend tests**
(21.87s), lint/production builds and **39 Chrome checks** passed. Full collection
preceded the four new secret-guard tests and final schema/hash refinements;
the final focused run covers those changes and overlaps the full run. New code
adds summary/exact-window links, redacted readiness, multi-file/drop import,
product/header branding and portable browser/security CI configuration.
**Backend dependency audit is not green:** 34 advisory entries across six packages.
No ignores/waiver added. CI execution, organization logos and broader hardening
remain pending. See [exact scope, limitations and evidence](PHASE4_LOCAL_OPERATIONS.md).

26 October final check-in review: pending code, regressions, browser script and
documentation reviewed; no blocking finding identified. Fresh pre-push reruns:
**372 frontend tests** (22.19s), lint, normal TypeScript check and **54 focused
PostgreSQL tests** (33.21s, warnings as errors) passed. These focused tests overlap
the earlier **1,218 full-suite** result; no second full backend run is claimed.
Production builds and the **37-check Chrome run** below remain applicable because
only documentation changed after that validated application tree. Disposable test
database restored to 0024 with round-trip/drift checks clean and no leftover
browser schemas. Pending and previously committed outgoing additions passed the
value-redacted secret-pattern scan; staged groups are checked separately before
commit. User authorized push, including the three earlier local commits. Scope
and exclusions: [check-in record](CHECKIN_PREPARATION.md).

26 October Archived/shared lifecycle selection follow-up: **372 frontend tests**
(25.74s), lint, TypeScript/isolated and live production builds passed.
**37 installed-Chrome workflow checks** passed (`phase3_browser_26291a6cb024`),
including two-row Archived selection, disabled row Restore/Purge, fixed-target
modal confirmation, Cancel focus/Escape, scoped Axe, and Assets/Uploads modal and
row-selection behavior. Additional component regressions cover admin bulk purge,
auditor permissions, incompatible states, cancellation and immutable bulk IDs.
Native dialogs prevent background selection changes; no backend contract changed.
The earlier **1,218 PostgreSQL tests** below were not rerun for this frontend-only
increment. Demo restarted with data/passwords retained. No live AI or paid calls.

26 October inclusive deadline validation fix: newly set due/review dates cannot
precede the finding's creation day in the entering browser timezone. Accepted
risk compares the saved UTC expiry against now, allowing today until exclusive
next-local-midnight (rather than rejecting today's calendar date). Kept legacy
deadlines are not backfilled/reinterpreted; bulk validation remains atomic.
Fresh focused PostgreSQL validation: **54 passed** (44.30s), including 15 new
creation/midnight/timezone/bulk regressions. Fresh **367 frontend tests** (23.64s),
lint, TypeScript/production builds and **35 installed-Chrome workflow checks**
passed (`phase3_browser_848f08d422c8`). Chrome now explicitly tests pre-creation
rejection and today's due/review acceptance, without inference or paid calls.
Separate full PostgreSQL regression: **1,218 passed** (637.17s), with
`--require-postgres -W error`; the 54 focused cases are included, not additional.
Demo restarted with data/passwords retained; no migration change, paid calls or
real inference. Live Chrome also rechecked date-input contrast/entry after restart.
Disposable `auditmind_test` restored to revision 0024 after the suite;
upgrade/downgrade/upgrade and Alembic drift check passed, 30 public tables and
zero leftover isolated browser schemas. Demo data was not part of this reset.

26 October date-picker contrast fix: native date inputs now share the dark
color-scheme rule in `globals.css`; the duplicate list-only utility was removed.
Fresh **367 frontend tests** (21.67s), lint and both isolated/live production
builds passed. Targeted installed-Chrome verification confirmed dark native
controls on both Findings date filters and workflow Due/Risk review inputs,
with date entry preserved and no workflow submitted. Screenshot visually reviewed:
`temp/auditmind-demo/date-picker-dark.png`. This targeted check is separate from
the earlier 35-check workflow run; backend tests were not rerun for this CSS-only
change. Demo restarted with data/passwords retained. Shared convention documented.

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



## Multi-user configuration and selected-action follow-up — 25 October 2026

Implemented: selection disables individual Findings Workflow/Archive/Undo until
Clear selection; selected bulk actions retain their eligibility rules. Settings
updates lock and refresh Organization before JSON merge. Profile mutations
serialize case-insensitive name checks and refresh cached parts; consent writes
serialize first creation and subsequent changes. No schema or inference changes.

Validation: **1,187 full backend tests passed in 563.87 seconds**, PostgreSQL
required, warnings as errors. Four further concurrency test cases were added after
that run's collection; the final **7 focused multi-user tests passed in 4.34s**.
These runs overlap: do not add them or claim a newer full-run count. Tests use
separate sessions and distinct admins for settings merge, first consent insertion,
profile name conflicts, cached profile replacement and workflow version conflicts.
**367 frontend tests**, lint, isolated and normal production builds passed.
**35 installed Chrome checks** passed (`phase3_browser_ea1eb15a3a45`), including
row-action disabling, modal inertness and workflow conflicts. A live normal-demo
Chrome smoke passed: select, verify row actions disabled, clear, open/cancel row
archive; no archive write. Demo restarted with existing data/passwords retained.

[Concurrency audit](MULTIUSER_CONCURRENCY.md) describes operation-specific
protection and remaining requirements. This increment is not application-wide
concurrency certification: same-field settings edits remain last-writer-wins,
real-time cross-browser updates are not guaranteed, and universal in-flight
permission fencing/manual-create lifecycle races need further hardening. Common
substring-search performance remains open. No staging, commit or push performed.



25 October archive-confirmation/search follow-up: **367 frontend tests**, lint and
isolated production build passed; **84 focused PostgreSQL tests** passed in
109.79s with warnings as errors, then **17 paging tests** passed in 23.24s after
a whitespace-query regression addition (overlapping runs, not 101 unique tests).
**35 installed Chrome checks** passed (`phase3_browser_6266c82a3ae4`), including
real pointer attempts against the inert archive-modal background. Row confirmation
names one finding/UUID; bulk confirmation freezes selected names/count/IDs. Cancel
is initially focused; cancellation and repeated submission are blocked while busy.
No schema or inference changes. Earlier full backend results were not rerun.
Normal demo production build/restart also passed. A live installed-Chrome smoke
selected a manual finding, opened the new one-finding modal and cancelled without
an archive write. Existing demo data/passwords were retained. The test database
was restored to revision 0023 with 30 public tables, no leftover browser schemas
and a clean Alembic drift check.

**Search performance remains open:** a local SA01 substring count-phase benchmark
improved from 14.419s to 8.052s after replacing the outer asset join and correlated
assignee search with independent match sets. This is one count-only measurement,
not end-to-end latency or performance acceptance. PostgreSQL indexed-search work
is still needed; no index migration was applied.


23 October 2026. Backend, Findings workflow UI and filters verified locally; not a Phase 4 closure or
production/live-AI release. [Contract and delivery boundaries](PHASE4_REMEDIATION_DESIGN.md).

## Implemented

- Finding lifecycle fields with default Open/version zero; optional assignee,
  due date, risk-review date and UTC update timestamp.
- Organization-scoped workflow reads, single PATCH and bounded atomic bulk POST;
  required versions, stale-edit conflicts, strict payloads and validation limits.
- Admin-only accepted-risk changes; auditors can make ordinary edits; viewer and
  platform-only access remain read-only. Active same-org assignment validation.
- Paged append-only API history and transactional Activity recording. Note-only
  PATCH appends history; explicit no-op field updates do not fabricate changes.
- Re-import preserves matching findings. Restore preserves any finding with
  workflow history even when a duplicate exists. Purge cascades history by design.
- Activity label synchronized between frontend and backend.
- Shared list controls/badges, URL-backed status/assignee/overdue filters,
  sortable workflow columns, same-scope counts and private assignee facets.
- Named keyboard-contained workflow dialog with explicit keep/set/clear changes,
  paged assignee search/history, read-only roles, accepted-risk note restrictions,
  draft preservation and mandatory refresh after conflicts/uncertain outcomes.
- Action-specific selection: imported findings can be remediated, not manually
  archived. Workflow selection is capped at 100 and clears on scope changes.
- Scroll-contained wide table and viewport-sized dialog; shared frame contains
  screen-reader-only absolute labels without expanding the document.
- Alembic 0022 adds fields/history. Initial acceptance used isolated test schemas;
  the later approved demo rollout is recorded below. The normal schema is unchanged.

## Verification checkpoints

Latest UI/filter follow-up:

- **1,153 full backend tests passed in 604.43 seconds** on PostgreSQL, warnings
  as errors and PostgreSQL required. This supersedes the earlier backend-only
  1,146-test checkpoint for this worktree, not its historical sign-off context.
- **323 frontend tests passed**, plus lint, TypeScript and the isolated production
  build. Ten focused UI tests cover dialog/list behavior; 33 focused PostgreSQL
  workflow/filter/paging regressions ran before the final full suite.
- **19 installed Chrome 155.0.8059.85 checks passed** against real frontend/API
  and an isolated PostgreSQL schema, including real 409 conflicts and atomic bulk
  rollback, all lifecycle states, risk approval validation, read-only/foreign roles,
  interactive filters/refresh, history paging, selection bounds/reset and tenant switching.
- Axe WCAG 2 A/AA and 2.1 AA checks passed for the desktop/mobile dialog and desktop
  Findings page. Screenshots reviewed; document width equals the 1440px desktop
  viewport, with a separate 390px mobile document-overflow assertion. This is
  automated/scoped acceptance, not an exhaustive accessibility audit.
- Chrome artifacts: `temp/testing/finding-workflow/phase3_browser_26a1a1431f90/`
  (`results.json`, desktop/mobile screenshots and service logs). Zero browser page
  errors and zero AI usage records. Isolated processes/schema cleaned afterward.

Earlier backend-only checkpoints (historical):

- 23 focused workflow/schema/concurrency/restore checks passed with PostgreSQL
  required and warnings treated as errors. This includes duplicate import,
  history-preserving restore and intentional purge cleanup.
- Initial expanded archive run: 54 passed, one assertion failed because an extra
  duplicate import changed asset sharing. Corrected the expected duplicate count;
  the dedicated restore test then passed in the 23-check focused run.
- Two overlapping public disposable-DB test invocations were stopped and excluded
  from acceptance evidence. Public-schema suites subsequently ran sequentially;
  browser acceptance uses separate, explicitly named schemas with translated FKs.
- 313 frontend tests, lint and production build (including TypeScript) passed.
- **1,146 full backend tests passed in 576.91 seconds**, PostgreSQL required,
  warnings as errors, no skipped-test acceptance. Command from `backend`:
  `.\.venv\Scripts\python.exe -m pytest --require-postgres -W error -q --tb=short --show-capture=no`.
  This was the backend-only full-suite result, distinct from the earlier 23 focused checks.
- Empty database to 0022, downgrade to 0020 and upgrade back to 0022 passed.
  Populated 0021 to 0022 to 0021 to 0022 also passed: existing source text
  preserved, status/version defaults correct, no fabricated history.
  Alembic drift checks found no new operations. Disposable `auditmind_test` left
  at 0022, 30 public tables, no remaining isolated browser schemas. Normal/demo
  databases were not migrated. Downgrade intentionally drops workflow/history.
- No new coverage percentage or load/soak acceptance is claimed.

## Approved demo rollout — 23 October 2026

- Stopped the owned demo services, upgraded only `auditmind_demo` from 0021 to
  0022, and passed Alembic's no-drift check. Rebuilt the normal demo production
  frontend (including TypeScript) and restarted API, worker and frontend.
- Before/after row counts and server-side content checksums matched for four
  users, 3,768,108 findings, 2,571,702 assets and 12 reports. Every existing finding
  has default Open/version zero. No passwords were reset. Normal `public` schema
  structure and revision 0020 remained unchanged.
- Installed Chrome checked the live demo's Findings page, editable workflow
  dialog and Escape dismissal with no page errors; screenshot reviewed at
  `temp/auditmind-demo/workflow-ready.png`. No workflow writes were made.
- Existing synthetic-report browser regression passed all 14 checks, including
  saved views/exports. These are additional demo smoke checks, not a rerun of the
  full 19-check isolated Phase 4 acceptance suite described above.
- Demo browser checks used a temporary server-created admin session, removed
  afterward. This does not establish password-login acceptance. Existing account
  credentials are unchanged. External inference remains disabled; no paid calls.
- Demo ready at `http://localhost:3000`; select **AuditMind Demo - Synthetic Data**
  and open **Findings → Workflow**. No commit or push was performed.

## Review notes

### Compact local-time display and shared full-day date filters

Removed repeated original-zone/IANA details from current deadlines, list cells and
history. One signed-in layout notice states times are browser-local. Deadline
metadata/storage remains unchanged; visible timing changes still appear in history,
while equivalent timezone aliases do not produce identical before/after arrows.

Shared since/until date controls are unchanged. The list hook sends browser
`filter_timezone` only when a date bound is present. Common DateRange processing
uses inclusive local 00:00 and exclusive next-local-day 00:00, covering the entire
11:59 PM minute, including microseconds and 23/25-hour DST days. Empty endpoints
remain unbounded; invalid zones/reversed/impossible ranges fail closed. All existing
date-filter screens use this common path; direct API callers without the new query
parameter retain UTC compatibility. No migration or new time-control GUI is added.

Initial focused checkpoint: **25 date-range/paging tests passed**. Frontend first
full run exposed a pre-existing timing assumption in an import-tracking test: its
report could render before a passive reload effect ran. The assertion now waits
for that effect, with no runtime change. Subsequent full frontend run passed all
**334 tests**. Final full backend and Chrome totals are recorded after completion.

Final checkpoint: **1,182 full PostgreSQL tests passed in 556.13 seconds**, warnings
as errors and PostgreSQL required; **334 frontend tests**, lint, TypeScript and
isolated production build passed. **26 installed Chrome checks passed**, including
compact cross-zone deadline display without raw zone IDs, the shared notice and
date-only controls transmitting the requesting browser's timezone. Existing
workflow/permissions/conflict/bulk/archive and scoped Axe regressions passed.
Artifacts: `temp/testing/finding-workflow/phase3_browser_d1a4f230b788`.
The earlier 25 focused checks are a subset; earlier full-run counts remain historical.
Test DB restored to 0023 with 30 public tables, zero browser schemas and clean drift.
Normal demo production build/TypeScript passed; owned services restarted. Live-demo
Chrome smoke confirmed the shared notice and absence of raw timezone IDs in Workflow,
plus history/Add dialogs. Existing 14 mock report view/export checks also passed
separately. Screenshots visually reviewed. Temporary sessions removed; no demo
workflow writes, data rewrite, passwords, inference, commits or pushes changed.

### Browser-authored deadline timezone correction

Supersedes the fixed-Eastern rule for new date writes. Browser detects its IANA
timezone and sends it only with explicitly set dates. API requires that zone;
invalid/missing zones and timezone-only writes are rejected. Each due/review date
retains its own original zone and fixed exclusive UTC expiry. Keep/note/assignment
edits preserve expiry; Clear removes date metadata. Overdue and sorting use actual
expiry, not the current viewer/server's calendar day. Displays show original date/zone
plus the final instant of the selected day in the viewer's browser timezone.

- **1,173 full PostgreSQL backend tests passed in 522.38 seconds**, PostgreSQL
  required, warnings as errors. Supersedes the 1,164-test checkpoint below.
- **331 frontend tests passed**, plus lint, TypeScript and isolated production build.
- Migration 0023 empty upgrade and populated 0022 → 0023 → 0022 → 0023 passed
  with clean drift, preserved source/workflow version, and summer/winter legacy
  Eastern backfill boundaries. Downgrade is only tested on disposable legacy data;
  it loses authored-zone metadata and is not a safe production rollback promise.
- New tests cover Kolkata's half-hour offset, Pacific viewing, New York DST,
  invalid zones, a skipped local day, required author zones, fixed expiry through
  note edits, metadata clearing and same-instant overdue comparisons.
- Initial API test exposed PostgreSQL's session-local offset representation;
  normalized workflow snapshots to UTC to avoid false no-op/history differences.
  All 48 focused checks passed after that fix; the later strict missing-zone test
  is included in the final full suite. First timezone Chrome assertion assumed
  Kolkata's spelling; Chrome reports the valid alias Asia/Calcutta. Assertion now
  checks the detected browser zone and its actual UTC boundary, not one spelling.
- Final installed Chrome rerun passed **25 checks** against the strict author-zone
  API; artifacts: `temp/testing/finding-workflow/phase3_browser_c9562c6d79ce`.
  Test target restored to 0023, 30 public tables, zero browser schemas, clean drift.
- Final migration backfill was simplified to one table scan; populated round-trip
  and drift checks passed again afterward. Demo services stopped for rollout;
  schema upgraded 0022 → 0023. Before/after account/deadline digests and row counts
  matched: four users, 3,768,108 findings, 2,571,702 assets, 12 reports, 102 history
  entries. Zero incorrect legacy backfills. Normal public revision/structure unchanged.
- Normal demo production build (including TypeScript) passed; API, worker and
  frontend restarted. Live-demo Chrome smoke verified detected browser timezone,
  Workflow/history and Add finding dialogs without writes. All 14 existing mock
  report view/export checks also passed; these are additional demo regressions,
  not part of the 25 isolated workflow checks. Temporary sessions removed. No
  passwords, credentials, real inference, commits or pushes changed.

### Settings/import reconciliation design review

Read-only review traced all three asset-existing strategies through the asset-row
and finding-only publishers, duplicate identity and archive matching. SA01's demo
effective strategy is update, with no organization override; nothing changed.
Added the behavior matrix, duplicate-payload/provenance limitations and recommended
canonical-observation/suppression compatibility rules to
[the design-only proposal](FINDING_RECONCILIATION_DESIGN.md).
**49 focused PostgreSQL/import-matching tests passed in 34.69 seconds**, warnings
as errors. The prior 1,164 full-suite checkpoint remains historical, not rerun here.
Test target restored to 0022, 30 public tables, zero browser schemas, clean drift.
Documentation-only changes: no import/settings behavior change or demo restart.

### Manual finding entry and Eastern deadlines follow-up

Manual entry uses the existing role/organization-scoped creation API, source manual,
and no scan ID. The UI preserves drafts on failures and blocks automatic retries
of uncertain creation. Organization facets indicate active manual findings; archive
availability is contextual, while imported findings remain upload/asset archived.
Shared sort arrows no longer shrink and risk-review heading width is increased.

Finding deadline comparisons and risk-date validation now use America/New_York.
The existing date-only values are interpreted in Eastern time, including DST;
no data rewrite/migration or inference is required. tzdata is explicitly pinned
for Windows installations. Mandatory rationale remains unchanged by user choice.
Imported-finding archive/reconciliation is design only by explicit user choice;
see [proposal and gates](FINDING_RECONCILIATION_DESIGN.md).

Initial focused checkpoint: 39 PostgreSQL/unit tests and 329 frontend tests passed,
plus lint and isolated production build. Later tests add Eastern overdue API
boundary coverage and uploaded-only archive UI behavior; final totals follow.
Existing complete browser run passed 22 checks, including UI create/archive;
final browser rerun additionally checks sort-arrow geometry and disabled archive
guidance. No claim is made that these interim results replace the full suite.

Final checkpoint:

- **1,164 full PostgreSQL backend tests passed in 538.45 seconds**, PostgreSQL
  required and warnings as errors. This supersedes the earlier 1,153 full run;
  initial 39 focused checks above are a subset, not an additional full run.
- **330 frontend tests passed**, lint, TypeScript and isolated production build.
  New tests cover manual creation payloads, uncertain-write retry prevention,
  uploaded-only archive availability and Eastern midnight/DST comparisons.
- **24 installed Chrome checks passed**, including UI manual create/archive,
  reachable final-heading arrow, unavailable-archive guidance, existing workflow
  conflicts/atomic bulk and scoped Axe checks (including the new Add dialog).
  Artifacts: `temp/testing/finding-workflow/phase3_browser_a085869202fe`.
- `pip check` passed. Test DB restored sequentially after browser cleanup: 0022,
  30 public tables, zero browser schemas, clean Alembic check. No new migration.
- Reviewed role gates, organization-scoped manual eligibility, no scan provenance
  override in the form, unknown-create retry blocking, fixed Eastern comparisons,
  unchanged mandatory notes, and design-only imported reconciliation boundaries.
- Demo rollout initially stopped on a test-only TypeScript error: Testing Library's
  getByRole options do not accept Playwright's `exact` option. Removed that option,
  reran all 330 frontend tests, and passed the normal production build including
  TypeScript. Owned API/worker/frontend restarted successfully. Live-demo Chrome
  smoke opened Workflow and Add finding, checked history navigation and dismissed
  both dialogs without writes. Temporary session removed; passwords/data preserved.
  No external inference, paid calls, commits or pushes; normal schema unchanged.

### Saved-note summaries and readable history follow-up

- Added independent latest-rationale/latest-verification summaries with author/time,
  clear new-entry labels and explained internal technical finding UUIDs.
- History hides unchanged workflow fields, identifies note-only entries and uses
  captured assignee name/email labels for new records. Legacy labels use only
  active same-org lookup, otherwise unavailable; technical IDs remain expandable.
  Existing audit snapshots are not rewritten, and no migration is required.
- **327 frontend tests**, lint, TypeScript and isolated production build passed;
  **30 focused PostgreSQL tests passed in 16.20 seconds**. The earlier full
  1,153-test run is not a new full backend run of these changes.
- **21 installed Chrome checks passed** with scoped accessibility checks;
  artifacts: `temp/testing/finding-workflow/phase3_browser_f99119a6b1b9`.
  New unit/integration assertions cover summary attribution, older verification
  preservation, changed-field rendering, label capture across renaming, email
  fallback and unavailable legacy assignees. PostgreSQL test target restored
  sequentially to 0022, 30 public tables, zero browser schemas and clean drift.
- Rebuilt/restarted the owned demo and passed live-demo Chrome smoke for both
  latest-note headings and history navigation, with no workflow writes. Updated
  the temporary smoke's old input-label expectation to the new Add wording and
  waited for summary loading; initial outdated-label failure was not acceptance.
  Session cleanup retained; no credentials, paid calls, commits or pushes changed.

### Note discovery and mixed-selection follow-up

- Added saved-notes/history navigation with a truthful current-page count,
  labelled saved rationale/verification and explicit new-entry guidance. Kept
  the existing paged history API and mandatory-note contract unchanged.
- Bulk dialog shows current status counts. Risk-date Set/Clear options depend
  on every target's resulting status; an incompatible retained draft blocks
  submission. No implicit status change, subset update or silent action removal.
- **326 frontend tests passed**, including ten dialog tests; lint, TypeScript and
  isolated production build passed. **29 focused PostgreSQL tests passed** in
  15.24 seconds (workflow integration/filter and unit/policy files). This is not
  another full backend run; the earlier 1,153-test checkpoint remains historical.
- **21 installed Chrome checks passed**, including new mixed-state and saved-note
  navigation checks, existing real conflicts/atomic bulk regression and scoped
  desktop/mobile Axe checks. Artifacts:
  `temp/testing/finding-workflow/phase3_browser_3315b0609ed4`.
- First Chrome attempt stopped because Playwright's option enabled-state matcher
  did not recognize the native disabled option despite its disabled attribute;
  corrected the assertion to inspect that attribute and reran all checks.
- Test-target restoration was first checked while the browser schema was still
  active; the zero-browser-schema assertion correctly failed. After Chrome cleanup,
  reran restoration sequentially: revision 0022, 30 public tables, zero browser
  schemas, clean Alembic check. No demo or normal data was reset.
- Optional rationale on assignment/date-only edits is a documented proposal,
  not an implemented policy change. No inference or paid calls were made.
- Final review removed a misleading plus suffix from the current-page history
  count; all ten dialog tests passed again. Rebuilt the normal demo frontend with
  TypeScript, restarted owned services and passed live-demo Chrome smoke including
  the history shortcut's keyboard focus. Temporary test session removed afterward;
  no workflow writes/password resets. Existing demo schema remains 0022.

Targeted review covers tenant scoping, existing archive/job/advisory lock order,
fresh role and finding-version reads, two-phase bulk validation before writes,
same-transaction history/events, payload limits and no score/source mutation.
Concurrent edit regression uses two independent PostgreSQL sessions: one update
succeeds and the other receives 409. This is not exhaustive race/load testing.

Finding-list filters, assignee pickers, workflow dialogs, bulk UI and the scoped
Chrome checks above are now implemented and verified. Dashboard security summary,
readiness/security hardening, performance and CI expansion remain Phase 4 work.
Duplicate consolidation, status-aware scoring and provider inference remain out
of scope. Existing Phase 3 Chrome evidence is historical, not new Phase 4 evidence.

No credentials, external consent, paid calls, commits or pushes are changed by
this increment. `cline.json` remains unrelated and untouched. Requested named
skills are unavailable; development/review disciplines are applied directly.

## Reproduce Chrome acceptance

### Unified Findings row/bulk actions — 25 October 2026

Removed Select for mode. One cross-page selection supports up to 500 findings;
workflow remains capped at 100 and is disabled above that count. Archive selected
requires all-manual available targets, with explicit mixed-selection guidance.
Selection retains UI-only metadata across pages; backend eligibility/authorization
remains authoritative. Bulk archive confirmations freeze IDs/names/counts and show
explicit backend refusals for concurrent changes, not silent skips. Completed jobs
clear stale selections. Workflow and eligible manual Archive now share a labelled,
sticky-right Actions column, independent of checked rows; viewers retain read-only
Workflow without mutation/selection. Narrow-screen Actions wrap within their column.

Passed: **365 frontend tests**, lint, TypeScript/isolated production build;
**67 focused PostgreSQL archive/workflow integration tests in 66.96 seconds**,
warnings as errors; **35 installed Chrome checks** with real frontend/API/test
PostgreSQL and an isolated worker. Artifacts:
`temp/testing/finding-workflow/phase3_browser_23462f490926` (ignored).
Coverage includes cross-page eligibility, mixed-selection denial, 100/500 limits,
frozen confirmation targets, multi-row manual archive completion, independent row
Archive, sticky action visibility, role/tenant boundaries and existing regressions.

The new queued-bulk acceptance required adding a worker to the isolated fixture.
The timer check was isolated from older grouped success notices; a pending promise
was replaced by a captured request so a failure cannot interrupt fixture cleanup.
The failed run's synthetic schema was explicitly removed; no demo data was reset.
The 500-selection unit check exercises the hook instead of rendering 501 rows at
once. The earlier full backend and document-specific browser runs remain historical,
not summed with this focused evidence. No backend behavior/schema or inference changed.
Test DB restored to 0023 with clean drift and zero browser schemas. Normal production
build/TypeScript passed; demo rebuilt/restarted with data/passwords preserved. Live
Chrome verified unified bulk controls and sticky independent row Archive, then
cancelled its confirmation without submitting an archive. Temporary diagnostic
session removed. Screenshot: `temp/auditmind-demo/finding-actions-ready.png` (ignored).

### Inline document previews — 25 October 2026

Documents and platform Shared standards now follow Uploads → Report: Preview vN
expands a named panel directly below the owning row, with title/version/edition,
correct column span, Hide preview toggle and Close preview. One preview at a time;
scope changes close it. Loading and errors/retry are local to the panel, independent
of write actions/list reloads. Switching/unmounting ignores old responses. Removed
versions have disabled preview controls; existing read authorization stays server-side.
Content is plain text, with wrapping, bounded scrolling and keyboard focus support.

Passed: **362 frontend tests**, lint, production build/TypeScript;
**6 focused PostgreSQL document integration tests in 13.30 seconds**, warnings as
errors; **6 grouped Chrome checks across viewer/admin/platform scenarios**, using
intercepted synthetic API fixtures. Checks include inline placement, span, toggle,
focus restoration, retry, switching documents, mobile long text and scoped Axe AA
with previews both open and closed. The first expanded-preview accessibility run
found a non-focusable scroll area; fixed and rerun with zero reported violations.
Artifacts: `temp/auditmind-demo/browser/documents-ui.json` and
`documents-{viewer,admin,platform}-preview*.png` (ignored).

Additional live-demo Chrome smoke passed real saved-text preview placement/close
without document writes, consent changes or inference. Screenshot:
`temp/auditmind-demo/document-preview-ready.png` (ignored). Owned demo services were
rebuilt/restarted with data/passwords preserved; temporary session removed. Test DB
restored to 0023 with clean drift and no browser schemas. No backend code or migration
changed. Earlier full backend and 34-check workflow Chrome runs remain historical,
not rerun or summed with this document-focused evidence.

### Job-notice timing and Settings width — 24 October 2026

Routine completed archive/restore/purge notices use a shared 10-second visible
timer. Hover, keyboard focus, hidden tabs and offscreen notices pause the timer.
Only routine successes auto-dismiss through the existing server endpoint, with
background activity headers to avoid extending idle sessions. Failures, running
or interrupted jobs, restore warnings (kept findings/duplicates purged), and mixed
groups remain manual. A failed auto-dismiss shows an error and does not loop;
manual retry remains available. Upload reports are deliberately unchanged.

Settings now uses full available content width and the shared header. Ingestion
controls and mapping selectors wrap/constrain on narrow screens. No setting values,
permissions, save rules, archived data or Activity history are changed.

Passed: **357 frontend tests**, lint, TypeScript/isolated production build;
**45 focused PostgreSQL archive/boundary integration tests in 61.35 seconds**,
warnings as errors; **34 installed Chrome checks**. Artifacts:
`temp/testing/finding-workflow/phase3_browser_95e81950ed2b` (ignored), including
desktop/mobile Settings screenshots. Reviewed desktop screenshot. Initial Chrome
run found a retention-control mobile overflow, corrected before the passing run.
Fake-clock tests cover timing boundary, hover/focus/tab/viewport pauses, rerenders,
failures and manual retry, warnings, grouping, cleanup and safe fallback without
IntersectionObserver. Chrome verifies real background dismissal persistence across
navigation/refresh and desktop/mobile width. No browser page errors or inference.
The prior full backend run remains historical; this is focused regression evidence.
Test DB restored to 0023 with clean drift and no remaining browser schemas.
Normal production build/TypeScript also passed. Rebuilt/restarted owned demo
services with data/passwords preserved; live-demo Chrome confirmed full Settings
desktop width and no mobile page overflow without settings writes. Temporary
diagnostic session removed; screenshot `temp/auditmind-demo/settings-ready.png`
is ignored. No paid calls, credentials, commits or pushes changed.

### Copy-success message timeout — 24 October 2026

Finding-ID copy success now dismisses after 3 seconds. Repeated successful copies
restart the timer; failures remain visible and cancel a prior success timer.
Unmounting clears pending timers. **347 frontend tests** and lint passed, including
fake-clock regressions for the 2,999/3,000 ms boundary, repeated copy, persistent
errors and cleanup. This presentation-only follow-up does not rerun backend tests
or replace the earlier 32-check browser acceptance evidence.
Normal production build/TypeScript and live-demo Chrome smoke also passed,
including timed dismissal after copying. Demo rebuilt/restarted; data/passwords
preserved and the temporary diagnostic session removed. No inference or workflow writes.

### Finding-ID traceability — 24 October 2026

Findings rows expose an expandable Finding ID and copy action without another
table column. Complete UUID search uses exact identity, avoiding text/asset scans;
`finding_id` is also a validated exact API filter. Counts, active-row exclusion
and tenant scope use the same predicate. Partial text remains normal text search.
Workflow technical finding IDs, report evidence/remediation finding references
and organization Activity workflow-change items link through an access-checked
organization resolver before opening the exact Findings filter. Asset/upload IDs
are not inferred to be finding IDs. History and report snapshots are unchanged.
Archived/purged/missing references can produce an empty active list.

Passed: **344 frontend tests**, lint, TypeScript/isolated production build;
**39 focused PostgreSQL integration tests in 70.05 seconds**, warnings as errors;
**32 installed Chrome checks**. Artifacts:
`temp/testing/finding-workflow/phase3_browser_12035cdc3efa` (ignored).
Tests cover copying/refusal, exact versus mentioned UUIDs, counts, archived-row
exclusion, foreign-tenant denial, access-checked context switching, refresh,
report links, known Activity references and malformed links. An initial browser
attempt looked for a paged-out Activity entry; corrected to filter its item. A
later selector was narrowed to distinguish the Next route-announcer alert.
Final rerun passed with no page errors or inference usage. Test DB restored to
0023 with clean drift and zero remaining browser schemas. The earlier 1,182-test
full backend run is historical; the 39 tests above are a focused rerun.
Normal demo frontend was rebuilt and owned services restarted without migration
or password/data reset. Additional live-demo Chrome smoke passed ID expand/copy,
exact-link navigation, single-row result and refresh without workflow writes;
temporary diagnostic session removed. Screenshot:
`temp/auditmind-demo/finding-reference-ready.png` (ignored).

### Identity-only assignee search — 24 October 2026

The member API now accepts validated `search_scope=identity` for name/email-only
search; its default `all` retains People-page role/status matching. The workflow
picker explicitly uses identity scope. Existing tenant, status and pagination
filters still apply. Searching `admin` no longer matches a person solely because
their organization role is Admin; matching email addresses still legitimately match.

Passed: **337 frontend tests**, lint, TypeScript/isolated production build,
**38 focused PostgreSQL integration tests in 43.56 seconds** (warnings as errors),
and **28 installed Chrome checks**. Browser artifacts:
`temp/testing/finding-workflow/phase3_browser_c727db4f4142` (ignored).
Coverage includes the Shali/Active Admin case, broad People-search compatibility,
case-insensitive name/email matching, invalid scopes and tenant isolation.
This focused backend run does not replace the earlier 1,182-test full run.
No migration, inference, password changes or workflow data edits are required.

Live SA01 Chrome verification after normal build/restart returned Shali for
`shali`. `admin` still returned both Active Admin and Shali Arakkal: the latter's
email contains `admin`, even though her name does not. Confirmed identity scope
on the actual request and checked every result matches name or email. The earlier
explanation attributing this result solely to role matching was incomplete.
Temporary diagnostic sessions were removed; no assignments or passwords changed.

### Assignee-history/search correction — 23 October 2026

Removed the separate technical-assignee section that bypassed unchanged-field
filtering. Raw user UUIDs remain in audit data, not dialog text. Current owners
and actual assignment changes use names/email, with an unavailable fallback.
Find assignee searches same-organization eligible members; search alone does not
write workflow changes. Added guidance, explicit empty results, whitespace-name
email fallback and retained selected labels while results change.

Verification: **337 frontend tests**, lint, TypeScript/production builds;
**37 focused PostgreSQL integration tests in 42.69 seconds**, warnings as errors;
**28 installed Chrome checks**, including real member search and status-only
history without unchanged owners/user UUIDs. Artifacts:
`temp/testing/finding-workflow/phase3_browser_a872acdeae63` (ignored).
The earlier **1,182-test full backend run** is historical evidence, not rerun or
combined with this focused result. No backend behavior/schema, inference,
passwords, commits or pushes changed.

### Commands

Use a dedicated PowerShell session, installed Chrome, dependencies and configured
local `auditmind_test`. Ports 3014/8012 must be free. From `frontend`:

```powershell
$env:AUDITMIND_ISOLATED_BUILD = '1'
$env:BACKEND_URL = 'http://127.0.0.1:8012'
$env:NEXT_PUBLIC_API_URL = '/api/v1'
npm.cmd run build
```

Then from the repository root: `node scripts/browser-finding-workflow.cjs`.
The build uses ignored `.next-acceptance`, leaving a running demo's `.next` chunks
alone. The fixture refuses nonlocal/non-test database targets, creates synthetic
accounts and a uniquely named schema, disables external credentials/HTTP and never
requests inference. It cleans only its own schema/processes; artifacts remain ignored.
No real account passwords are needed or changed. Close that dedicated shell after
testing so acceptance-only environment values do not affect normal development.

## Evidence reviewer UI follow-up — 27 October 2026

### 28 October real HTTP and two-user acceptance

The live local Chrome/Next/API checks completed four full SA01 evaluations:
116.524/110.537 s sequentially and 135.653/133.253 s simultaneously. Each processed
all 6,374,205 records, returned identical fingerprints and left inventory/AI usage
unchanged. This is repeated local-cache evidence, not controlled cold-cache or
production acceptance. Artifact: `temp/testing/evidence-http/ac002e283bcb407b6e722576`.

Cancellation during database work exposed a retained idle transaction. The route
now explicitly closes its synchronous snapshot iterator in shielded response
cleanup. Two real PostgreSQL/ASGI disconnect tests pass, covering disconnect-task
cancellation and send failure. Live post-fix cancellation restores the UI in
38.9 ms and releases the reader after its current fetch, ~27.8 s including polling.
Artifact: `temp/testing/evidence-http/447bbaf0ba1f93a7628b3de7`.
This is not an immediate database statement cancellation. Demo services were
restarted only after verifying no import/report/archive jobs; existing data and
account passwords were retained.

`node scripts/browser-evidence-acceptance.cjs` passed **six focused Chrome checks**
against its own local test schema with 100,000 synthetic assets. Two independent
admins submit the same saved-version approval concurrently: exactly 200/409;
the losing browser keeps edits and deliberately reloads version 2. The suite
checks partial eligibility without Dashboard changes, server-enforced viewer and
auditor read-only roles/foreign-tenant denial, real inventory-write overlap
(91.8 ms write completion during a 1,705 ms scan), snapshot consistency, subsequent
stale-binding rejection, revoke/rebind/material conflict and no native warnings,
page errors, scoring activation or inference. Its schema/processes/accounts were
removed. Artifact: `temp/testing/evidence-review/phase3_browser_3ddd814e9605`.
These six scenarios are not a rerun of the historical full browser suite.

Opt-in repeat commands: `node scripts/browser-evidence-http.cjs` against the idle
running demo, or `--cancel-only`; then the isolated reviewer command above.
Build `.next-acceptance` first with the documented isolated environment values.
Do not overlap isolated acceptance with public-schema PostgreSQL test suites.

Latest frontend recheck: **456 tests**, ESLint and isolated production build /
TypeScript pass. High-severity Bandit for the evidence route/service also passes.
Fresh full PostgreSQL run: **1,335 passed in 753.92 s**, zero failures/errors/skips,
using `python -m pytest --require-postgres -W error -q
--junitxml=../temp/testing/evidence-backend-20261028.xml` from `backend`.
The two disconnect regressions are included in that total, not additive. The
disposable test database was restored to migration **0030**, 33 public tables,
with no Alembic drift. `pip check`, tracked/new task-file secret checks and
`git diff --check` passed. No push or fresh hosted CI claim; the subsequently
approved local check-in is recorded below.

Review scope included qualification authorization/tenant boundaries, optimistic
versions and write admission, inventory/source integrity and repeatable reads,
expiry/downgrade handling, stream disconnect/error cleanup, browser confirmation
ownership and unchanged default-off scoring/report behavior. The cancellation
transaction leak discovered by real-service testing was corrected, regression
tested and rechecked in Chrome. This is a scoped code/acceptance review, not a
claim of an independent security audit or production load certification.

Approved local check-in boundaries (28 October; not pushed):

1. `0191f85` Backend registry/review/evaluator: migrations 0029/0030, models/schemas/routes,
   registration, fingerprint/progress cleanup and PostgreSQL regressions.
2. `aeb62a8` Settings reviewer: evidence component/tests, versioned actions/application
   confirmations, operation-local progress, stream client/parser and tests.
3. `0f4acb1` Presentation-only follow-ups: report print/filter contrast, local timestamps,
   known scope/enum labels and shared sentence-case headings with tests.
4. This acceptance/documentation commit: opt-in HTTP/reviewer harnesses, guarded fixtures,
   recorded results, verification instructions and roadmap state.

Exclude `.env`, `SIGN_IN.txt`, test artifacts, generated builds/type paths,
unrelated `cline.json` and unapproved/untracked branding assets. A future approved
push still needs hosted CI verification for its own SHA; `ceef079` is historical.

28 October contextual-progress follow-up: 456 frontend tests, lint/TypeScript
and production build passed. Twelve focused Chrome checks passed
(`phase3_browser_58598e808b6e`), including evaluation progress inside its own
section and inventory-loading status/Cancel inside domain qualification.
Held-stream tests verify Cancel remains enabled while editing is locked, errors
stay in the owning area and cancellation returns control without partial results.
The current demo evaluation was not interrupted; the restart occurred after no
active cursor requests/background jobs remained. No backend/scoring changes or
new full-backend/full-browser acceptance are implied.

Application-confirmation follow-up: 454 frontend tests, lint/TypeScript and
production build passed. Eleven focused Chrome checks passed
(`phase3_browser_9991cf55fa21`), including app-styled discard confirmation,
Cancel-first focus, Escape preserving edits/restoring focus, confirmed reload,
no browser warning and a clean Axe scan. Evidence review/conflict/revocation
also use app confirmations; component tests assert no write before confirmation
and frozen expected-version payloads. The Settings purge-log link now has an
underline after the Axe check flagged color-only identification. No backend,
authorization or scoring-rule change; no new full-backend run is claimed.

Scope/reload UX follow-up: 451 frontend tests and lint passed; production build
passed. Ten focused installed-Chrome checks passed (`phase3_browser_ac90e6cbc152`),
including the separate organization-wide evaluation section and fresh read-only
reload without a discard popup. Component coverage verifies clean reload, latest
server version, Cancel preserving edits, failed reload preserving edits and
confirmed discard. Evaluation preserves unsaved editor content and ignores it
when checking saved organization evidence. No backend/scoring/authorization rule
changes or new full-backend/full-browser run are implied.

Performance/progress follow-up: 49 focused PostgreSQL qualification tests and
447 frontend tests passed; lint and production build passed. After releasing the
authorization read transaction before streaming, 3 focused stream tests also
passed (overlapping, not additive). Tests cover whole-snapshot reads, nested JSON
change detection, ordering stability, old-version rejection, explicit stream
errors/truncation/cancellation and unchanged scoring. No new full-backend run is
claimed. SA01 measurement and controlled-benchmark caveats are recorded in
[performance detail](EVIDENCE_EVALUATION_PERFORMANCE.md).
Nine focused installed-Chrome checks passed (`phase3_browser_b32ac6b0ca49`),
including a nonempty synthetic inventory, visible progress bar reaching the
actual total, versioned draft save and unchanged scoring. This is not a new
full browser suite. High-severity Bandit checks passed for the changed backend
route/service. The disposable test database was restored to migration 0030.

Subsequent display-only casing/time increment: 442 frontend tests and lint passed;
production build passed. Nine focused installed-Chrome checks passed, including
browser-local Captured time, sentence-case report heading, explicit UTC scope
explanation and retained report-only printing (`phase3_browser_6becbf62a66e`).
Shared table/filter/section all-caps transforms were removed; report/page labels
and known risk enums use sentence case. Names, acronyms, original authored text,
technical provenance, saved date boundaries and downloadable exports are unchanged.
The demo restart retained data/accounts. No backend behavior or inference change.

Subsequent report-print increment: all 439 frontend tests passed (including 15
focused ReportViewer tests); lint and production build passed. Nine focused installed-Chrome checks passed
(`temp/testing/finding-workflow/phase3_browser_5a7fd04a2664`), including report-only
print media, hidden application navigation/actions, all-priority content despite
screen filtering, black print text and restoration of screen filtering. Generated
Chrome PDF is retained in that ignored artifact folder. These focused checks
overlap earlier browser checks; they are not an additional full-suite run.

Settings reviewer preview: 437 frontend tests passed (including 3 new component
tests for default-off/explicit expensive reads, versioned draft save and read-only
roles). TypeScript, lint and production build passed. Demo upgraded to 0030 and
restarted after confirming no pending/running imports, archive jobs or reports.
No inference calls. This does not replace the earlier 1,327 full backend run / 55
focused backend follow-up. Nine focused installed-Chrome checks passed, including
the reviewer draft/inventory/evaluation path; artifacts:
`temp/testing/finding-workflow/phase3_browser_fb17678b8ea6`.
This is a focused run, not a rerun of the full 71-check browser suite or exhaustive
approval/revocation browser acceptance.
Dashboard scoring integration and performance acceptance remain pending.
