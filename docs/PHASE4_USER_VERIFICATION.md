# Phase 4 changes and Chrome verification

26 October 2026. This increment is for **local synthetic testing**, not production
or live-AI release acceptance. No provider calls or paid inference are needed.

## What changed

- Findings: manual entry; single/bulk remediation workflow; assignee and deadlines;
  mandatory rationale, transition-specific verification and attributed history.
- Traceability: finding UUID lookup/copy and links from Activity/report references.
- Actions: one checkbox selection, row actions disabled during selection, separate
  workflow/archive limits, exact frozen targets and modal archive confirmation.
- Dates: browser-local display and calendar-day filters; deadlines store their
  authoring timezone and fixed UTC expiry, including daylight-saving boundaries.
- Concurrency: optimistic workflow versions and atomic bulk workflow; privileged
  write-admission fencing rechecks lifecycle, membership, role and account state;
  archive bulk admission rechecks each independently committed item.
- Search: migration 0024 adds concurrent pg_trgm/support indexes. Specific searches
  became substantially faster; short/broad searches can still take seconds.
- Shared UI: success notification timing, full-width Settings, inline Documents
  previews and clearer workflow history/assignee labels.
- Tooling: patched undici/zod transitive dependencies, isolated acceptance builds,
  worker metric-session cleanup, migrations and regression/Chrome tests.

## Start safely

1. Open **Chrome → http://localhost:3000**. If the demo is stopped, run
   `powershell -ExecutionPolicy Bypass -File .\start-demo.ps1` from the repository.
2. Sign in with your existing demo credentials, then select **SA01** (or another
   synthetic organization where your account is an admin). Do not paste passwords
   into screenshots, issues or terminal commands. Credentials are not in this guide.
3. Use only synthetic findings for edits. Do not change AI keys, processing consent
   or provider settings. Do not use Purge for this walkthrough.

## 1. Create two manual findings

In **Findings → Add finding**, create `Phase4 Chrome check A` and
`Phase4 Chrome check B`. Choose Domain/Severity and enter Description; Category
is optional. Search `Phase4 Chrome check` to isolate them. Both should have source
**manual**, initially Open, with row **Workflow** and **Archive** available.
**Upload file** remains the primary import action; manual entry is separate.

## 2. Edit workflow and inspect saved history

With nothing selected, click A's **Workflow**. Choose an assignee after searching
their name/email, set a due date and enter **Rationale or note**, then save.
Searching alone does not assign anyone. Reopen the dialog: current values and
**Latest rationale or note** should persist with author/time.

Change status to **Mitigated**, supply rationale and **Verification note**, save
and reopen. Verification is also required for Resolved/False positive transitions.
Blank rationale should block any submission. Saved notes are assertions, not
automatic evidence qualification; workflow status does not rewrite saved reports
or change deterministic scores.

In **Workflow history**, check human-readable assignee labels and only changed
fields. An unchanged assignee/date must not produce a before → identical-after
entry. Notes/history remain paged; **Saved notes and history** opens the history area.

As admin, you can separately test **Accepted risk** with a future review date.
For a selection with mixed resulting statuses, setting a shared review date must
be blocked unless every resulting status is Accepted risk. Cancel that draft if
you do not intend to update all selected findings. Auditor access to accepted-risk
findings is note-only; viewers cannot write.

## 3. Verify identifiers and search

Expand A's **Finding ID**, click **Copy ID**: the success message disappears after
three seconds. Paste the complete UUID in common search: only that active finding
should appear. Follow its reference from Activity/history/report where available;
it must open the correct organization and finding. **Clear filters** restores the list.

For larger SA01 data, use a specific known description/IP, not `s` or `ss`.
Historical `ssss` measurements returned two findings, but that count depends on
retained demo data; adding/archiving records can change it. Chrome **F12 → Network**
can show the Findings request duration. A fresh restart may be slower than repeats;
the API timing does not include typing debounce or rendering. See
[measured search results](FINDING_SEARCH_PERFORMANCE.md), not a universal SLA.

## 4. Verify selected versus individual actions

