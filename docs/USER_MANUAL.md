# AuditMind user manual

Password fields are hidden by default. Use **Show** beside a field to reveal it,
then **Hide** to mask it again. This applies to sign-in, registration, current/new/
confirmation passwords, and admin temporary-password handovers. Each field works
independently; reopening the screen or receiving a new handover starts hidden.
Temporary passwords can still be copied while hidden. Visibility does not change
the password or submit the form. Avoid revealing passwords during screen sharing
or when someone can see your screen; the clipboard is also sensitive. Password-
manager autocomplete and paste remain supported.

Platform admins: open **Platform → Product branding → Sidebar product logo size**
to choose Small **144 × 40**, Medium **180 × 48** (default) or Large **192 × 64**.
The choice saves automatically across all organizations; refresh other sessions.
Organization admins cannot edit it. Sign-in branding, company logos and company
name sizes are unchanged. No new logo file or rebuild is needed for size changes.

To enlarge the company name, open **Settings → Organization logo → Header company
name size**: Small **16px**, Medium **20px** (default), Large **24px**. It saves
automatically for all organization members; other sessions update on refresh.
Only admins can change it. It affects the common header only, not the organization
selector or product logo. If the name is hidden beside a logo, enable **Show
organization name beside logo** to see the new font size.

To enlarge your company logo, open **Settings → Organization logo → Header logo
size**. Choose **Small (96 × 48)**, **Medium (160 × 64)** or **Large (224 × 80)**.
Medium is the default. It saves automatically for the organization; other sessions
update on refresh. The preview and header preserve the logo's proportions. This
does not change the AuditMind product logo. If artwork still looks small, check
for transparent padding inside the uploaded image; sizing cannot add image detail.

In **Settings → Organization logo**, admins can turn off **Show organization
name beside logo** when the artwork already includes the name. It saves
automatically for all members; refresh other sessions to see it. The header
always shows the name if no usable logo is available. The organization selector
is unchanged. Header names use configurable medium-weight text (20px default); the sidebar product logo
uses a 180×48px box with the existing SVG. Sign-in sizing is unchanged.

Brand placement: the product logo appears in the sidebar, while the application
header shows only the selected organization's name/company logo. Authentication
keeps its single larger product logo above the card.

Sign-in and registration now share a single larger logo above the card, clearer
workspace descriptions and consistent keyboard-accessible controls. This is a
presentation change only; passwords, sessions and sign-up policy are unchanged.

Approved product-logo trials: replace the fixed product SVG and browser icon;
[locations and exact refresh/restart steps](PRODUCT_BRANDING.md). These are
separate from company logos managed through Settings.

New local Phase 4 features: [Dashboard security summary, readiness, multiple-file
import and branding](PHASE4_LOCAL_OPERATIONS.md). Admins can now use
**Settings → Organization logo** to upload/replace/remove logos; members see
them in the common header. See [limits and Chrome steps](ORGANIZATION_LOGOS.md).
Broader hardening remains pending. Initial backend audit findings are addressed in the
separate [dependency compatibility increment](BACKEND_DEPENDENCY_REMEDIATION.md).

New Phase 4 functionality: [what changed and how to verify it in Chrome](PHASE4_USER_VERIFICATION.md).

Search performance (25 October): specific Findings text/IP searches now use
PostgreSQL indexes. Matching semantics and filters are unchanged. Prefer at least
three specific characters; one/two-character terms and broad matches can still
take several seconds. Full Finding IDs use exact lookup. See
[measured results and limitations](FINDING_SEARCH_PERFORMANCE.md).

Phase 4 remediation tracking now includes the Findings workflow UI and filters.
See [the workflow contract](PHASE4_REMEDIATION_DESIGN.md) and
[validation/delivery limits](PHASE4_VALIDATION.md). Running the updated backend
against an existing database requires migration 0023 first; do not restart or
deploy it against an unmigrated database. On 23 October 2026 the isolated
`auditmind_demo` schema was upgraded to 0023 for timezone-aware deadlines. The normal application
schema is not migrated automatically. Scoring and existing report snapshots remain unchanged.

