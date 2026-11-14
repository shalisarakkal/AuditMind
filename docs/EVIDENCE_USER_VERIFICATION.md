# Verify the evidence-aware reporting changes

## 13 November: manual acceptance deferred; next engineering scope

- [ ] Complete the [manual consolidation acceptance walkthrough](CONSOLIDATION_CHROME_WALKTHROUGH.md)
  in a test organization. **TODO, deferred at the user's request**; the complete
  manual flow has not been signed off. No user testing is required now.
- [x] Automated verification remains complete: local/hosted Chrome, backend,
  frontend and security checks passed; local schema activation is at `0055`.
  This is separate from manual user/pilot acceptance.
- [ ] Next PB-1.3 engineering increment: Stage B's versioned native observation
  payload contract, ownership/identity/context admission and bounded read-only
  publication preview, following the [publication design](REVIEWED_FINDING_PUBLICATION_DESIGN.md).
  Preserve finding ownership/workflow and retained history. Publication writes,
  scoring/evidence invalidation and guarded UI must be reviewed/tested before
  exposing Apply. Stage B is not implemented by this documentation update.

Deferring manual acceptance does not close PB-1.3 or approve broader feature
rollout. Existing settings, partial test records and running services are unchanged.

For the activated consolidation feature, use the complete [step-by-step Chrome walkthrough](CONSOLIDATION_CHROME_WALKTHROUGH.md), including both sample files, identity/canonical setup, Apply, scoring approval and Undo.

## Current verification baseline - 11 November 2026

