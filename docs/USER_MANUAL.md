# AuditMind user manual

Report prompt update: **audit-evidence-v3** adds explicit input limits and omission
disclosures. Existing reports are unchanged. Before any separately approved real
AI use, an organization admin must review/reapprove the new processing target in
Documents. Real inference is still disabled in the demo. In report details,
expand **Captured evidence details** to inspect included excerpts, text limits,
omitted finding/citation IDs and actual input bytes. A truncated excerpt is not
the complete finding; an omitted record was not available to the model.

Remediation follow-up (2026-10-22): the preview demo is usable, not release-approved.
Keep real inference disabled. Cancellation is rechecked before each provider
attempt/reservation and prevents result publication; it cannot abort an issued
request. Report-period dates remain API-only; browser date fields are a deferred
enhancement, not a release blocker. Docker deployment is deferred to the Future
phase; the current demo runs native local services. Framework selection does not install licensed standards.
See [current code review and release gates](RELEASE_READINESS.md).

The [native Phase 3 Chrome checklist](PHASE3_ACCEPTANCE.md) passed with synthetic
accounts and mocked inference/embeddings. It does not enable real AI reporting or
certify production deployment; ordinary demo credentials and data remain unchanged.

Version: Phase 3 core preview, 21 October 2026. This manual describes the implemented
application, not every capability proposed in the roadmap. Final release acceptance
is still pending. See [Phase 3 operations](PHASE3_OPERATIONS.md) for administrator
deployment, quotas, retention and model-cache instructions.

## 1. Start the local browser demo

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
```

Open **http://localhost:3000/login** in Chrome. The launcher builds the current
frontend, prepares synthetic examples and starts the API, worker and frontend as
hidden, loopback-only processes. PostgreSQL must already be running locally.

Two random passwords are printed on first preparation only:

- `demo.admin@example.com`: organization administrator; use this for the feature tour.
- `demo.platform@example.com`: platform administrator; use this for platform controls.

Passwords are not embedded in this manual or checked into source control. Keep the
first-launch output somewhere private. Existing demo passwords and edits are never
reset when restarting. Use Account to change your password. A platform admin can
reset an organization user's password through Accounts. For a lost platform password,
an operator can create a separate sysadmin using the existing server-side tooling;
never reset database hashes manually.

Stop the demo without deleting its data:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -Stop
```