### Manage a finding's workflow

#### Upload protection

Upload protection: imports, documents and logos share a per-address/process
request quota (default 120 attempts/minute). If an upload reports 429/Too many
upload requests, wait for the server's retry interval, then retry only the failed
file; do not resubmit files already accepted. Shared proxy/NAT users may share
the quota. Document files remain limited to 10 MiB and logo files to 2 MiB;
transport limits also bound multipart overhead. These controls do not constitute
malware scanning. [Security details](SECURITY_HARDENING.md).

#### Job notifications

Routine successful archive, restore and purge confirmations clear automatically
after 10 visible seconds on the current screen. Hovering the message, focusing
its controls, hiding the browser tab or scrolling it out of view pauses the timer.
**Dismiss** remains available. Once dismissed, the confirmation stays dismissed
on other screens and after refresh; the job, Activity history and archived data
are not deleted. Automatic dismissal does not count as sign-in activity.

Running/queued/interrupted jobs and failures remain visible. Restore messages
about findings kept archived or duplicates purged require manual dismissal, as
do grouped results containing any failure or warning. A dismissal failure shows
an error and allows manual retry; it does not retry in a loop. Detailed upload
reports and their warnings/errors retain their existing manual review behavior.

Organization **Settings** now uses the full available content width, like the
other screens, with wrapping controls and locally scrollable tables on narrow
viewports. Setting values, permissions and save actions are unchanged.

#### Locate a finding by its ID

- In **Findings**, expand **Finding ID** below a finding's description to see its
  internal UUID. **Copy ID** copies that identifier; a message reports success or
  clipboard refusal. Success disappears after 3 seconds; copying again restarts
  that timer. Failure messages remain visible. No extra table column is added.
- Paste a complete Finding ID into **Search findings**. Complete UUID searches
  match the ID exactly (case-insensitively), not descriptions mentioning it.
  Partial UUID text is an ordinary text search, not an ID-prefix lookup.
- Workflow dialogs' **Technical finding IDs**, report evidence/remediation
  finding references, and organization Activity workflow-event IDs are links.
  A link verifies organization access, selects that organization, then opens
  **Findings** filtered to the exact ID. Save or discard an editing draft before
  following a link; a link does not save it.
- These links show current active data, not historical report snapshots. Archived,
  purged, missing or synthetic-only IDs can return no active findings. Existing
  reports and audit history are not changed. **Clear filters** returns to the list.
- Finding IDs are not Asset IDs, Upload IDs, scanner IDs/QIDs or CVE identifiers.
  Asset/upload references are not interpreted as finding links. Organization
  access remains enforced by the API, including when an address is edited.

#### Edit workflow

Admins/auditors can use **Findings → Add finding** to enter a description, domain,
severity and optional category. It creates an organization-level manual finding
with source `manual` and no scan association. Existing filters/sorting may hide
the new row; clear filters and search its description if necessary. Use **Archive**
in the row's sticky **Actions** column, or select manual findings and use
**Archive selected** above the table. There is no **Select for** mode. Bulk archive
is enabled only when every selected finding is manual and available. Imported findings remain
archivable with their upload/asset, not individually. See the
[design-only reconciliation proposal](FINDING_RECONCILIATION_DESIGN.md).

1. Select your organization and open **Findings**, then **Workflow** in the
   finding's sticky **Actions** column, beside Archive for eligible manual findings.
   Row actions are independent of checked rows. The dialog identifies its organization and exact targets.
   Use **Saved notes and history** near the top to jump directly to saved entries.
   Each entry labels its rationale and verification note; the empty editing fields
   create a new entry, not replace a saved one. The shortcut count is for the
   current history page, not a total count.
   The current-details area also shows **Latest rationale or note** and **Latest
   verification note**, each with its own author/time. A later note does not erase
   an earlier verification note. History displays only changed workflow fields;
   note-only entries say no workflow fields changed. Assignee changes show saved
   names/email (safe same-org lookup for older entries), not raw IDs. Expand
   **Technical finding IDs** to see internal finding UUIDs, not CVE/scanner IDs.
   Raw assignee IDs are retained in audit data but are not displayed in the dialog.