Check A and B. **Update selected workflow** and **Archive selected** should be
available; **all individual row Workflow/Archive actions must be disabled**.
Click **Clear selection** to restore row actions. Workflow supports at most 100
selected findings; archive selection supports up to 500 eligible manual findings.
Selection can span pages, and clears on organization/filter-scope changes.

Select a manual and an imported finding if available: workflow may remain enabled,
but Archive selected must be disabled with an explanation. No imported item is
silently skipped. Individual imported findings are not supported for archive;
their upload/asset is the archive unit. Later-scan reconciliation is design-only.

## 5. Verify archive targeting, blocking and restore

Clear selection and click A's row **Archive**. The modal must identify **one**
finding and UUID, with **Archive 1 finding**. Try clicking a background checkbox
or another action: the background must be inert. **Cancel** or Escape returns
without archiving. Cancellation/repeated submission is disabled while submitting.

Select A and B, click **Archive selected**, and check the frozen names/count and
**Archive 2 findings**. Cancel once to verify no change. If desired, reopen and
confirm; wait for queued jobs to finish. Only those synthetic targets should
disappear. Open **Archived**, locate them, use **Restore** and confirm, then check
that they return to Findings. Do not permanently purge records for this check.

Bulk workflow changes are atomic on a conflict. Bulk archive jobs are independent:
some may start while others are refused, and the result must explain that.

## 6. Verify browser-local dates

Choose a known date for A and reopen: the deadline should display at the end of
the entering browser's day (11:59 PM presentation). Internally the expiry is the
exclusive next-midnight instant, not literally a stored 11:59 PM timestamp.
From/To filters remain date-only: processing covers local midnight through the
whole final day. There should be one general browser-timezone notice, not cluttered
timezone labels on each field. Other list screens use the same filter convention.
Cross-timezone and DST cases have automated coverage; do not change your system
clock just to perform this walkthrough.

## 7. Verify shared screen improvements

- **Settings:** fills the available content width; mobile controls wrap without
  overflowing the page.
- **Documents → Preview:** expands inline beneath its row, toggles closed, allows
  one preview at a time, and scrolls long text. Closing returns focus to its trigger.
  Permissions and lifecycle actions remain role-dependent. Error/retry cases use
  controlled browser fixtures in automated acceptance, not intentional server damage.
- Successful archive/restore notices clear after **10 visible seconds**, pausing
  during hover/focus, hidden tabs or off-screen display. Dismiss remains available.
  Errors/warnings remain for manual attention. Copy-ID success uses three seconds.

## 8. Verify two-user conflict handling

Use **different Chrome profiles**, or normal plus Incognito with two different
organization-member accounts. Two ordinary tabs usually share the same login and
do not prove two-user behavior. Accounts must already be provisioned; use no
real organization data.

1. Both users select the same organization and open A's Workflow **before either saves**.
2. User 1 changes a field with rationale and saves.
3. User 2 submits the older draft. Expect a conflict/reload message, not a silent overwrite.
4. User 2's draft should remain available; explicitly reload latest state/history,
   review the changes and choose whether to submit again. No automatic write retry.
5. With an existing viewer account, inspect workflow/history: no write controls.

Do not remove/deactivate your own only admin to test access revocation. Precise
lock-wait races and bulk rollback are better proven by the PostgreSQL tests than
by trying to time clicks. Open browser lists are not real-time organization locks:
other users' changes may require reload. Previously committed jobs are not
retroactively cancelled by later role changes.

## Automated evidence and limits

- **25 October:** 1,203 full PostgreSQL tests, warnings as errors; migrations and
  lifecycle/permission races. This was not rerun for the dependency-only update.
- **26 October:** 367 frontend tests, lint, TypeScript/production build; 35 workflow
  Chrome checks and 6 grouped Documents checks (different scopes, not 41 equivalent
  checks). Full/production npm audits zero after targeted undici/zod updates.
- Native browser acceptance uses synthetic fixtures and intercepted provider
  responses only. No paid inference, live-AI approval or production/load certification.
- Docker and report-date UI remain Future; imported-finding reconciliation remains
  design-only. See [concurrency limits](MULTIUSER_CONCURRENCY.md) and
  [check-in scope](CHECKIN_PREPARATION.md).
