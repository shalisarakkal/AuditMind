# Exact counts and large-list navigation

## November 5 Findings search and workflow-refresh follow-up

Live API logs separated a 47 ms workflow PATCH from a 10.7 s subsequent list
reload; other observed finding-list reads took 9–20 s. Search/filter work after
save was the measured delay, rather than the workflow write itself.

For broad common searches under severity/created ordering, paging now uses an
ordered predicate scan once exact counts establish at least 10,000 matches.
Counts still use indexed UNION branches; selective searches retain that path.
The local `Deprecated` case (184,836 matches) improved from 3.31 s first /
2.55 s repeat / 3.17 s Next to 1.25 s / 27 ms / 60 ms in the final sample.

The Finding-column literal backtick case found one match in 10.85 s before
the change. Rare one/two-character column filters now reuse at most 1,000
candidate IDs and their domain/severity count metadata, under the existing
tenant/schema/epoch/revision/TTL cache key. If a 1,001st result is found, exact
normal counting/paging remains in use; results are never truncated. Workflow,
archive, membership and data changes invalidate this metadata. ASCII-only
punctuation/digit patterns use equivalent escaped LIKE rather than ILIKE;
alphabetic filters keep case-insensitive matching. Final local sample: 5.83 s
first and 11 ms repeat. Cold short filters and refresh after invalidation can
still take seconds because they cannot use trigram selectivity.

No new index, schema migration, search restriction or frontend change. The
58 focused PostgreSQL list/navigation/workflow-filter tests pass; the final
punctuation comparison also passed all five dedicated short-filter checks.
These tests cover exact counts, literal wildcard escaping, sample overflow,
cursor ordering and invalidation after workflow/archive changes.
Real Chrome also verifies the backtick column filter and displayed totals through
workflow save, archive and restore, including preservation of the saved rationale.
Measurements are read-only, single observations on the current local inventory,
not production latency guarantees. Reproduce with:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py --case findings_literal_short --case findings_common_search
```

## November 4 query-plan review

The wider review measures all eight Assets sorts and eleven Findings sorts in
both directions, including next-page requests. The initial matrix exposed
expensive reverse-severity, domain, finding text, category/source, joined asset,
workflow, assignee and deadline paths. These are addressed by ordered indexes
and bounded group plans. All 38 sort/direction variants and their following
pages retained exact totals and disjoint IDs in the final matrix. The final
ascending-IP covering-index correction was remeasured separately.

Migration 0039 adds ordered hostname/asset-label and finding-text/category/source
indexes, plus group-page indexes and sparse deadline-presence indexes. Its 19
indexes occupy about 7,097 MiB on the local 5.3-million-asset/7.3-million-finding
inventory, in addition to 0038's approximately 951 MiB. This storage and added
write maintenance are a deliberate cost of supporting these sort choices.
The local builds preserved source counts and protected account/Platform settings.
Application changes are recorded in `fe53274`, the separate retention correction
in `cf53f05`, and reproducible benchmark tools in `a660014`.

Representative final next-page timings on SA01's 2,798,320 active assets and
3,581,221 active findings:

| Sort | Before review | After review |
| --- | ---: | ---: |
| Findings reverse severity | 16,245 ms | 65 ms |
| Findings domain | 5,083–5,370 ms | 65–69 ms |
| Findings finding text | 9,446–10,104 ms | 86–87 ms |
| Findings asset | 21,858–31,364 ms | 37–105 ms |
| Findings assignee | 11,051–21,970 ms | 45–57 ms |
| Findings due date | 5,348–5,763 ms | 35 ms |
| Assets IP, final covering-index check | — | 48–53 ms |

All Findings next-page timings in the final matrix were about 20–105 ms.
Cold workflow/assignee group counts took about 1.5–1.7 seconds, then subsequent
pages reused them. Assets cloud-ID and metadata sorts still took about
1.3–2.6 seconds; arbitrary first deep offsets, short/broad cold searches, long
finding-text fallback and highly varied deadline fallback remain costlier.
These are measured limits, not a universal subsecond or SaaS throughput claim.

The final 100,000-row-clone benchmark measured median 5,000-row batches:

| Table / operation | Before navigation indexes | With navigation indexes |
| --- | ---: | ---: |
| Assets insert | 420 ms | 719 ms |
| Assets hostname update | 606 ms | 926 ms |
| Findings insert | 293 ms | 758 ms |
| Findings description update | 375 ms | 899 ms |

This is a substantial read/write tradeoff: about 1.5–2.6 times the tested write
cost, plus approximately 7.9 GiB of indexes across 0038/0039 on this inventory.
The benchmark excludes parsing, statement triggers and production concurrency;
it must not be extrapolated into a guaranteed full-import duration. Its clone
schema was removed and source records were not modified.

Final validation: all 519 frontend tests, lint, TypeScript and normal/isolated
production builds pass. The initial full backend run had 1,464 passes and three
failures: two DST-retention defects and an old strict JSON-shape assertion.
Those were fixed; 60 focused navigation/filter/migration/permission/retention
checks pass, the four fixed-date retention cases pass again, and the final
index/migration/all-sort checks pass. High-severity Bandit and dependency
consistency checks pass. Hosted Linux acceptance belongs to the pushed commit's
Actions run; no local run is presented as a hosted result.

Finding descriptions are indexed only when their lowercased description/category
key fits within 1,024 bytes. A matching longer value selects the full exact-sort
fallback; long ASCII and multibyte values remain accepted. The long-value probe
uses a cached exact count rather than `LIMIT 1`, which PostgreSQL can otherwise
misplan as a table scan when the partial index is empty.

Severity/domain paging fixes the leading enum ranks and seeks the date/ID
suffix. Workflow and assignee groups reuse exact revision-bound counts. Assignee
ordering uses PostgreSQL dense ranks so database collation and equal names retain
their original behavior. Deadline groups scan only dated rows and derive the
undated bucket from existing severity totals. At more than 1,024 groups, the
query retains the ordinary exact-sort fallback. Seek plans include only enough
following groups to fill the page, plus the current partially consumed group.

Asset sorting reads the populated-label segment through a driving asset index
and targeted finding lookups. It visits the NULL segment when the page reaches
it, retaining findings without a linked/displayable asset. Random deep offsets
remain supported through the existing fallback.
The asset-label index intentionally includes archived assets because legacy
active findings can still reference their labels. Sort-only joins are excluded
from count queries; required asset-filter joins remain. This avoids a planner
case where an eliminated LEFT JOIN still prevented index-only counting.

Reproduce the full review matrix with:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py --sort-matrix
```