2. Choose **New status**, or keep the current state to add a note. Organization
   admins and auditors can make ordinary changes; viewers can read current state
   and paged history without receiving edit controls.
3. Use **Find assignee** to filter organization members by name/email only, not
   role or account status. The People-page search still includes role/status.
   Results appear in **Assignee** after a short
   pause; **More assignees** pages through 50 results at a time. Searching alone
   does not assign anyone: select a member, enter a rationale, then **Save workflow**.
   An empty result is explicitly reported; clearing search restores the choices.
   The selected name/email remains visible when searching another page.
   Choose **Keep current assignee** to preserve the owner or **Unassigned** to clear it.
   Deactivated members are excluded. Assignment grants no
   additional permissions. A removed/deactivated owner is shown as unavailable.
4. Date actions distinguish **Keep**, **Set** and **Clear**. Remediation due dates
   may be in the past. New dates use the entering browser's timezone internally.
   Risk acceptance requires an admin and a future calendar date in that
   deadline's recorded timezone. Auditors may add notes on accepted-risk findings,
   not change their fields. Keep preserves each existing date, timezone and expiry;
   explicitly setting a date records your browser's timezone even if the date text
   matches the old one. Clear removes the date and its timezone/expiry metadata.
5. Enter **Rationale or note**. Transitions to Mitigated, Resolved or False positive
   also require a **Verification note**. These are user assertions, not automated
   verification or proof of compliance. **Save workflow** records state and history.
6. Select findings with the checkboxes; the bar labelled **Actions for selected
   findings** offers both **Update selected workflow** and **Archive selected**.
   While any findings are selected, individual row Workflow/Archive/Undo actions
   are disabled. Use **Clear selection** before operating on a single row.
   Selection persists across pages, up to 500. Workflow updates support at most
   100 selected findings; reduce a larger selection to enable that action.
   Imported findings are eligible for workflow, but bulk archive requires all
   selected findings to be eligible manual rows. Mixed/imported selections disable
   Archive selected with an explanation; no imported rows are silently skipped.
   Archive confirmation shows the count and names (first ten for long lists) and
   freezes the selected target IDs. Server-side validation still applies; explicit
   refusals are shown if concurrent changes prevent an item from starting.
   Archive confirmation is modal: background selection/actions are unavailable
   until confirm/cancel. Row Archive identifies one finding and its UUID and says
   **Archive 1 finding**; other checked rows are excluded. Bulk Archive shows its
   frozen names/count with **Archive N findings**. Cancel receives initial focus;
   Escape cancels before submission. Cancellation is blocked while submitting.

   Multiple organization members may work concurrently. Workflow conflicts require
   reloading before retry; a bulk workflow conflict rolls back every target.
   Archive bulk jobs instead report per-item refusals. Settings/profile/consent
   writes are serialized, but the same explicitly edited field is last-writer-wins.
   Other users' changes may require a reload to appear. See
   [multi-user behavior and review limits](MULTIUSER_CONCURRENCY.md).
   Privileged writes now wait for an organization transaction fence and recheck
   current access before proceeding. If an admin archives the organization or
   removes/demotes/deactivates the caller first, the waiting write is refused.
   A write admitted first finishes its transaction before the competing change.
   Findings cannot be added against an asset/upload with an unfinished archive;
   archived references are rejected after refreshing current database state.
   Previously committed background jobs are not retroactively cancelled by a
   later role change. Bulk archive reports committed jobs and refuses later items
   if access changes between its independently committed admissions.
   Review workflow's exact targets before **Apply to N findings**.
   The bulk dialog lists current status counts. **Keep** preserves individual
   values; explicit changes apply to every target, with no silent skipping.
   Setting a risk-review date requires every resulting status to be Accepted risk;
   clearing it is unavailable while any resulting status remains Accepted risk.
   An incompatible retained date action blocks saving until corrected. Read saved
   notes by opening each individual finding's workflow. Successful actions clear
   selection; completed background jobs also clear stale selections. Filter or
   organization changes reset selection.
