# Phase 4 kickoff: remediation workflow contract

23 October 2026. **Remediation backend, Findings workflow UI and filters implemented;
scoring integration is not approved.** Phase 3
local-testing closure remains unchanged. See [validation](PHASE4_VALIDATION.md).

## Scope and delivery order

1. Finding remediation state, assignee, due date, rationale and history.
2. Permission-safe single-finding UI and API, then bounded bulk updates.
3. Re-import, archive/restore, membership and concurrent-edit safeguards.
4. Dashboard security summary and shared UI improvements.
5. Readiness/security hardening, measured performance and CI acceptance.

Cloud hosting, Docker, report-date UI, provider additions, live inference and
external ticketing are excluded. Scoring integration requires a separate decision.

## Code findings underpinning this proposal

- `backend/app/models/finding.py` stores source evidence and archive metadata,
  but no workflow status, assignment, due date or remediation history.
- `backend/app/api/routes/findings.py` provides organization-scoped lists,
  facets and creation. Existing creation permits organization admins/auditors.
- `backend/app/api/deps.py` already makes archived organizations read-only;
  platform-only sysadmin access does not grant organization write permissions.
- `backend/app/services/ingestion_service.py` skips matching findings using
  asset/source/category/description identity. Changed text or asset identity may
  create a different finding; this is not a stable external vulnerability ID.
- `frontend/src/app/(app)/findings/page.tsx` reuses selection and bulk confirmation
  for archiving manual findings. Imported findings must become selectable for
  remediation without becoming eligible for manual-only archive actions.
- `backend/app/services/scoring_service.py` and report evidence capture select
  active findings, not workflow states. Changing that would alter assessment semantics.

These are targeted code-review observations, not a full Phase 4 audit.

## Proposed lifecycle

| Status | Meaning | Required on transition into this state |
|---|---|---|
| Open | Work remains, including reopened findings | Reopening rationale when previously non-open |
| Accepted risk | Explicit business decision, not proof of remediation | Admin approval, rationale and review date |
| Mitigated | Compensating action applied; verification outstanding | Rationale and verification note |
| Resolved | Remediation verified for this finding | Rationale and verification note |
| False positive | Finding judged inapplicable or incorrect | Rationale and verification note |

All states may be reopened. Other transitions are explicit edits subject to the
same authorization and evidence rules; no silent status changes. Moving out of
Accepted risk requires admin approval too. A passed review date marks acceptance
overdue, not automatically Open or approved again. Review date must be future
when accepting/reaffirming risk. Due dates may be past to represent existing overdue work.

Verification notes are user assertions, not automatic technical verification or
qualified evidence for AI scoring. No attachments in the first increment.

## Proposed persistence and consistency

- Add finding workflow fields: status (default Open), nullable assignee user ID,
  due date (calendar date), risk review date, updated-at UTC timestamp and integer
  workflow version. Do not overload archive state or source `raw_data`/`details`.
- Append a history row for each actual change: organization/finding IDs, actor,
  timestamp, before/after values and bounded rationale/verification text.
  Status transitions and assignments must be attributable; no history-edit API.
- Notes are append-only history entries, not mutable source descriptions. Bound
  text lengths and reject blank required rationale; render as escaped plain text.
- Explicit null clears an optional field; omitted fields are unchanged. Reject
  unknown request fields. No-op updates create no fictitious change event.
- Write state, history and Activity event atomically. Every successful change
  increments version; stale expected versions return 409 without overwriting work.
- Proposed first limits: 2,000 characters per rationale/verification note,
  100 explicit unique finding IDs per bulk request. No unbounded “all matching”.
- Bulk mutation validates every row and expected version before applying any:
  all succeed or none. Lock rows in deterministic ID order and recheck organization
  archive/purge state in the transaction; coordinate with existing archive locks.
- Existing findings migrate to Open without fabricated historical transitions.
  Verify empty/existing PostgreSQL upgrades, downgrade constraints and drift.

## Permission and organization boundaries

| Caller | Read workflow/history | Ordinary edits | Enter/leave/reaffirm Accepted risk |
|---|---|---|---|
| Organization admin | Yes | Yes | Yes |
| Organization auditor | Yes | Yes | No |
| Organization viewer | Yes | No | No |
| Platform-only sysadmin | Existing read-only organization access | No | No |
| Nonmember | No | No | No |