The disposable-clone write benchmark is
`scripts/benchmark_list_index_writes.py`. It compares 5,000-row insert/update
batches with and without the added navigation indexes on 100,000-row clones.
It measures secondary-index cost, not parsing, statement-trigger overhead or
production concurrency. Only its randomly named prototype schema is modified.

The full regression run also exposed an archive-retention daylight-saving
boundary defect. Purge timestamps and supplied scheduler times are normalized
to UTC before adding/subtracting retention days, making the displayed deadline
agree with the scheduler's elapsed-day policy. Fixed-date tests cover both
seasonal transitions and 180/365-day retention.

The Assets and Findings lists retain exact totals and their existing filters,
sort choices, selection behavior and Previous/Next controls. This increment
reduces repeated counts, large offsets and sorting of complete asset payloads.

## Count freshness

Only count metadata is cached in each API process: at most 256 entries for
60 seconds. Keys include the database, schema, organization, filter values and
transactional revision. No records or authorization decisions are cached.
Every request still checks the live session and organization membership.

Migration 0038 installs statement triggers for asset/finding changes and for
organization/member/user changes affecting list results. A commit changes the
revision; the next read cannot reuse the prior count. Uncommitted writer
transactions bypass caching. Overdue filters also expire at the next relevant
deadline and reject reuse if the clock moves backward. Findings counts can be
shared between domain tabs and sort orders without changing their semantics.

Concurrent edits can change rows between count and page queries, as with the
existing READ COMMITTED behavior. A revision recheck prevents publishing
reusable count metadata or a navigation hint across such a change.

## Navigation and sorting

