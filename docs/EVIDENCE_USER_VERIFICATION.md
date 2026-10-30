# Verify the evidence-aware reporting changes

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