An assignee must be an eligible active member of the same organization. Viewers
may be accountable owners but gain no write rights from assignment. Assignment is
optional, and due date is independent. Check current membership at mutation time.
If a user loses membership or is disabled, show “Assignee unavailable”; preserve
history and require an eligible replacement for reassignment. User deletion may
null the current reference without erasing prior assignment history, subject to
the existing account-deletion/privacy policy. Never expose foreign user details.

Archived organizations/findings are read-only; purging organizations are inaccessible.
Missing, archived, foreign or conflicting rows cause the whole bulk request to
fail without disclosing foreign metadata. Restoring the same finding preserves
its workflow. Restore deduplication was inspected: an archived duplicate with any
workflow history (version greater than zero) is restored intact, never silently
merged or deleted. Untouched duplicates retain existing purge-on-restore behavior.
This may leave two active findings representing the same source issue; they remain
distinct and both count under existing scoring rules. Consolidation is separate
work, not an automatic risk-acceptance transfer. Purge follows existing retention
rules, including scoped history cleanup; do not promise indefinite audit retention.

## Re-import and assessment boundaries

- Exact duplicate import must not reset status, assignment, dates or history.
- A genuinely new finding defaults to Open. Changed source text is not sufficient
  proof of identity: do not automatically transfer risk acceptance or resolution.
- Source evidence refresh must not masquerade as a user workflow change.
- First delivery: deterministic scores, AI inputs, coverage rules and report
  schemas remain unchanged. Resolved/accepted findings still participate exactly
  as today; UI must clearly disclose this rather than imply risk reduction.
- Existing report snapshots and exports remain immutable. Later status-aware
  scoring requires versioned rules, capture-time workflow provenance and separate
  acceptance; no retroactive report rewrite or automatic evidence qualification.

## API delivery boundary

Implemented in this increment: GET/PATCH
`/orgs/{org_id}/findings/{finding_id}/workflow`, GET its `/history` (offset/limit),
and POST `/orgs/{org_id}/findings/workflow/bulk`. PATCH requires `expected_version`;
bulk uses `targets` (finding_id/expected_version) and `patch`. A rationale-only
PATCH is an explicit appended note. Explicit unchanged fields create no history.
Workflow GET returns status/version, assignee availability, dates and updated_at.
First history page is newest first; no history mutation endpoint is provided.

Finding-list responses now include status/version, assignee ID/label and deadline
dates. Status and assignee multi-select filters, due/risk-review overdue filters,
global search over workflow labels and new sorting columns are implemented.
Counts and domain chips use the same filter scope. Facets expose only active
findings and same-organization, active-account assignee labels; removed or disabled
owners are labelled unavailable without exposing foreign account details.

- Extend finding read/list responses with workflow fields; add status, assignee,
  due/overdue filters with consistent counts, facets, paging and URL state.
- Organization-scoped finding workflow detail and paged history reads.
- PATCH single workflow: explicit patch plus expected version and rationale.
- POST bulk workflow: explicit IDs/expected versions plus shared patch/rationale.
- Separate note creation from status change. Successful note writes also use a
  version check to make retries safe from silent duplication; after uncertainty,
  refresh history/version before retry. Do not auto-retry non-idempotent writes.
- Map validation to 422, insufficient permission to 403, inaccessible finding to
  non-disclosing 404, and stale/archived conflicts to structured 409 responses,
  while preserving existing organization-access denial conventions.

## Findings UI delivery

25 October lifecycle/permission fencing: privileged organization mutations enter
through `require_org_role`/`authorize_org_write`, acquiring job admission before
an Organization NO KEY UPDATE row fence, then refreshing lifecycle, membership,
role and active-account state. Competing archive/role changes serialize until
transaction end. Bulk archive repeats admission after every independent commit,
retaining prior jobs and explicit refusals. Manual finding creation also takes
the inventory advisory lock, refreshes asset/upload references, and refuses
unfinished archive batches (409) or archived/invalid references (422).
This does not cancel previously committed jobs retroactively, impose workflow
version tokens on settings, or make browser selections cross-user reservations.
See [multi-user contract](MULTIUSER_CONCURRENCY.md) for scope/performance limits.