Responses optionally include signed next/previous cursors. The frontend uses
them alongside the existing offset, so old links and offset-only API clients
continue to work. Cursors bind the organization, filters, ordering, revision,
page size and requested offset. Invalid, altered or stale hints fall back to
the ordinary offset query. Oversized anchors are omitted.

Seek queries include every tie-break key, handle empty values in both
directions and fetch only the requested page's payload. Default sort indexes
include the IDs used for stable ordering. Disjoint indexed ranges avoid
filtering all preceding index entries for default-order seek navigation.
Other sort orders operate on IDs and sort keys before hydrating the page.
Assignee ordering joins the organization-member labels once rather than
evaluating a correlated label query for each candidate finding.

Changing filters or sorting clears the cursor and returns to page one. Paging
does not change the selection's filter identity. Other pages retain their
existing offset navigation.

Findings remounts its list when the selected organization changes, consistent
with Assets. This clears the previous organization's filters, sort, cursor,
selection and open actions before requesting the new organization's list.

## Local deployment and verification

Migration 0038 creates one revision row per organization and three active-row
indexes. On the isolated local demo (5,324,472 assets and 7,338,410 findings),
the initial migration took 76.46 seconds. Index sizes were 242 MB for Assets
created/ID, 330 MB for Findings created/ID and 379 MB for Findings severity/date/ID.
These indexes add disk and write work. Source row counts and account/Platform
setting digests were preserved; no seeding was performed.

Historical October 30 measurements, before the wider 0039 review, against the
same SA01 inventory (2,798,320 active assets and 3,581,221
active findings), in milliseconds:

| Request | Previous routes | New first request | Repeated offset | Next cursor page |
| --- | ---: | ---: | ---: | ---: |
| Assets, default order, offset 2,000,000 | 8,985 | 1,675 | 1,108 | 27 |
| Assets, hostname order, offset 2,000,000 | 14,284 | 12,697 | 6,046 | 1,304 |
| Findings, default order, offset 2,000,000 | 20,080 | 19,039 | 1,864 | 71 |
| Findings, text order, offset 2,000,000 | 14,548 | 14,662 | 14,675 | 5,834 |
| Assets, broad tag filter (337,021 matches) | about 5,300 | 1,809 | 56 | 86 |

Timings include exact counts when not reusable. OS/database cache warmth,
the 60-second count lifetime and prior cases affect each measurement. This
is a single-machine local comparison, not a SaaS load-test result. The
indexes target deep-page continuation, while first deep-offset requests can
still visit preceding keys.

Validation: 47 focused PostgreSQL paging, search, workflow-filter and migration
checks passed in 105.08 seconds; the added deadline-crossing regression then
passed separately. All 518 frontend tests, lint, TypeScript and isolated/normal
production builds passed. Signed-in Chrome verified Assets next/previous cursor
requests at the normal application address. These are historical local results;
the pushed commit's Actions run supplies current Linux acceptance. The baseline `4aa1467` passed all
four Linux jobs in [run 41069210537](https://github.com/shalisarakkal/AuditMind/actions/runs/41069210537).

November 4 review follow-up: fixed the Findings organization-switch state issue
identified in the local Copilot review. The new regression verifies that the
first request for the new organization starts at offset zero without the old
search, sort or cursor. Initial focused runs: 33 PostgreSQL navigation/paging/
migration tests and 36 frontend page/navigation tests pass; TypeScript and lint
pass. The isolated production build also passes. The earlier full-suite and
browser results above belong to October 30.

Use the read-only benchmark script with no import, index build or other heavy
work running:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py --case findings_deep --case findings_sort_deep
```

Each case reports its first request, a repeated offset request and the next
cursor page. Cache expiry and preceding cases affect first-request timings.
Use `--baseline --baseline-ref 4aa1467` for the previous committed routes.

In Chrome, open Assets or Findings, apply a filter, use Next and Previous,
and change sorting. Check that totals and ordering remain correct, paging
preserves selections, and changing a filter/sort returns to page one. In
DevTools Network, Assets/Findings responses may include `next_cursor` and
`previous_cursor`; the following request includes the corresponding `cursor`.
After editing/archiving a matching item, reload and check the updated exact
total. A copied old page URL remains usable through offset fallback.
