# UI conventions: list pages

Every page that lists things (Assets, Findings, Imports, Archived, Activity,
and any new one) looks and behaves the same. Build new list pages from the
shared pieces in `frontend/src/components/ListPage.tsx` and
`frontend/src/components/ListControls.tsx` rather than styling them afresh.
Agreed 2026-09-30.

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

## Checklist for a new list page

- [ ] `PageHeader` with the count, `ListToolbar` with the search box and,
      if the list has a date column, `DateRangeFilter`
- [ ] every column sortable (or a reason it isn't), a filter for each
- [ ] badges for statuses, `ACTIONS_CELL` for actions, `EmptyRow`
- [ ] row actions: checkboxes and a SelectionBar for doing them to several
- [ ] backend: `q`, per-column filters, `since`/`until` on the date
      column, `sort`/`order`, paging, facets
- [ ] tests: filters reach the API, sorting, the empty and filtered messages