The implementation uses the existing Findings page, not a separate disconnected task database.
Add a compact Status column and row action opening workflow detail; show owner,
due date, risk-review date, notes and paged chronological history there. Keep
source evidence visible and distinct from user notes. Use existing shared forms,
dialogs, filters, pagination and confirmation controls after inspecting them.

Provide status/assignee/overdue filters and a bounded selection action. Selection
eligibility is action-specific: imported findings support remediation, not manual
archiving. Reset selections on organization/filter scope changes; display exact
bulk target count and reject stale or inaccessible selections server-side.

Read-only roles receive a visible explanation, not broken edit controls. Include
loading, empty, save-in-progress, validation, conflict/reload and failure states.
Keep unsaved input on recoverable errors; don't report success before commit.
Keyboard navigation, labelled inputs, focus return/trapping, escape/close behavior,
status text beyond color and narrow-screen layout are acceptance requirements.

## Verification gates

1. Unit: transitions, permission decisions, patch/null semantics, date boundaries,
   note limits, versions and no-op behavior.
2. PostgreSQL integration: roles/tenant isolation, membership changes, atomic
   history/events, stale edits, bounded bulk rollback, archive/purge races,
   import duplicate/new identity and restore deduplication behavior.
3. Regression: imports, archive/restore/purge, dashboard scoring, reports/evidence
   capture, immutable prior snapshots and existing read-only sysadmin behavior.
4. Frontend: form/filter/selection states, all lifecycle states, conflicts,
   permissions, keyboard accessibility and organization switching.
5. Installed Chrome: end-to-end lifecycle and history, bulk success/failure,
   read-only roles, re-import preservation and responsive/accessibility checks.
6. Backend full suite on PostgreSQL, focused concurrency tests, migration round
   trip/drift check, frontend suite, lint, TypeScript and production build.
   Record actual counts; focused runs do not replace full-suite evidence.
7. Review exact diffs for authorization/data integrity and secrets. Simplify
   unnecessary complexity without unrelated rewrites. Update manual, roadmap and
   validation summaries before separately authorized commits/pushes.

## Implementation decisions and remaining review

### Simplified local-time presentation and shared date-only filters

One signed-in layout notice states that times are browser-local. Deadline cells,
current details and history render concise local date/time values without IANA
names, original-zone duplication or conversion explanations. Timezone/expiry
metadata remains intact. Visible expiry adjustments are represented as deadline
changes in history; equivalent zone aliases do not produce unchanged arrows.

The common list state injects `filter_timezone` for nonempty since/until filters;
it is processing metadata, not a new UI control or persisted shared-link timezone.
The common DateRange dependency applies start-local-day inclusive / next-local-day
exclusive bounds across all existing date-filter screens. Empty endpoints remain
unbounded, invalid/reversed/impossible ranges fail closed, and API callers without
a browser-provided zone retain the previous UTC default. No migration is needed.
The implementation includes the entire final minute, not just exactly 23:59:00.

### Browser-authored timezone correction (supersedes fixed Eastern rule below)

New deadline writes require `deadline_timezone` from the entering browser's
`Intl.DateTimeFormat().resolvedOptions().timeZone`. No timezone-only writes are
accepted. Each due/review date has independently persisted IANA zone and UTC expiry
at the exclusive next-local-day boundary. Keep/note/assignment changes do not
reinterpret deadlines; clearing a date clears its metadata. Cross-zone bulk setting
applies the entering zone only to explicitly set dates. Invalid zones, unavailable
browser timezone and non-existent local days fail closed.

Migration 0023 backfills existing dates only with the previously agreed Eastern
interpretation, preserving source, workflow/version and history. This is a legacy
rule, not the default for new date submissions. Overdue and date sorting use the
fixed expiry; risk acceptance retains the future-calendar-date rule in its recorded
zone. Displays show original date/zone plus the expiry end time in the viewer's
machine timezone. Existing shared timestamp formatting is already browser-local.