7. Filter with the Status/Assignee column pickers and **Overdue**. Deadlines become
   overdue at their persisted expiry instant (start of the next day in the entering
   user's timezone); resolved/false-positive findings
   are excluded from remediation-overdue results. Risk-review overdue applies to
   accepted risk only. Dates remain unchanged automatically when they become overdue.
   Column headers sort; filters/sort/page are kept in the URL across refresh.
   Changing filter scope or organization clears selection.

8. On a conflict or uncertain network/server result, the draft stays visible and
   saving is blocked. Use **Reload latest state**, inspect current state/history,
   and review your retained draft before submitting again. There is no automatic
   write retry. A stale bulk update changes none of its targets.

Migration 0023 retains existing dates and assigns them their agreed legacy Eastern
interpretation (`America/New_York`, including DST), storing their UTC expiry. New
dates are **not** forced to Eastern: the browser supplies its timezone and the
backend calculates a fixed UTC boundary. For October 25, 2026, Eastern expiry is
October 26 04:00 UTC, while Kolkata expiry is October 25 18:30 UTC. Other viewers
see the deadline date/time in their own browser timezone, without technical zone
details; changing
machines or travelling does not move a saved deadline. Deadline sorting uses actual
expiry instants. Other timestamp displays continue using the browser timezone.
API clients must supply `deadline_timezone` with any explicitly set deadline date;
timezone-only edits are rejected. Bulk setting uses one entering timezone for those
explicit changes, while Keep preserves each target's individual deadline metadata.

### Time display and date filters — all screens

All displayed times use the accessing browser's timezone. A single shared notice
states this; table cells and workflow summaries do not repeat timezone names,
origin-zone metadata or UTC conversion explanations. Original timezone/expiry
metadata remains stored for correct processing and audit, not removed from records.

Existing date-only From/To controls remain unchanged. Processing defaults are:

- **From:** 12:00 AM at the start of the selected browser-local day, inclusive.
- **To:** the entire selected day through 11:59 PM, including its seconds/fractions.
  Internally the query is strictly before the next local midnight, so no records in
  the final minute are lost. DST days may contain 23 or 25 hours, not always 24.
- A blank endpoint is unbounded. Invalid timezones, reversed ranges and impossible
  local days are rejected. Changing/share-opening a date-filter link uses the new
  viewer's browser timezone; it does not move stored finding deadlines.

This shared rule covers the existing Findings, Uploads, Archived, Reports, Documents,
People and organization/platform Activity date filters. It adds no time selectors
or new date filters to screens that do not already have them. Web requests supply
`filter_timezone` automatically; direct API clients omitting it retain UTC behavior.

Workflow status does **not** reduce deterministic scores or rewrite reports in this
delivery. Matching re-imports preserve decisions. Restore preserves edited duplicate
findings and their history; both remain independently counted until an explicit
consolidation policy is implemented. Purge intentionally removes associated history.

For the opt-in evidence-aware reporting changes, use the
[step-by-step verification guide](EVIDENCE_USER_VERIFICATION.md). It separates
normal-demo checks, saved screenshots/exports and isolated mocked Chrome tests;
no real inference or credential changes are needed.

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

An organization admin can choose **Settings → Ingestion → Exact duplicate files**:

- **Ask before importing again** (default): completed byte-identical files appear
  in the grouped decision list. Upload selected anyway explicitly confirms them.
- **Skip identical files**: no new import/job/report; the queue counts them as
  skipped and **Activity → Exact duplicate file skipped** records the matching
  upload and reason. Even an explicit confirmation cannot override Skip.
- **Reimport identical files**: start another import without prompting. Existing
  asset/finding rules still apply; this is not a guaranteed record update.

The comparison is SHA-256 within the current organization, across shared import
sources/profiles. Filenames are not identity; different content with the same
name is a new file. A matching queued/running import is always skipped under all
three policies, preventing concurrent duplicate jobs. Failed or archived matching
imports are excluded from duplicate matching. Reprocessing after profile changes
requires Reimport or Ask with explicit confirmation. Reset to default follows
the server's EXACT_DUPLICATE_FILE_POLICY (Ask unless configured otherwise).
This setting is independent of **Asset already in inventory**, and applies to
Assets/Findings uploads, not document-version or logo-replacement workflows.

You can also drag one or more files onto the Assets/Findings page content (not
just the small upload button); the same review queue opens once. File drops on
other signed-in pages do not open the file in the browser or start an import.
Native Documents/logo file inputs remain usable. Drop onto page content, not
Chrome's address bar or tab strip, which the application cannot control.

Selecting files opens **Upload files**, keeping the page header compact. Review
the source on each file; **Detected** means its columns matched the source.
Close (or Escape while idle) asks before removing remaining queued files.
Keep reviewing retains them. Remove affects only that queued file; closing never
cancels submitted imports. Upload is disabled until its source is compatible.
If no source matches, configure an import profile in Settings, convert the file,
or remove it.
The dialog cannot close during submission. Once every selected file is accepted,
it closes automatically; the submission notice disappears after 3 seconds.
Background work continues independently. Use **Show progress and reports** while
processing, or **Show reports** after completion. The expanded summary says **Hide**.
Expand the summary
on Assets/Findings to inspect each file. Failures/interruption open the summary
for attention; reports and errors remain available until explicitly dismissed.

1. Open Assets or Findings and use its import/upload control.
2. Choose a supported CSV, JSON, Nessus or configured tool-export file. Select or
   confirm the correct source/import profile when prompted. Not every arbitrary
   vendor export is supported; the profile must recognize its structure.
3. Review the result: imported, updated/skipped and invalid rows are distinct.
   When selecting or dropping multiple files (up to 20), review each source and
   choose **Upload all ready files (N)** to submit them sequentially. Individual
   Upload/Cancel controls remain available before the batch starts. Sources and
   queue changes are locked during submission. **Stop remaining uploads** stops
   after the current request; it does not cancel accepted jobs. Failed files stay
   in a **Submission failed** group for **Retry failed**. Duplicates do not stop
   later ready files: under Ask they collect under **Already uploaded (N)**. Review previous
   uploader/date, select individual files (or Select all), then **Skip selected**
   or **Upload selected anyway**. No duplicates are selected/approved automatically.
   Files with unreadable sources stay under **Source needs attention**; correct
   their source or cancel them, then submit the remaining ready files.
   Upload anyway permits another import, not a guaranteed update: Settings still
   determine existing-asset handling. Accepted files are never included in later
   retries or duplicate decisions. This covers all supported Assets/Findings
   formats/sources. Documents and logos remain single-item version/replacement
   flows, not multi-file imports.
   Each file keeps its own report; submission completion is not import completion.
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

**Preview vN** opens the saved text directly beneath that document's row, like
**Uploads → Report**. The panel identifies the title, version and edition; only
one version preview is open at a time. Use **Hide preview vN** or **Close preview**
to collapse it. Closing from the panel returns keyboard focus to its toggle.
Loading, permission/network errors and **Retry preview** stay inside the panel.
The text area can receive keyboard focus for scrolling long documents.
Changing filters, sorting, page or organization closes the old preview. Removed
versions cannot be previewed. Preview is read-only and does not index documents,
approve processing, execute embedded HTML, or modify saved reports.

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
An opt-in evidence-aware report contract is available for controlled rollout.
When enabled, insufficient/limited/conflicting domains are not scored; partial
reports can complete successfully without an overall AI score. Existing legacy
scores are preserved and their evidence status shown as not recorded. Default
reporting remains unchanged until operators enable the new contract and review
its [qualification rules](EVIDENCE_COVERAGE_PROFILES.md). Deterministic baseline
remains separate. The Reports page can filter complete/partial new assessments;
legacy reports are included under All. Null scores sort last, not as zero.
# Synthetic evidence-state demonstration

Four persistent mocked report examples are available in the separate
**Evidence examples - SYNTHETIC ONLY** organization. See
[the demonstration guide](SYNTHETIC_EVIDENCE_EXAMPLES.md) for access and limitations.

## Finding deadline validation

Due dates and risk review dates include the entire selected day in the entering
browser's timezone. Newly set dates cannot precede the finding's creation day in
that timezone. Today is allowed. Accepted risk additionally requires a review
deadline that has not expired: it expires at the start of the next local day.
Bulk edits validate every finding and reject the entire update if any target
fails. Keeping an existing deadline does not reinterpret it in another timezone.

## Archived selection and actions

With no selection, use a row's **Restore** or (admins only) **Purge** action.
Select checkboxes for one or several archived items to use **Restore selected**
or **Purge selected** in the selection bar. Row mutation actions are disabled
until you **Clear selection**; reports remain readable. Selection is retained
across pages, up to 500 items, and reset by filter/organization changes or
completed jobs. Purging items cannot be restored; restoring items cannot be
purged. Incompatible selections disable the corresponding bulk action rather
than silently skipping items.

Review the confirmation's item count and expandable names/IDs. The confirmation
blocks background selection changes until you confirm or cancel; Escape cancels
before submission. Purge is permanent and cannot be undone. Bulk operations may
queue some jobs and refuse others if availability/permissions changed; review
the refusal details. This is not a database-wide atomic bulk transaction.
Assets and Uploads use the same selection/confirmation safeguards.
# Reading resilience scores

An organization with **zero active assets and zero active findings** displays
**Not assessed** for the overall score and all seven domains, without numeric
scores or risk tiers. Archived records do not count as active data. This is a
narrow empty-data safeguard: asset-only or partially covered organizations still
use the existing findings-based baseline, which is not proof of evidence coverage.
The optional evidence-qualified mode below changes this interpretation only when
an organization administrator explicitly enables it.

Dashboard and browser Reports retain their original compact layout. Only score
and risk-tier text colors indicate risk: Critical red, High orange, Medium amber,
Low green. No new colored card backgrounds, bordered badges or explanatory
blocks are added. Existing textual tier labels remain; color is not the sole cue.
Scores and thresholds are unchanged. Evidence coverage/confidence remain separate;
unscored report domains stay neutral. Downloaded templates are unchanged.

## Evidence-qualified Dashboard pilot

Under **Settings → Scoring and evidence review**, an organization admin can enable
**Evidence-qualified scoring** after confirming the change. It is **off by default**.
Off means the findings-based baseline described above; on means current reviewed
evidence is required before a domain receives a score. This does not change saved
reports, scoring deductions or domain weights, and it makes no AI calls.

Use **Evaluate evidence across all domains** to queue an organization-wide worker
job. The selected domain below only controls the qualification editor. Evaluation
uses saved records across all seven domains. Its status, processed/total count,
elapsed time and Cancel remain in the Organization-wide evaluation section.
You can navigate away and reopen Settings to follow the same job. Simultaneous
requests share an active job; only its requester or an org admin may cancel it.
Keep the worker running. Cancellation waits for the current database fetch and
never publishes a partial result.

With the setting on, eligible domain scores use the existing baseline calculation;
missing/stale/expired/conflicting evidence stays unscored. The overall score needs
all seven qualified domains with compatible scope, not just the selected domain.
Material inventory/source/review changes invalidate cached eligibility; rebind and
review affected qualifications where needed, then evaluate again. Dashboard does
not trigger a full scan automatically. An open Dashboard checks current mode and
evidence state every ten seconds/on focus, so another user's change is not an
instant server-pushed update. Failed verification hides scores.

Turning the setting off restores baseline interpretation without deleting reviews.
Follow [the Chrome walkthrough](EVIDENCE_USER_VERIFICATION.md) using synthetic test
data first. Production rollout/default-on adoption remains a separate decision.