Restart without rebuilding only if frontend code has not changed:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -SkipBuild
```

The demo uses the separate `auditmind_demo` schema inside the configured local
PostgreSQL database. The regular application's `public` tables, accounts and
migration revision are not changed. It is **not** the disposable `auditmind_test`
database. The launcher does not edit `.env`. It disables provider credentials,
public sign-up and automatic archive purging for its own processes, and enables
explicitly labelled rule-based test reports. Do not use real confidential data.
Logs and process records are under ignored `temp/auditmind-demo/`.

Prerequisites on another machine:

1. Install Python 3.12, Node.js 22 and local PostgreSQL with pgvector.
2. Follow the root [README](../README.md) to create `backend/.env`, a strong
   `SECRET_KEY`, a local database and backend virtual environment. The database
   role needs schema-creation permission; pgvector must be installed/enabled by an
   operator if the role cannot enable it. Remote database targets are refused.
3. Install backend dependencies with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
   from `backend`, and frontend dependencies with `npm ci` from `frontend`.
4. Run the demo launcher. No Anthropic key is needed for the tour.

The existing `start-dev.ps1` starts the **regular development application**, not
this isolated demo. Do not run both on ports 3000 and 8000 at the same time.

## 2. Ten-minute feature tour

1. Sign in as the demo organization admin. Check the organization picker shows
   **AuditMind Demo - Synthetic Data**.
2. On **Dashboard**, inspect four assets, seven findings, the overall resilience
   score, domain scores and severity counts.
3. On **Assets**, filter for `demo-web-01`, inspect the record and clear the filter.
4. On **Findings**, filter by severity/domain and inspect the matching evidence.
5. On **Reports**, open **DEMO - Rule-based preview (not AI)**. Inspect the summary,
   domain scores and remediation sections; download HTML and PDF.
6. Use **+ Rule-based test report** to create another explicitly non-AI
   snapshot. Its score reflects the current findings, not a model assessment.
7. On **Documents**, inspect the synthetic policy and **Data processing consent**.
   It is initially unpublished/unindexed; indexing and search require the real
   model cache described below. Do not grant external consent merely for the tour.
8. Visit **Uploads**, **Archived** and **Activity**. Uploads/Archived initially have
   no records; Activity includes report creation and your sign-in activity.
9. Inspect **People**, **Settings** and the account menu without changing security
   or deleting data unless you intend to explore those operations.
10. Sign out, then sign in as the demo platform admin to inspect **Organizations**,
    **Accounts**, **Platform activity**, **Security defaults** and **Shared standards**.

All seeded hosts, addresses and security observations are synthetic. The demo is
not an assessment of this computer or network. Nothing is discovered or scanned.

## 3. Accounts, organizations and permissions

Use the organization picker before reading, importing or changing data. Lists,
reports and evidence are scoped to the selected organization. Your role may differ
between organizations. An archived organization is read-only.

| Role | Intended use |
| --- | --- |
| Viewer | Read organization data and available reports; no imports or generation. |
| Auditor | Read data, import assets/findings and generate reports. |
| Organization admin | Auditor capabilities plus people, settings, organization documents and processing approvals. |
| Platform sysadmin | Manage organizations, accounts, security defaults and shared standards; organization data access is read-only, not an organization editing role. |

Sign-up is normally closed. A platform sysadmin creates an organization and its
first admin; an organization admin adds people through **People**. New temporary
passwords must be changed at first sign-in. Password rules, expiry, idle session
limits and lockout depend on platform defaults and organization policy.

Use the account menu for profile/password and sign-out. If access expires, sign
in again. Browser refresh should restore an eligible session through its secure
session cookie. Stay on one hostname: switching between `localhost` and
`127.0.0.1` uses different browser cookies.

Expired access tokens renew automatically for protected account requests as well
as organization data. If a Platform page cannot load your account temporarily,
it shows an error with Retry instead of remaining on Loading. A genuinely ended
session requires sign-in; Retry does not bypass authorization.

## 4. Dashboard and scoring

Dashboard scores are deterministic, calculated live from currently active findings
across identity/access, network configuration, vulnerability management, backup/
recovery, monitoring/detection, incident response and compliance alignment.
Higher resilience scores mean lower risk:

| Score | Risk tier |
| --- | --- |
| 80-100 | Low |
| 60-79 | Medium |
| 40-59 | High |
| 0-39 | Critical |

Severity deductions and domain weights are documented in [risk scoring](../RISK_SCORING.md).
No findings can yield a high score; that is not proof that a domain was examined
or is secure. Coverage and evidence quality matter. AI report assessments are
separate snapshots and do not replace the deterministic `/risk/score` service.
Legacy saved reports preserve their original scoring labels.

## 5. Assets, findings and imports

**Assets** holds inventory; **Findings** holds security observations, their domain,
severity, source and associated asset where known. Use search/column filters,
sorting and pagination. Applied filter chips show active restrictions and let you
remove them. Check selection scope carefully before a bulk action.

Multi-select filter menus stay open while you select checkboxes. Click outside,
click the dropdown summary again, or press Escape to close one without clearing
its selections. Escape returns focus to the summary when focus was inside the
menu. Use Clear only to remove the selected values.

For an import:

1. Open Assets or Findings and use its import/upload control.
2. Choose a supported CSV, JSON, Nessus or configured tool-export file. Select or
   confirm the correct source/import profile when prompted. Not every arbitrary
   vendor export is supported; the profile must recognize its structure.
3. Review the result: imported, updated/skipped and invalid rows are distinct.
4. Use **Uploads** to inspect history and row-level import feedback. Correct bad
   source rows and re-upload when needed; do not assume a partial import imported
   every row. Partial-success and matching behavior are configurable in Settings.
5. Large files wait for the background worker and show progress. Keep the worker
   running; navigation away does not stop a queued job. Use Retry where offered
   for an interrupted/failed job whose source is still retained.

To practice, import [demo-assets.csv](examples/demo-assets.csv) from Assets using
the generic assets source, then [demo-findings.csv](examples/demo-findings.csv)
from Findings using the generic findings source. These add two synthetic hosts
and two findings, so your dashboard counts will increase from the initial 4/7.
Do this only in the demo organization. The seeded report will retain its original
counts; generate a new test report to capture the updated data.

Re-uploading an identical file may require explicit confirmation. Existing asset
matching can update, skip or duplicate according to policy. Uploaded findings are
not a live scanner: direct asset discovery is not implemented.

## 6. Documents and permitted evidence

**Documents** combines organization-owned evidence with visible shared standards.
The header shows the organization name and, for authorized admins, **Upload
document**. This opens an inline metadata/file form; **Cancel upload** dismisses
it. Viewers and auditors can read/preview but do not receive document mutation
checkboxes, bulk actions or upload controls. Organization admins cannot modify
shared sources; platform Shared standards requires a Sysadmin.
An organization admin can upload authorized document text with title, edition,
source and rights information, add versions and request indexing/retry. Use the
supported text formats shown by the upload form; this is not a general PDF/OCR
ingestion system. Uploading a version does not instantly make it searchable.

The worker creates an index and publishes the version when processing succeeds.
Inspect processing status and errors. **Queued** / **Processing** describe new work;
**Reactivating…** describes republication of a retained retired version. Expand
**Version details vN** for source, rights and the content hash. Evidence search is
separate from filtering the document list and shows progress, result counts,
no-matches feedback or an error.
Retire stops future use; reactivation needs
successful processing. Permanent removal is destructive and may be blocked while
an active report uses the source. Previously captured report excerpts remain part
of their saved snapshot; retirement does not rewrite old reports.

**Search permitted evidence** searches eligible indexed versions. The demo does
not fabricate embeddings or download models automatically. Local semantic search
requires optional embedding packages and a preloaded, revision-pinned BGE-M3 cache.
See [operations](PHASE3_OPERATIONS.md) and `backend/scripts/setup_embeddings.py`.
The seeded synthetic policy deliberately starts unpublished so the UI does not
claim successful indexing without that prerequisite.

Full licensed CIS/ISO text is not bundled merely because a framework is selectable.
Only upload material you may process. Official NIST catalog setup and reference-only
limitations are documented in [standards documentation](standards/README.md).

## 7. Consent and real AI reports

An optional **OpenRouter → Anthropic/Claude** route is available in backend code
for mocked testing, but real inference remains disabled. It requires a distinct
processing-target approval; direct-Anthropic consent is not reused. The demo still
blocks external calls. See [OpenRouter setup and limitations](OPENROUTER_REPORTING.md).

External embeddings and external AI reports have **separate** approvals under
Documents > **Data processing consent**. Only an organization admin may grant them.
Review the displayed provider/model/prompt target first. Changed targets can
require renewed approval; old consent does not automatically cover a new target.
AI-report and embedding processing have separate status cards. Expand
**Processing target** for the exact target. Click Approve or Revoke, review the
inline confirmation, then confirm the change. Cancel leaves approval unchanged.
Local embedding targets display **Local processing**, without an unnecessary
external approval action.

- External embeddings can transmit document text and search queries.
- AI reports can transmit sampled findings and retrieved evidence excerpts.
- Revocation blocks future authorized operations; it cannot recall data already
  sent or abort an already-issued provider request.

The isolated demo intentionally has **no provider credentials**. Do not expect
Generate AI Report to succeed there, even if you approve consent. It is not a local
Claude substitute. To evaluate real AI reports, use a properly configured regular
development/staging instance with its correct migration head, provider credentials,
prepared evidence indexes, an active worker and explicit organization approval.
This may incur costs; provider quotas, reservations and retention are described in
the operations guide. The manual does not authorize or perform that rollout.

On a configured instance: open **Reports**, choose AI generation, enter a title,
select frameworks, and submit. Follow pending/running/completed or failed status.
The dialog names the selected organization and checks report-processing approval
before enabling generation. Missing approval offers **Review consent in Documents**;
a failed check offers **Retry approval check**. These actions do not approve
processing for you. Approval is not a provider/worker/index readiness guarantee.
Frameworks are grouped under **Frameworks**, with a reminder that selection does
not install standards or certify compliance. Use Escape or the labelled close
button to dismiss the dialog; keyboard focus returns to its opener. The form
scrolls on smaller screens, and dismissal is blocked while a submission is in flight.
Cancellation is available where shown; do not repeatedly resubmit an uncertain
request. Check failures and prerequisites before trying again.

## 8. Read and export reports

Open a completed report from Reports. Depending on assessment type and available
evidence, inspect its executive summary, domain scores and reasons, remediation
priorities, compliance sections, citations and provenance. AI remediation confidence
is a model estimate of support, **not a calibrated probability**. Referenced asset/
finding IDs identify captured evidence; empty reference lists can represent general
guidance. Test reports have no model confidence. Legacy reports may lack these fields.

HTML and PDF exports are saved snapshots, not live dashboard views. Selected
reports can be downloaded as a ZIP where offered. Deletion is restricted by role
and status and is permanent, not an Archived-page restore operation. Review the
confirmation carefully. A rule-based test report does not evaluate CIS/NIST/ISO
controls and must not be presented as an AI audit or compliance certification.

The report-generation dialog does not yet expose reporting-period selection;
do not infer date-limited coverage from its title. The API supports date inputs,
but period semantics are creation-date filtering of currently active findings,
not historical point-in-time reconstruction. Fully local AI generation (Phase 3a)
is separate delivery; Phase 3b is not an enabled provider feature.

## 9. Archive, activity and administration

Archive removes eligible assets, findings or uploads from active views and scoring;
associated data can be included in the archive operation. **Archived** offers
restore and, with authorization/confirmation, permanent purge. Large actions may
run as worker jobs. Retention can automatically purge expired archives on ordinary
configured instances. The isolated demo disables automatic archive purging only;
manual purge is still irreversible.

**Activity** records sign-ins, imports, reports, document/consent changes and other
audited actions. Filter by available fields and inspect failures. It is an audit
trail, not a substitute for server logs. **People** supports membership/role and
account recovery tasks for admins. **Settings** includes ingestion rules, file
profiles, security overrides and retention-related controls according to role.
Connector descriptions do not imply a live scheduled connector is configured.

Platform sysadmins use **Organizations** for organization lifecycle, **Accounts**
for account recovery/access, **Security defaults** for baseline policy and **Shared
standards** for shared evidence/provider profiles. Sysadmins should not grant
external processing approval without reviewing its scope and authority.

Organization **Archive** is refused while uploads, archive/restore/purge jobs,
AI reports or organization document indexes are queued or running. Wait for those
jobs to finish (or cancel a report and wait for its terminal state), then retry.
Shared-standard indexing and other organizations' jobs do not block your archive.

## 10. Troubleshooting

| Symptom | Check |
| --- | --- |
| Browser cannot connect | Run the launcher; inspect `temp/auditmind-demo/*.log` and `*.error.log`. |
| Port already in use | Stop the owning app. For this demo use `start-demo.ps1 -Stop`; never kill unrelated processes blindly. |
| Database preparation fails | Local PostgreSQL connection, schema-creation permission and pgvector availability. Do not redirect the demo to a remote or test DB. |
| Sign-up unavailable | Expected: use the printed demo credentials or an admin-provisioned account. |
| Sign-in loops or refresh signs out | Use the same hostname and check local HTTP cookie settings; demo config sets them automatically. |
| Upload/report waits indefinitely | Check worker logs and the worker-status warning. Restart the demo if a worker stopped. |
| No documents returned by search | Successful real indexing, a current published version, permitted scope and prepared model cache. |
| AI report fails | In the demo this is expected: credentials are deliberately disabled. In staging check consent target, credentials, worker, provider/quota and evidence readiness. |
| Buttons are missing or action forbidden | Selected organization, your role, archive state and job status. |
| Score/report appears inconsistent | Dashboard is live; reports are snapshots. Check filters, archived items, assessment type and legacy labels. |

Report a problem with the page, steps, approximate time and safe error/correlation
identifier. Never share passwords, session tokens, API keys or confidential evidence.
## Reading report scores and confidence

AI report scores are **advisory**, separate from the captured deterministic
baseline. Higher scores mean greater resilience; neither proves framework
compliance. AI score variation alone is not a measured change in security posture.
Missing historical baseline/sampling information is shown as not recorded, not zero.
Inventory totals do not imply the model received every finding or full description.
Read the sampling/evidence limitations and complete domain explanations.

Remediation confidence is model-estimated evidential support, not a calibrated
probability of compliance or successful remediation, nor evidence completeness.
Evidence-reference links navigate to the captured source; unavailable legacy
sources are identified. Related-control descriptions are not independently verified
official control identifiers. HTML/PDF exports carry the same interpretation notes.
An explicit insufficient-evidence scoring state is not implemented in this contract.