Downgrade loses author-zone/expiry metadata: export and explicit operator approval
are required outside disposable tests. A later upgrade cannot recover authored zones
from dates alone; it would apply the legacy Eastern rule. No production downgrade
or normal-schema migration is authorized by this increment.

### Manual entry, archive guidance and Eastern deadlines

Admins/auditors can add organization-level manual findings with domain, severity,
description and optional category. UI fixes source to manual and omits scan ID.
Archive eligibility is exposed by organization facets; an unavailable archive
option explains manual entry versus imported upload/asset archive. Sort labels
retain nonshrinking arrows and the risk-review column has additional width.

Finding deadlines now use a single explicit `America/New_York` calendar-day rule,
including DST. Existing date-only fields are interpreted in that zone without
rewriting data: overdue means stored date is before the current Eastern date.
Risk acceptance requires a date after the current Eastern date. This supersedes
the initial UTC comparison below. With one application-wide zone, storing another
derived Unix boundary is unnecessary; per-user timezone deadlines remain outside
this increment. `tzdata` is pinned for Windows portability.

Individual imported-finding archiving and scan reconciliation are **design only**,
per the user's explicit selection. See [proposal and approval gates](FINDING_RECONCILIATION_DESIGN.md).
Mandatory-note relaxation remains a separate contract proposal, not implemented.

### Note visibility and mixed-selection follow-up

25 October UI simplification: Findings uses one cross-page selection (maximum
500), without a selection-mode dropdown. Workflow remains a maximum-100 atomic
operation and is disabled above that count. Archive is enabled only for an
all-manual available selection; mixed/imported targets are not silently skipped.
Eligibility metadata survives paging but remains non-authoritative; backend
roles/archive/job boundaries still validate requests. Bulk archive confirmations
freeze their target IDs/count/names. Row Workflow and manual Archive are together
in a sticky, labelled Actions column; checked rows do not disable row actions.
Viewers can inspect row workflow but have no mutation controls. Saved reports,
scoring, workflow note policy and imported-finding archive rules are unchanged.

The dialog provides a prominent saved-notes/history shortcut (current-page count,
not a total), explicit rationale/verification labels and new-entry guidance.
Bulk selection displays current status counts; Keep preserves individual values.
Risk-review Set is available only when all resulting statuses are Accepted risk;
Clear is unavailable if any resulting status remains Accepted risk. Retained
incompatible drafts block saving rather than silently dropping selected actions.
Server validation and atomic bulk semantics remain authoritative and unchanged.

Latest rationale and latest nonempty verification are independently queried by
finding/org/version, not inferred from the displayed history page. Their author
and timestamp remain attached; inputs create new entries. History renders only
the four supported workflow fields when their raw values differ. New history
JSON snapshots capture assignee labels without changing state/version comparison;
legacy labels resolve only active same-org members, falling back to unavailable.
No historical backfill or migration is required. Technical UUIDs stay expandable.

Mandatory-rationale policy is unchanged: every submission requires a rationale;
Mitigated/Resolved/False positive transitions additionally require verification.
**Proposed, not implemented:** optional rationale for assignment-only/date-only
edits, while retaining required rationale for status changes and note-only entries.
That policy requires separate contract approval, backend validation changes and
unit/integration/browser regressions. No optional-note behavior is claimed here.

The first backend increment uses admin-only risk-acceptance edits (including
assignment/date changes while accepted), required transition verification notes,
future UTC risk-review dates, unchanged scoring and all-or-nothing 100-item bulk
requests. Auditors may append notes on accepted-risk findings, not change their
workflow fields. It preserves edited duplicates on restore as described above.
History is append-only through application APIs, not a database-level prohibition
on privileged SQL maintenance. Schema downgrade deliberately removes workflow and
history; export/backup and explicit operator approval are required outside tests.
Frontend presentation and list filters are implemented. Broader Phase 4 work
(dashboard summary, readiness/security hardening, performance and CI expansion)
remains pending. See validation for exact completed checks, not a Phase 4 closure.

Requested `feature-dev`, `code-review`, `frontend-design` and `code-simplifier`
skills were not available in this session. The workflow above applies those
disciplines but does not claim execution of unavailable skill instructions.
