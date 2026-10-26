# Verify the evidence-aware reporting changes

For the newly committed Phase 4 changes, start with the detailed
[Chrome walkthrough and phase summary](PHASE4_USER_VERIFICATION.md). It covers
workflow, selection/archive, dates, search, shared UI and two-user conflicts.

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