The committed application is `e4c7488c1a0b40a99bc20efe60a6663fac7f62d3`.
All four hosted Linux jobs passed in
[run 43144443993](https://github.com/shalisarakkal/AuditMind/actions/runs/43144443993).
This includes the unchanged-draft correction. The preceding suppression and
retained-source correction through `f97a4fb` passed all four jobs in
[run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797).
Local activation is recorded at schema 0050; the draft-save fix adds no migration.

Draft-save local acceptance: 54 backend draft/review tests and 15 component tests,
lint and production build. Earlier suppression scopes (120 expanded backend,
three final indexed cases, 576 frontend and 103 Chrome checks) are separate,
overlapping checkpoints; do not sum them or describe them as a fresh local full
suite for e4c7488. Full exact-source hosted jobs are verified above.
[Current scope and release evidence](SUPPRESSION_RELEASE_REVIEW.md).

The instructions below are manual verification steps, not a claim that all
product phases or production/pilot gates are closed. Older dated checkpoint
statements are superseded by the current delivery record.


## Durable absence review verification - 11 November 2026

Use a disposable organization and the synthetic native examples linked in
[scan snapshot verification](SCAN_SNAPSHOTS.md#chrome-verification). After
migration 0049 is activated:

1. Review the scanner/host bindings and save compatible Complete declarations.
   Compare the pair; the baseline-only candidate appears without changing it.
2. Save candidates explicitly. Reopen Uploads, choose **Open absence review
   queue**, and confirm the captured scan names and candidate survive reload.
3. Enter a rationale and select **Keep finding active**. During submission,
   Close, Escape, filters and paging must not dismiss or change the operation.
4. In **Kept active**, enter another reason and choose **Reopen review**. This
   reopens the queue item, not the finding workflow. Confirm both reasons remain
   in Activity and the latest decision appears in the queue.
5. Have a second reviewer save an older decision version: it must return a
   conflict, retain the rationale and require explicit reload. Change the live
   finding workflow after capture: the old snapshot cannot authorize a
   keep-active review; compare again to save a fresh batch.
6. A viewer can read the queue but cannot save a disposition. Verify the finding's
   workflow version, archive state, severity and risk treatment are unchanged
   by queue review. Saving/reviewing does not call an AI provider.

Saved summaries remain after source-record purge, until organization deletion.
Suppression, archive/restore dispositions and automatic reconciliation are not
implemented by this queue.


PB-1.3 canonical finding designation: follow the
[canonical review Chrome steps](CANONICAL_FINDING_REVIEW.md#chrome-verification)
for two independent identities, both workflow histories, explicit canonical
selection, stale-preview conflicts, versioned revocation and retention semantics.
This designates a pair without merging records or changing scoring/counts.

PB-1.3 cross-import identity review: follow the
[native Nessus Chrome steps](CROSS_IMPORT_IDENTITY_REVIEW.md#chrome-verification)
for explicit pair comparison, confirmation, stale-preview rejection and canonical
conflict handling. This does not authorize automatic reconciliation or scoring.

Dashboard tabs: Findings-based opens by default and displays known-risk baseline
scores. With evidence-qualified scoring enabled but no valid qualification, select
Evidence-based and confirm its assessment remains Not assessed with coverage
reasons. With that setting disabled, the tab explains how an admin can enable it.
Tab changes must not change settings, submit jobs or start an evaluation. Check
that Inventory and finding risk shows the same totals, severities, current-risk
findings and verified exclusions on both tabs, including disabled evidence mode.
Check
arrows/Home/End navigation and that Refresh preserves the selected tab. Empty
inventory and all-excluded findings still have no fabricated baseline.

Automated tab presentation check, against the running local UI:
`node scripts/browser-dashboard-tabs.cjs`. It intercepts synthetic API data and
does not use credentials or mutate the real organization. Screenshots and results
are saved under `temp/testing/dashboard-tabs`.

PB-4.4 status-aware scoring: verify Platform default On, organization overrides,
administrator evidence approval, Mitigated retaining full risk, and stale/revoked
evidence restoring contribution. Workflow notes alone must not exclude findings.
See [the Chrome checklist](STATUS_AWARE_SCORING.md#chrome-verification). This is
separate from evidence-qualified domain coverage, whose setting is unchanged.

PB-1.2 source-scan review: on Uploads, open **Snapshot**, declare source scope,
tool instance/configuration and source snapshot time, then **Use as baseline**.
Declare a later source snapshot and choose **Review against baseline** followed
by **Compare scans and build review list**. Check both scans, scope/exclusions
and the explicit absence blocker. Finding workflow, severity, archive state and scores must not
change. [Detailed steps and clean synthetic files](SCAN_SNAPSHOTS.md#chrome-verification).

PB-1.1 source history: after installation, import a small findings file, open
the finding's **Workflow**, then **Show source observations**. Reimport the file
with a changed severity/description and the same matching key. Two occurrences
should be visible, while canonical finding/workflow values remain unchanged.
These observations are explicitly ineligible for reconciliation; history is not
backfilled for earlier/manual findings. See the
[Chrome steps and retention contract](FINDING_OBSERVATIONS.md#inspection-and-chrome-verification).

UI text/time follow-up (27 October): application headings, report filters and
shared table/section labels use sentence case instead of forced all caps. Names,
acronyms, authored report titles and evidence text retain their original case.
Report **Captured** timestamps use browser-local date/time; original UTC values
remain in technical provenance and exports. Known UTC selection semantics are
rephrased as an explicit scope explanation, without changing saved boundaries.

Report priority-filter contrast follow-up (27 October): in a completed report's
Prioritized Remediation Roadmap, select All, Critical, High and Medium. The active
option should have a cyan background and readable navy text; exactly one option
is selected. This is presentation-only and does not change saved report content.

Report Print follow-up: open a report, choose a priority filter, then click
**Print**. Chrome preview should contain only the report (including every
remediation priority), without sidebar, application header, Back link, filters,
Print or Download buttons. Text is black on white for printing. Cancel preview:
the original screen filter and application navigation should be unchanged.
Chrome's own Headers and footers option controls its added URL/page/date lines;
these are separate from the application's report-only print layout.

## Dashboard evidence review and opt-in scoring (updated 28 October 2026)

Latest local acceptance: **18 dedicated Chrome scenarios** pass with `--pilot --load`,
including seven-domain/real-zero/weighted aggregation, real review expiry, scope
mismatch and a bounded six-account/two-organization exercise. The earlier 11
opt-in/isolation/rollback scenarios passed hosted Ubuntu CI at `898b309`.
The latest `0b1732f` hosted Ubuntu run also passed all **17 correctness-only pilot
scenarios** and the **71-check workflow suite**; see
[run 40774060584](https://github.com/shalisarakkal/AuditMind/actions/runs/40774060584).
The implementation checkpoint also passed
71 full regression checks, 465 frontend and 1,366 full PostgreSQL tests; those
broader suites were not rerun for the browser-only follow-up. See
[validation](PHASE4_VALIDATION.md) for final backend/build results and successful
hosted Ubuntu CI for implementation `5ce836b`
([run 40749424003](https://github.com/shalisarakkal/AuditMind/actions/runs/40749424003)). Qualified scoring is now available as
an admin opt-in but remains **off by default**. Verify in a synthetic organization
before opting in real organization data. No AI calls or provider consent are needed.
The local demo is on migration 0031. Refresh Chrome with **Ctrl+Shift+R** to load
the new production-build UI before following these steps.

Scope/reload clarification: **Evaluate evidence across all domains** is in the
separate **Organization-wide evaluation** section, above the domain editor.
It always checks all seven domains for the selected organization, regardless of
the domain picker. It uses saved records, not unsaved editor changes.

**Open / reload domain** fetches the latest saved qualification/version for the
chosen domain, or opens an empty local draft when none exists. It does not scan
inventory, save, approve, or change scores. An application-styled confirmation
dialog appears only when there are actual unsaved edits: **Discard and reload**
loads the saved record; **Cancel** or Escape keeps your edits. Cancel receives
initial focus, and the modal blocks background interaction. No browser popup is
used. Review/conflict/revocation confirmations in this panel use the same
application dialog. Read-only/unchanged reloads do not prompt. Switching domains
also protects unsaved edits. A failed reload leaves the existing form intact.

Performance/progress follow-up: Load current inventory and Evaluate evidence
across all domains display a processed/total count, current phase, elapsed timer and
progress bar after counting completes. Counts include relevant lifecycle records.
Evaluation progress, errors and Cancel appear inside **Organization-wide
evaluation**, below its action button. Inventory-loading progress/errors/Cancel
appear next to **Load current inventory** in **Domain qualification**. Other
domain editor controls are locked during its synchronous inventory-binding action;
they are not locked for a separate background evaluation. Cancel remains enabled
for the authorized requester/admin. These statuses are not shown above their area.
Use **Cancel operation** to request cancellation. A count may
pause while PostgreSQL prepares/sorts the next population; the timer continues.
Cancellation releases the database snapshot after its current fetch finishes;
it does not instantly kill a running database statement. The 28 October Chrome
streaming check measured prompt UI recovery and approximately 28 s database cleanup;
the durable worker has its own measurements in the linked performance record.
Old v1 bindings require rebind/save/review after the v2 fingerprint update.
See [performance measurements and limits](EVIDENCE_EVALUATION_PERFORMANCE.md).

Open **Settings → Scoring and evidence review** as an organization administrator.
Leave the scoring switch off initially. Reviews/evaluation do not enable it
automatically, and saved reports are never rewritten. No inference is required.

1. Choose a domain and click **Open / reload domain**. The required objectives
   come from the backend policy. Enter the scope description and rationale.
2. Click **Load current inventory** to bind the entire organization inventory.
   This and **Evaluate evidence across all domains** scan inventory on demand and may be
   slow in SA01. They never run automatically on page load.
3. Add observations: choose an objective, source type, the Finding ID copied from
   Findings (or an organization-policy **document version** UUID), and the actual
   observation time. **Validate source and add** retrieves its current hash.
   Source validation does not establish that it satisfies the objective: that
   requires the administrator's operational review.
4. **Save draft**. Incomplete drafts are allowed. To approve, cover all three
   objectives with current evidence, supply a review note and expiry, and confirm
   the whole-inventory operational/conflict review. Approval applies to the saved
   version only, not unsaved edits. Expiry cannot exceed the evidence's 90-day
   freshness window. A conflict requires at least two distinct sources.
5. Use **Evaluate evidence across all domains** to see current eligibility and reasons for
   each domain. A saved approval is not automatically current eligibility.
   Inventory/source changes or expiry can invalidate it. Evaluation does not
   enable the scoring setting automatically.
6. Revoke approved/conflicting records with a mandatory reason before revising
   an approved record. Concurrent edits produce a conflict rather than silently
   overwriting another user's work; preserve your edits and reload deliberately.

Non-admin members can inspect saved records and evaluate, but cannot edit or
review. All entered/displayed times follow the browser time zone. Reloading a
domain discards unsaved edits only after confirmation. Navigating away also
discards unsaved edits; save first.

### Verify background processing and the Dashboard setting in Chrome

1. Click **Evaluate evidence across all domains** once. It should promptly show
   queued/running status, then real phase/count/elapsed progress inside that section.
   A stopped worker leaves it queued; run the worker to continue. Do not repeatedly
   click expecting separate simultaneous scans.
2. Navigate to Findings, then return to Settings. The same job/progress or completed
   result should reappear. Changing the domain picker must not limit evaluation.
   A second signed-in member joins the existing job; they cannot cancel someone
   else's job unless they are an organization admin.
3. After completion, record the qualified count and evaluated time. In the
   Dashboard, with the switch still off, the heading says findings-based baseline.
4. As an org admin, check **Evidence-qualified scoring**. In the application dialog,
   try Cancel first: the setting must remain off. Repeat and confirm to enable it.
   Go to Dashboard. It should identify the mode and qualified count; unqualified
   domains are Not assessed / Insufficient evidence / Review required, not 100.
   With only one qualified domain, that domain can score, but overall stays null.
   All seven with compatible scope are required for an overall score.
5. In a second browser profile/session, revoke an approval or change its bound
   synthetic inventory/source. Refresh Dashboard (or wait up to ten seconds/on focus).
   The old evaluation must no longer authorize scores; Settings should request
   reevaluation. Rebind/review affected records before reevaluating. Expired review,
   failed evaluation or cancellation must never authorize partial output.
6. Test **Cancel operation** during a running job. It should acknowledge cancellation
   and remain pending until the current database fetch drains, then show cancelled
   with no partial result. No instant database-kill behavior is promised. An earlier
   completed result can remain usable only if it is independently still current.
7. Turn the setting off again and confirm. Baseline scores return; reviews and
   saved reports remain. Other organizations keep their independent setting.

There are no automatic full scans on Dashboard refresh. The browser polls cheap
mode/revision status; failed verification hides scores. Background evaluation does
not save unsaved edits or bypass operational human review. See
[the background contract](BACKGROUND_EVIDENCE_EVALUATION.md) for pilot limits.

### Repeat the isolated two-user acceptance

Use the isolated build procedure in [Phase 4 validation](PHASE4_VALIDATION.md),
then run `node scripts/browser-evidence-acceptance.cjs` from the repository root.
Ports 3014/8012 must be free; do not overlap another PostgreSQL backend suite.
The opt-in fixture creates 100,000 synthetic assets in its own guarded local
test schema and uses two real administrators plus viewer/auditor/foreign-tenant
sessions. It checks normal UI source validation, concurrent saved-version
approval (one success, one 409), retained edits/reload, partial eligibility,
revocation, rebind/conflict, permissions and an inventory write during evaluation.
The in-flight scan uses its original snapshot; the next evaluation rejects the
changed binding. The test removes its schema/accounts/processes afterward;
ignored screenshots/results remain under `temp/testing/evidence-review`.
No normal tenant edits or existing-account password changes; no external AI
calls or ordinary-organization scoring enablement. The fixture temporarily enables
the synthetic test organization's setting, verifies partial scoring, and rolls it
back off before teardown. The real worker job also survives leaving/reopening Settings.

The expanded opt-in checks verify all seven domain cards, persistent mode after
reload, the other administrator's Dashboard, the other organization's unchanged
setting, automatic withdrawal of stale scores through real state polling, and
conflicting evidence shown as **Review required**. They cancel disabling first,
then confirm **Use findings-based baseline** in the UI and verify both sessions
return to the current baseline without deleting the saved qualification or job.
Invalidated domains show **Insufficient evidence** until reevaluation, not numeric
zero/100. No application code or ordinary-organization settings are changed by
this follow-up. These 11 scenarios also passed hosted Ubuntu CI at `898b309`
([run 40769552484](https://github.com/shalisarakkal/AuditMind/actions/runs/40769552484)).

To extend the same guarded synthetic fixture to all seven domains, run
`node scripts/browser-evidence-acceptance.cjs --pilot`. It adds explicit UI
approvals for all profiles, weighted overall/genuine-zero checks, a real
short-lived review that expires without a patched clock, re-review and scope
mismatch. The fixture then turns both organizations off before removal.
The CI browser job runs this correctness-only variant (17 scenarios, including
canonical native date input at exact minutes/nonzero seconds). These synthetic approvals
test software behavior, not the adequacy of real operational evidence.

For a separate bounded local concurrency exercise, use
`node scripts/browser-evidence-acceptance.cjs --pilot --load`. Six independent
accounts read two synthetic organizations for 60 seconds while eight worker
evaluations run in four waves. It records per-endpoint latency/counts and checks
HTTP success, mode/organization isolation and exact terminal record counts.
`--load` requires `--pilot`; it is deliberately not part of hosted correctness CI.
Do not overlap local backend suites or other benchmarks. This small local exercise
does not establish sustained production capacity; agree representative workloads,
duration and service targets before broader rollout. No normal tenant is enabled.

Full-size local SA01 read-only measurements are a separate opt-in command:
`node scripts/browser-evidence-http.cjs` (or `--cancel-only`). This requires the
running local demo, verifies no jobs or inventory scans are active, creates two
temporary viewer accounts and removes them afterward. It performs expensive real
scans and preserves inventory; do not run during imports or other benchmarks.
[Recorded results and limits](EVIDENCE_EVALUATION_PERFORMANCE.md).

For the newly committed Phase 4 changes, start with the detailed
[Chrome walkthrough and phase summary](PHASE4_USER_VERIFICATION.md). It covers
workflow, selection/archive, dates, search, shared UI and two-user conflicts.
The 26 October follow-up includes today's inclusive deadlines and matching
Archived/Assets/Uploads row/bulk confirmations. Follow that current walkthrough;
older test counts below remain historical evidence, not current suite totals.

23 October 2026. Synthetic/mocked testing only. **Do not enable real inference,
enter credentials, grant ordinary-organization external processing consent, or
change backend/.env just to perform these checks.**

## 1. What you can check in the normal demo

Archive confirmation (25 October follow-up): select several rows; row Workflow,
Archive and Undo must be disabled, while eligible selected actions remain enabled.
Clear selection, then click a row's Archive.
The modal identifies exactly one finding/UUID; other checked rows are excluded.
Background selection/actions are blocked. Cancel or Escape returns without a
write; Archive 1 finding submits only that row. Archive selected instead confirms
the frozen names/count and Archive N findings. Cancellation is blocked while busy.
Selective substring search is now indexed (migration 0024). In SA01, searching
`ssss` should still show two findings; a live Chrome check completed in 1.13s.
One/two-character or very broad terms can still be slow. Full timings, cold/warm
distinctions and limits: [search performance](FINDING_SEARCH_PERFORMANCE.md).

Lifecycle/access follow-up: privileged writes recheck organization lifecycle,
membership, role and active account after waiting for locks. A waiting write is
refused if archive/removal/demotion/deactivation committed first; an already
admitted transaction is fenced until commit. Manual finding references cannot
target pending/stopped archives or already archived assets/uploads. Automated
PostgreSQL tests in `test_write_admission.py` verify the blocked waits and both
outcomes without needing destructive manual tests against demo data.

Finding traceability (24 October 2026): expand **Finding ID** under a finding's
description and use **Copy ID**. Paste the complete UUID into **Search findings**
to locate the exact active finding. Workflow technical IDs, report evidence and
remediation finding references, and organization Activity workflow-event IDs link
to an exact Findings filter in the referenced organization. Links require access;
archived/purged/missing or synthetic-only references can show no active findings.
They do not alter saved reports or workflow state. See [the user manual](USER_MANUAL.md)
for identifier distinctions and clipboard behavior.

Findings actions (25 October 2026): Workflow and eligible manual Archive are
together in the sticky-right **Actions** column. There is no selection mode.
Checking rows shows both **Update selected workflow** (up to 100) and **Archive
selected** (up to 500, all targets must be manual/available). Mixed selections
disable archive with an explanation. Row actions remain independent. Selection
and its eligibility persist across pages; confirmations identify the exact targets.

1. Open Chrome at **http://localhost:3000/login** and use your existing local demo
   sign-in. Do not paste credentials into chats, screenshots or Git commits.
2. Choose your demo organization, then open **Reports**.
3. Find **Assessment completeness**. Leave **All assessments (including legacy)**
   selected initially. Legacy reports do not receive fabricated new evidence states.
4. Open the existing rule-based preview using **View**. It should remain a
   **deterministic test / no AI** report, with unchanged saved values, no framework
   control assessment and working HTML/PDF downloads. On an older AI report, if
   one exists, evidence status should say **not recorded (legacy assessment)**;
   captured baseline appears only when it was actually recorded.
5. Choosing Complete or Partial filters **new-contract** assessments only. An empty
   list in the original demo organization is expected: the new mode is off by default.
   Select **Evidence examples - SYNTHETIC ONLY** for the persistent mocked examples
   described below. Do not enable real generation to fill it.

The new mode is not a global rescore of existing reports. Opening Documents or
approving external processing alone does not activate it.

## 2. Inspect the already captured new-mode UI/report without generating anything

Open these existing files through File Explorer, or press **Ctrl+O** in Chrome and
paste the full path. These paths belong to this workspace, not a fresh clone:

```text
S:\AI-Projects\AuditMind\temp\auditmind-demo\browser\phase3\phase3_browser_50059684831c\report.png
S:\AI-Projects\AuditMind\temp\auditmind-demo\browser\phase3\phase3_browser_50059684831c\report.html
S:\AI-Projects\AuditMind\temp\auditmind-demo\browser\phase3\phase3_browser_50059684831c\report.pdf
```

The PNG is a captured application screen, not interactive. HTML/PDF are standalone
exports, not the full application. These files are ignored temporary evidence and
may not exist after cleanup/on another machine; use the runner below to recreate.

Check:

- Report is visibly synthetic/mock, not a real Claude assessment.
- Overall says **Partial AI assessment — overall score unavailable**, not0/100
  or a made-up overall tier. Successful report completion is not a failed job.
- Domain scores are unavailable where evidence is insufficient; explanations and
  reference IDs remain visible. A domain can be unscored while useful guidance exists.
- Captured deterministic baseline is100/100 in this fixture, clearly separate
  from the missing AI score; it is not a compliance certification.
- Remediation confidence is model-estimated/not calibrated, not probability of
  compliance or successful remediation. Source references and limitations are shown.

Use `result.json` in that folder to see individual executed browser checks.
The mock intentionally contains policy-only evidence, so this artifact demonstrates
**insufficient** states, not every limited/conflicting/sufficient combination.

## 3. Recreate the full mocked Chrome verification

Prerequisites: installed frontend/backend development dependencies, installed
Chrome, reachable local `auditmind_test` with pgvector, and the production demo
frontend running on3000. Run from **S:\AI-Projects\AuditMind** in PowerShell.
If the demo is stopped, run `powershell -ExecutionPolicy Bypass -File .\start-demo.ps1`.
Do not start another copy if it is already running. Test API port8012 must be free.

```powershell
$previousEvidenceMode = $env:AUDITMIND_BROWSER_EVIDENCE_V3
try {
    $env:AUDITMIND_BROWSER_EVIDENCE_V3 = '1'
    node scripts/browser-phase3.cjs
    if ($LASTEXITCODE -ne 0) { throw 'New-contract browser verification failed; inspect its result.json.' }
    $env:AUDITMIND_BROWSER_EVIDENCE_V3 = '0'
    node scripts/browser-phase3.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Legacy browser verification failed; inspect its result.json.' }
} finally {
    $env:AUDITMIND_BROWSER_EVIDENCE_V3 = $previousEvidenceMode
}
```

Expected: **18 new-mode** and **17 legacy checks**, each with `passed:true` and
`cleanedUp:true`. This launches headless installed Chrome, so you will not see an
interactive window. Each run prints a fresh evidence-folder path containing PNG,
HTML, PDF, logs and result.json. Review those files instead of reusing an old ID.

Real frontend/API/worker/PostgreSQL are exercised; inference/embeddings are mocked
and external provider HTTP blocked. Each runner creates then removes an isolated
synthetic test schema and test-only consent/accounts. It does not leave reports
for you to sign into later or grant consent to SA01/the ordinary demo. Keyboard
source links, mobile/print display, downloads, tenant permissions, retries,
cancellation and the new completeness filter are checked automatically.

Run acceptance sequentially—do not overlap public-schema backend suites. Do not
replace this with requests to real Generate Report endpoints.

## 4. Verify all policy states and the scored path

Chrome's new-mode fixture covers partial/insufficient evidence. The following
tests cover the other states, trusted complete coverage, aggregation and failures.
They do not require a new paid/model call.

From the repository root:

```powershell
Push-Location frontend
try {
    npm test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed.' }
    npx tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw 'Frontend type check failed.' }
} finally { Pop-Location }
```

For targeted PostgreSQL verification, **fixtures recreate/drop public tables in
the disposable test database**. Do not use your normal/demo database or run another
backend suite concurrently. This guarded command confirms the exact local target
before testing and restores the migrated schema afterward. It does not display
the connection string/password:

```powershell
Push-Location backend
try {
    .\.venv\Scripts\python.exe -c "from app.core.config import settings; from sqlalchemy.engine import make_url; u=make_url(settings.TEST_DATABASE_URL); assert u.get_backend_name()=='postgresql' and u.database=='auditmind_test' and u.host in ('localhost','127.0.0.1'); print('Confirmed local auditmind_test target')"
    if ($LASTEXITCODE -ne 0) { throw 'Wrong/unconfigured test target. Stop here.' }
    .\.venv\Scripts\python.exe -m pytest -vv -W error --require-postgres tests/unit/test_evidence_policy.py tests/unit/test_report_context.py tests/unit/test_report_presentation.py tests/unit/test_assessment_contract.py tests/integration/test_evidence_assessments.py
    if ($LASTEXITCODE -ne 0) { throw 'Targeted regression tests failed.' }
} finally {
    .\.venv\Scripts\python.exe -c "from app.core.config import settings; from sqlalchemy.engine import make_url; from alembic.config import Config; from alembic import command; u=make_url(settings.TEST_DATABASE_URL); assert u.get_backend_name()=='postgresql' and u.database=='auditmind_test' and u.host in ('localhost','127.0.0.1'); settings.DATABASE_URL=settings.TEST_DATABASE_URL; c=Config('alembic.ini'); command.upgrade(c,'head'); command.check(c)"
    $restoreExit = $LASTEXITCODE
    Pop-Location
    if ($restoreExit -ne 0) { throw 'Test schema restoration failed. Stop; do not force/stamp migrations.' }
}
```

Expected **130 targeted tests** at this check-in checkpoint. `-vv` lists scenario
names. Important checks include all21 domain/non-sufficient combinations, strict
null/score/tier rules, genuine zero score, half-up aggregation, stale/hash/scope/
foreign-source rejection, guidance-only references, marker-injection preservation,
partial API/export/filter/sort and reviewed complete aggregation. These tests do
not leave persistent sample reports, either.

Full backend suite can be substituted for the targeted pytest command by omitting
the listed test paths. Allow roughly10minutes and restore the test schema afterward.
The last full checkpoint was1,115 tests; one subsequent check-in marker regression
was added, so a fresh full collection is expected to contain1,116—not a claim that
that larger full run has already been performed. No new coverage percentage is claimed.

## 5. Acceptance checklist

- [ ] Existing reports/values and rule-based labels unchanged.
- [ ] Partial reports finish successfully with no invented numeric overall score/tier.
- [ ] All domain states and reasons distinguish unknown evidence from failed controls.
- [ ] Sufficient scoring cannot be self-granted by the model or an uploaded policy.
- [ ] Source IDs/hashes, scope, recency and qualifications reject mismatches.
- [ ] Baseline and AI remain separate; confidence explanation is clear.
- [ ] Completeness filtering and null-last sorting behave as documented.
- [ ] UI, HTML/PDF, keyboard/mobile/print checks pass.
- [ ] No real inference, paid calls, credentials or ordinary-tenant consent changed.

Record PASS/FAIL, date, test command, evidence folder and any screenshots. Report
unexpected results before enabling anything. Adopting real operator qualifications
and enabling a controlled rollout is a separate decision described in
[coverage profiles](EVIDENCE_COVERAGE_PROFILES.md); production/live-AI acceptance
remains open.
# Persistent synthetic demonstration reports

## Settings display checks (October 29, 2026)

In Chrome, open Settings as an organization administrator:

1. Under Dashboard refresh, confirm **Reload saved settings** reloads saved
   configuration without regenerating Dashboard data. Select **Inherit Platform
   refresh interval**, then **Save refresh interval** to restore inheritance;
   selecting the checkbox alone does not save. There is no separate Reset button.
2. Under Organization-wide evaluation, run an evaluation or open a completed one.
   **Evaluation completed.** and its progress bar disappear after five seconds.
   Coverage results and **Last evaluated** remain visible.
3. A stale-evidence warning must remain visible after the progress display hides.
   Running, failed and cancelled states do not use the completion timeout.

Component checks: six evidence-evaluation tests and three Dashboard-refresh tests
passed; lint and the isolated production build passed. Chrome login smoke check returned HTTP 200, with no page
JavaScript errors; an empty login payload reached backend validation (HTTP 422).
These smoke checks do not establish a successful credentialed sign-in or replace
the signed-in Settings checks above.

An initial installed-Chrome attempt with outdated saved credentials was rejected.
After the operator updated the local platform credentials, signed-in Chrome
verification passed on October 29, 2026: Reload saved settings worked without
page JavaScript errors. In SA01, the completed message and progress bar disappeared
after five seconds while Last evaluated and coverage results remained visible.
No new evaluation, password reset or saved organization-setting change was made.

## Opening the synthetic reports

Sign in at http://localhost:3000 using the existing demo organization-admin account.
In **Organization**, select **Evidence examples - SYNTHETIC ONLY**, then open **Reports**.
Four saved examples show sufficient, limited, insufficient and conflicting evidence.
Use **View**, **Download HTML** and **Download PDF**. The sufficient example has a
simulated score of 70; the other three deliberately have no numeric overall score
or risk tier. The completeness filter shows one Complete and three Partial reports.

These are fixed mocked snapshots, not model output or operational evidence approvals.
No consent, real inference, embeddings, qualifications or paid calls are enabled.
The original demo organization and its credentials are retained. Examples persist
across restarts; seeding does not overwrite existing reports or user edits.

To deliberately create missing examples, run from `backend`:
`.\.venv\Scripts\python.exe scripts/demo.py seed-evidence-examples`.
This command refuses ordinary application schemas and remote demo targets.

## Assets and Findings navigation checks

For the list-performance changes, see [the measurements and browser steps](LIST_NAVIGATION_PERFORMANCE.md).
On Findings, apply a search, change sorting and move to another page. Switch
organizations using the sidebar. The new organization should start on page
one with a blank search and default sorting. Previously selected rows and open
actions must also be cleared. Use Next and Previous to check that the exact
total and row ordering remain consistent while no findings are being edited.


## Reviewed finding identity (PB-1.3 local increment, 7 November 2026)

Use an organization-admin account and a retained completed native Nessus upload.
Generic CSV/JSON and generated profile rules do not offer identity review yet.

1. Findings -> row Workflow -> Show source observations -> Review identity binding.
2. Inspect the captured source asset. Select its registered Nessus tool instance,
   or expand Register a tool instance, enter a unique instance name and review
   reason, then register it. Registration saves immediately; cancelling the later
   binding review does not delete that namespace or undo a submitted write.
3. Verify the canonical asset UUID (defaults to the captured source asset), enter
   the binding reason, explicitly confirm scanner/asset verification, then save.
4. Expand Identity assessment: a current candidate key appears. Reconciliation
   remains ineligible; workflow status, severity, archive state and scores do not
   change. Eligibility reasons labelled at import retain their historical meaning.
5. Reopen the review and provide a reason to Revoke identity binding: the version
   advances and the key becomes unavailable. Review/create another decision only
   after explicitly checking current context.
6. To retire a scanner, select it and use Retire selected tool instance, then the
   application confirmation. Every binding for that namespace becomes unavailable;
   it cannot be reactivated/reused. A replacement needs a new namespace.
7. Two stale browser edits: the second save is refused; its draft stays. Reload
   identity context and reconfirm before retrying. Close/Escape remain blocked
   during submission. Read-only users have no review controls; API writes also
   enforce organization-admin permissions.

New uploads never inherit reviewed bindings automatically. Retained source scan,
asset identity and namespace lifecycle are checked when the history is read.
No not-observed queue, automatic merge, source-driven resolution or imported-row
suppression is enabled by this increment.


## Migration 0050: reviewed native suppression and clear

Use an isolated test organization and native Nessus test file. Do not use
production evidence to create test mutations. Requires the matching backend,
worker and frontend build after migration 0050 activation.

1. Import native Nessus and review every retained observation's scanner/canonical
   asset identity as an organization admin. A generic source label, declaration
   or verification note must not bypass this review.
2. Record the Finding ID, workflow/history, filtered list total and Dashboard
   baseline. Open row Suppress, verify that it names the exact target/status/
   plugin/service, and try submitting without rationale or acknowledgment: blocked.
3. Submit with both. Confirm the row/filtered total/facets/top issues exclude it,
   workflow fields are preserved and Dashboard reports the suppressed count apart
   from verified exclusions. While the saved Dashboard refresh is queued/running,
   it must not display an older score as current. Existing reports are unchanged.
4. Open Suppressed findings, inspect decision actor/rationale/time, reload and
   confirm persistence. At 320px, long labels/tool names and the footer must wrap
   without horizontal overflow; keyboard focus/Cancel remain visible.
5. As viewer/auditor, inspect history but verify Clear suppression is unavailable
   and the clear API refuses the role. An auditor may suppress eligible records;
   only an admin may clear. A different organization cannot read or mutate these IDs.
6. As admin, clear the retained record and verify active counts/risk return under
   the existing policy. Archived parents stay archived; purged payloads are not
   recreated. A duplicate/source conflict must explain why restore is blocked.
7. Use two sessions: save one decision, then submit the other's old preview.
   Expect a conflict with its rationale retained and no second effect. During a
   deliberately delayed save, Cancel/Escape/inputs must be disabled.
8. Reimport a similar source. New unreviewed data stays visible; possible
   reappearance history does not grant a trusted mapping or resolution. Source
   purge retains the historical decision. Fresh explicit mapping/reapply updates
   the current source context; different service/asset/namespace does not inherit it.
9. For an isolated transport test, drop/replace the response after a committed
   decision and retry. Exactly one durable decision must exist for the request ID.
   No action claims a submitted operation was cancelled by closing its dialog.

These are feature checks, not pilot, production, model-quality or SaaS acceptance.
See [release review](SUPPRESSION_RELEASE_REVIEW.md) for automated evidence.

### Multiple retained suppression payloads

If a standing suppression was explicitly reapplied after archiving an older
upload, restoring that older upload can leave multiple hidden payloads with the
same reviewed identity. **Clear suppression** must refuse this conflict. Archive
the additional retained source or resolve its canonical conflict before retrying.
Clearing never silently publishes both. After clearing, attempting to restore an
older conflicting payload must fail safely while retaining its data/history;
this also applies when its source asset differs through a reviewed alias.

## Draft saves without version noise

In Settings > Scoring and evidence review, open an existing saved draft.
Save draft is disabled until persisted content or the inventory binding changes.
Change the scope or rationale: Save draft enables. Revert the edit (including
whitespace-only changes): it disables again. Typing only a review note or an
unfinished source observation does not enable it. Loading the same inventory
binding also leaves it disabled; a different/new binding enables it.

The first valid save creates version 1. After a real edit, save once and verify
one version increment followed by a disabled Save draft button. An identical
API save with the current expected version returns the existing record without
changing its timestamp, audit entries or evidence revision. Source validation
and stale-version conflicts still apply. Two reviewers editing the same version
must still receive a conflict on the stale save, even if its content matches the
new server version. Approved records remain protected from editing; returning a
revoked/conflicting record to draft remains an explicit state change.

## 12 November 2026: PB-1.3 read-only foundation

Migration `0051` adds retained consolidation/decision ledgers and bounded read APIs.
An administrator-only preview validates current pair prerequisites in a read-only
snapshot. No consolidation writes, visibility changes or new UI actions are enabled.
Current membership/dependencies, proof, lifecycle and consumer integration remain
pending before publication. Validation and API details: [foundation review](CONSOLIDATION_FOUNDATION_REVIEW.md).

The membership/dependency follow-up is also API-only: an eligible admin preview
returns `dependency_summary` with source-type counts and a deterministic fingerprint.
A blocked preview returns no usable manifest. This is diagnostic: `apply_available`
remains false, and there is no Apply/Undo control to exercise in Chrome yet.


## Consolidation visibility integration: internal validation only

The current local increment has no Apply/Undo button and publication remains
disabled. Do not attempt to activate it by changing a setting. Automated tests
simulate an admitted pair and check one visible canonical finding, retained
source rows, atomic totals/evidence invalidation and safe undo/retries. Browser
acceptance of publication belongs to the later guarded UI increment. Migration
`0053` is not applied to the normal application database and requires coordinated
activation. See [visibility integration](CONSOLIDATION_VISIBILITY.md).


## 12 November: reviewed native pair publication (Stage A, locally verified)

Group-scoped scoring proof, source lifecycle/reappearance guards, default-off
organization opt-in, authorized apply/undo and guarded UI are implemented locally.
Both source records/workflows remain; no payload is copied. Existing notes are
not approvals, and undo requires explicit approval revocation. PB-1.3 remains
partial: Stage B payload publication and additional/automatic mappings are open.
No normal-data migration or restart occurred. Contract, activation and Chrome
steps: [Stage A release review](CONSOLIDATION_RELEASE_REVIEW.md).


## 13 November: Stage A local review closeout

Local validation passed: 1,903 full backend tests, 585 frontend tests, 106 full
Chrome checks and the final focused Chrome walkthrough. The final 58-test
PostgreSQL run covers the subsequent failed-archive revocation recovery fix;
these scopes overlap. Lint, high-severity static security, secret and whitespace
checks passed. Retained history paging and reapply after undo are covered.
Changes remain uncommitted; normal-data migration/restart and hosted Linux CI
for this increment remain pending. Consolidation stays default-off. See
[scope, measurements, activation and verification](CONSOLIDATION_RELEASE_REVIEW.md).


## 13 November: hosted verification and local activation complete

Application commit `427596b781d278a9b65d4a8d46511662b50834ed` passed all four
[hosted Linux jobs](https://github.com/shalisarakkal/AuditMind/actions/runs/43436101209):
backend, frontend, dependency/security and browser acceptance. The hosted mobile
Settings overflow was corrected and the 374px/390px checks remain enforced.

The owner selected maintenance after CI success. Services were stopped, an
approximately 1.74 GB custom-format `auditmind_demo` backup was created in 126.9
seconds, and its archive listing and SHA256 were verified. Backup and manifest
remain in the ignored local `temp/auditmind-demo/checkpoints` directory; no
backup data or credentials are committed.

Migrations `0053` through `0055` completed, including all 28 findings index
replacements and both observation indexes. No invalid indexes or metadata drift
remain. The maintenance script's initial Alembic version-table reflection check
was corrected to match `demo.prepare`; this required no application/schema fix.
The frontend was rebuilt and API/frontend/one-slot worker restarted. `/health`,
`/ready` (database/uploads/worker) and `/login` passed. Existing accounts and
passwords were retained. No organization is opted in and no alias was published.

The application is available at http://localhost:3000/login. Enabling the
separate organization setting and applying a reviewed pair remain explicit
admin actions. Remaining PB-1.3 scope is unchanged: Stage B payload publication,
additional identity mappings, larger groups and automatic reconciliation.


## Stage B preview foundation - automated local verification

The [versioned native payload/read-only preview](OBSERVATION_PAYLOAD_PREVIEW.md)
is locally verified: full backend 1,960 passed and Chrome 106 checks passed, plus
focused context-drift checks. This adds an administrator-only read-only API and
passive version stamps on newly captured native snapshots. Publication and Undo
remain unavailable and there is no new publication UI to test yet. No manual
action is requested; the existing Stage A user/pilot acceptance stays TODO.
