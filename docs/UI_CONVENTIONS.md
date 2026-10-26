# UI conventions: list pages

Dashboard security cards link to the same exact seven-day organization event
window used for counting; Activity labels that window and replaces it when date
filters change. Import cards keep source/cancel/error/report independent per file.
Use shared ProductBrand/header components rather than screen-specific marks.

Review synchronization (2026-10-22): These conventions remain normative. Passing component tests does not replace full Chrome accessibility/lifecycle acceptance; release findings and remaining gates are tracked separately.
See [current code review and release gates](RELEASE_READINESS.md).

Every page that lists things (Assets, Findings, Imports, Archived, Activity,
Reports, Documents, and any new one) looks and behaves the same. Build new list pages from the
shared pieces in `frontend/src/components/ListPage.tsx` and
`frontend/src/components/ListControls.tsx` rather than styling them afresh.
Agreed 2026-09-30.

Native date inputs use the shared `input[type="date"] { color-scheme: dark; }`
rule in `globals.css`, including workflow deadlines and list filters. Keep the
calendar indicator legible against navy; retain the native picker and keyboard
entry rather than applying per-screen icon inversion or custom replacements.

Archived, Assets and Uploads follow the Findings selection contract: selected
rows enable bulk actions and disable individual mutation/retry actions (read-only
reports/details remain available). Clear selection restores row actions. Native
application-styled confirmation modals block background interaction, focus Cancel,
preserve original bulk IDs, and block cancellation while submitting. Organization
changes remount the list; filter changes and completed jobs clear selection.
Archived shows Restore for writers and Purge only for admins. A purging target
blocks bulk Restore; a restoring target blocks bulk Purge, including across pages.
Never silently omit incompatible targets; backend validation remains authoritative.

## Layout, top to bottom

1. **Header** (`PageHeader`): the title; under it the count, "2,184,928
   findings in Acme" (filtered: "12 findings match"; one: "1 upload"); the
   page's main action on the right (e.g. Import data). An explanation, if
   needed, is one short grey line (`note`), never a paragraph.
2. **Trackers and messages**: the import tracker (`ImportStatus`), job
   progress and results (`JobStatus`), confirmation panels (`JobConfirm`,
   `ConfirmPanel`; never browser dialogs).
3. **Chips**, if the page pre-filters one column (`FilterChips`: Findings'
   domains, Archived's types): "All (n)" first and chosen by default, then
   each value that occurs with its count under the other filters (the list
   endpoint returns them, e.g. `domain_counts`, `type_counts`); a chip
   sets that column's pick-list filter, so the two always agree. Rounded
   pills, the chosen one cyan. No tabs: one list, one table.
4. **Toolbar** (`ListToolbar`): "Search all columns" first; then the
   From/To range on the list's date column (`DateRangeFilter`, e.g.
   "Uploaded 09/01/2026 to 09/30/2026"; every list with a date column has
   one); then "Clear filters" when any filter is set.
5. **Table** (`ListTable`, `THEAD`, `ROW`, `TD`), then the **pager**
   (`Pager`), 100 rows a page.

## Table

Findings action layout (25 October 2026): one selection, no **Select for** mode.
Keep Workflow and eligible manual Archive together in a labelled sticky-right
Actions column, with an opaque application background and narrow-screen wrapping.
Viewers retain row Workflow for read-only inspection, without archive/selection.
The selected-findings bar exposes both bulk actions: workflow up to 100; archive
up to 500 only when every target is manual/available. Explain disabled actions,
and disable individual row Workflow/Archive/Undo whenever any selection exists;
show Clear selection guidance. Selection is local, not a cross-user reservation.
never silently skip imported rows. Preserve eligibility metadata across pages;
it is UI guidance, not authorization. Confirm exact targets/counts, preserve the
confirmation target snapshot and retain server validation/refusal reporting.
Use an application-styled native modal for Findings archive confirmation (not
window.confirm): inert background, initial Cancel focus, restored trigger focus,
explicit row/bulk target counts, and no cancellation/repeated submission while busy.

- **Every column that has values is sortable** (`SortHeader`): click for
  ascending, again for descending, again for the default order. A list that
  defaults to newest first passes `defaultSort` and `defaultOrder="desc"`.
  Only columns of words describing several things (Result, "Archived with
  it") and the actions column aren't.
- **A filter row under the headers**, one filter per column:
  - text columns (names, files, hostnames, who): a "contains…" box
    (`TextFilter`);
  - columns with a fixed set of values (type, status, severity, criticality,
    event): a pick-list (`PickFilter`) with the values that occur (a
    `/facets` endpoint);
  - the date column: the From/To range in the toolbar (API `since` and
    `until`, `date_range` in paging.py), so its cell under the header
    stays empty.
- **Who and when are separate columns**, dates as `formatDateTime`.
- **Statuses are badges** (`StatusBadge`): completed green, failed or stopped
  red, running cyan, pending grey. Criticality (`CriticalityBadge`): critical
  red, warning yellow, info grey. Severity keeps its own four colours.
- **Interrupted is violet, with ⚠**: an upload or job waiting for, or cut off
  by, the background worker while it's down (and the sidebar's "worker isn't
  running" alert). Not red (failed: nothing is lost, it goes on when the
  worker is back) and not amber (an import report's warnings).
- **Row actions** go in the last column, right-aligned (`ACTIONS_CELL`), as
  text buttons in three tiers: white, always underlined, for what only
  shows something (`ROW_ACTION_VIEW`: Report, Details), cyan for what
  changes data (`ROW_ACTION`: Archive, Restore, Retry, Undo), red for what
  can't be undone (`ROW_ACTION_DANGER`, e.g. Purge). From the moment it's confirmed, a
  job's button says so ("Archiving…") and is disabled, whether it runs in
  the request or in the background; a small one done in the request then
  says "Archived" until the row leaves the list; a job that stopped
  part-way offers "Retry …" (`JobButton`).
  One exception: a toggle that only opens more about a row, which every
  member may see, can sit under the row's text instead (Findings: an event
  log finding's Details), since the actions column is shown only to those
  who can change things.
- **Several at once**: where rows take an action (archive, restore,
  purge), writers get a checkbox column first (`SelectBox`, and
  `SelectPageBox` in the header for the page's rows; `useSelection`).
  The selection stays while paging, starts over when a filter changes, and
  holds at most 500. While anything is picked, a bar under the toolbar
  says "12 selected" with the actions and Clear selection
  (`SelectionBar`, `SelectionAction`); they confirm first
  (`BulkConfirm`), then queue one job per row, each row showing its own
  state ("Queued…", "Archiving…"). Rows that can't take the action now are
  disabled; ones the server refuses are listed with why.
- **Empty table** (`EmptyRow`): "No findings yet." or, filtered, "No findings
  match."
- **Loading and errors**: `StatusMessage` ("Loading…", or the error in red).

## Words

Agreed 2026-09-30:
- **Upload**: a file a person sends in ("Upload file", the Uploads page,
  "Already uploaded", "Upload anyway"). Everything today is an upload.
- **Processing**: AuditMind reading an uploaded file ("Processing
  big.csv…", "processed", "processing failed").
- **Import**: data AuditMind collects itself from a connected source (e.g.
  Active Directory, a cloud account): connectors, later. Their runs join
  the same page, then "Uploads & imports", with a Source column.
- **File formats** (Settings): how each tool's export file is read.
- Code, API paths and database names keep "import" and "scan"; only what
  people read follows these words.

## Behind the page

- The sort, filters and page offset live in the page address
  (`useListState`), so a refresh, the Back button or a shared link keeps
  them; the address names its organization.
- The list endpoint takes `q` (search every shown column, including values
  as the page shows them, e.g. "Network device"), one parameter per column
  filter (`contains` for text, `one_of` for pick-lists, both in
  `backend/app/api/paging.py`), `sort` and `order`, and `limit`/`offset`,
  and returns `{items, total}`.
- A pick-list's values come from a `GET .../facets` endpoint.
- Reports may show a separate "Rule-based test report" action only when the
  API's test-only capability is enabled. These reports must be labeled as
  non-AI and explicitly state that framework controls were not evaluated.
- Completed reports offer separate HTML and direct PDF downloads; "Print"
  opens the browser print dialog and is not a substitute for PDF export.
  Selected completed reports download as one ZIP of PDFs. Bulk deletion is
  admin-only and remains separate from downloading.
- Retired document versions can be reactivated by writers. Reactivation
  reindexes the retained content and only makes it current after indexing
  succeeds; while it is queued or running, show "Reactivating…" and prevent
  removal. A failed reactivation leaves the version retired and retryable.

## Checklist for a new list page

- [ ] `PageHeader` with the count, `ListToolbar` with the search box and,
      if the list has a date column, `DateRangeFilter`
- [ ] every column sortable (or a reason it isn't), a filter for each
- [ ] badges for statuses, `ACTIONS_CELL` for actions, `EmptyRow`
- [ ] row actions: checkboxes and a SelectionBar for doing them to several
- [ ] backend: `q`, per-column filters, `since`/`until` on the date
      column, `sort`/`order`, paging, facets
- [ ] tests: filters reach the API, sorting, the empty and filtered messages

## Document libraries

- Organization Documents and Platform Shared standards use the same library
  controls. Show the real organization name and put Upload document in the header.
  Upload metadata uses a labelled inline form with primary/secondary actions.
- Hide mutation selections, bulk controls and forms in read-only mode. Organization
  admins manage only their own documents, not shared sources. Shared standards and
  provider configuration are restricted to the Sysadmin. Backend authorization
  remains authoritative; hiding controls is not a security boundary.
- Use shared status badges with readable labels. Initial publication is Queued /
  Processing, not Reactivating. Reactivating applies only to retained retired
  versions awaiting republication; do not offer removal during that operation.
- Keep version metadata compact behind Version details: source, rights and content
  hash remain available without filling every row. Read-only preview stays available.
- Separate AI-report and embedding consent into named sections with explicit
  status, target details and descriptions. Approve/revoke actions require an inline
  confirmation; local embedding targets do not offer unnecessary external approval.
- Keep permitted-evidence search distinct from document-list filtering. Announce
  search progress, counts, empty results and errors; do not show stale excerpts as
  the result of a failed new search.

## Report-generation forms

- AI and rule-based preview modes use the same application-owned dialog. This is
  not a browser `alert`/`confirm` prompt. Use named navy/cyan tokens, consistent
  borders, input styling and primary/secondary actions; avoid custom hex colours.
- Show the selected organization explicitly. Fetch AI report approval on each
  opening and organization change; missing, loading or failed approval checks
  disable AI submission. Offer an organization-scoped Documents link, and Retry
  for failed checks. Do not grant consent or imply that approval configures a
  provider, evidence index or worker.
- Use a named dialog, a labelled close action, initial focus, contained Tab/
  Shift+Tab navigation, Escape dismissal and focus restoration. Do not dismiss
  while submission is in flight. Ensure scrolling and actions remain usable on
  short/narrow viewports.
- Frameworks use fieldset/legend and labelled checkboxes. Use plain language;
  framework selection does not install licensed material or certify compliance.
- Announce submission/check errors through alerts. Keep rule-based previews
  explicitly non-AI and independent of external-processing consent.

## Job-result notifications and Settings width (24 October 2026)

Document previews (25 October 2026) follow the Uploads report pattern: expand
directly below the owning row, span the correct visible columns, show title/version
and edition, and toggle Preview/Hide preview. One preview at a time. Keep loading,
errors/retry and Close inside the panel; Close restores focus to its row toggle.
Scope changes close previews, late responses cannot replace another version's text,
and long text wraps/scrolls inside the panel without widening the page. Preview
uses existing read permissions and is not an indexing or mutation action.

- Successful archive/restore/purge notices auto-dismiss after 10 seconds of visible
  time on the current screen. Pause for hover, keyboard focus, a hidden browser tab,
  or scrolling the notice out of view. A newly mounted notice starts its countdown;
  once dismissed, the existing server dismissal keeps it gone across screens/refresh.
- Running/queued/interrupted jobs, failures and outcomes requiring review remain
  visible. Restore outcomes that kept findings archived or purged duplicates require
  manual dismissal. A grouped result containing any such outcome stays visible.
- Keep Dismiss/Dismiss all available. Automatic dismissal is background activity
  and must not renew idle activity. If it fails, show the error and require manual
  retry; do not loop. Do not delete jobs, Activity events, uploads or archived data.
- Full upload reports and their warnings/errors keep their existing manual review
  and dismissal behavior. Do not apply a blanket timer to all messages.
- Organization Settings uses the same available content width and shared page
  header as other screens. Keep forms usable on narrow viewports and horizontally
  scroll wide tables inside their own containers, not the page body.

## Accessibility

All interactive components must meet **WCAG 2.0/2.1 AA** at minimum.

### Rules

- Every `role="group"` element (e.g. `FilterChips`) must carry an `aria-label`
  describing what the group controls.
- Icon-only buttons must have a visible `aria-label` or a `<span className="sr-only">` label.
- Form inputs must have a `<label>` or `aria-label`; placeholder text is not a
  substitute.
- Focus order must follow the visual reading order; do not use `tabIndex > 0`.
- Use semantic HTML (`<button>` for actions, `<a>` for navigation, `<nav>`,
  `<main>`, `<header>`) rather than styled `<div>` elements.

### Audit script

`npm run a11y` launches the app's dev server pages through Playwright + Axe
and exits non-zero if any WCAG 2.0/2.1 AA violation is found.
Script: [`frontend/scripts/a11y.js`](../frontend/scripts/a11y.js).
Pages audited: `/login`, `/reports`, `/`.

**Last audit:** 2026-10-12 — **0 violations** on all three pages (`/login`, `/reports`, `/`).

