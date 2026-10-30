# Large-list query performance — 30 October 2026

This is the 0036 measurement record. The subsequent
[guarded Assets-search increment](ASSET_SEARCH_INDEX.md) addresses selective
tag/metadata searches with 0037. Its common-query fallback and write/storage costs
are documented separately; earlier broad-search timings below are the baseline.

## Delivered increment

Migration 0036 adds eight partial B-tree indexes on active rows: organization
plus type/subtype/environment/criticality for Assets, and organization plus
source/workflow status/assignee/scan for Findings. Facet queries use ordered
distinct-value probes, skipping repeated index entries rather than scanning all
active rows. NULL is queried separately; blank values remain one empty-string
option. The existing 500-value text facet cap is retained; assignee options are
not silently capped. The scan index also accelerates checking for manual findings.

Long non-label Findings searches count distinct candidate IDs with domain/severity
projected inside each search branch. They no longer fetch each candidate's base
row again just to group counts. Existing date-text branches are retained.
Literal wildcard escaping, date fragments,
tenant/archive restrictions, all other filters, exact totals/domain counts and
pagination are retained. Raw finding import JSON is deferred on list reads; it
was not part of the list response and remains available for other operations.

An experimental UNION ALL rewrite was slower and was reverted. The final search
retains UNION de-duplication. No approximate counts, result cache, stale facets,
minimum search length or changed search semantics were introduced.

## Measurements

Read-only local `auditmind_demo`, SA01 organization. These are observations on
one development machine, not latency guarantees or SaaS capacity measurements.
Source tables across the schema contain 5,324,472 assets and 7,338,410 findings.
Measurements vary with PostgreSQL cache, table visibility, disk and other work.

| Operation | Before | Final local query | Signed-in Chrome request |
| --- | ---: | ---: | ---: |
| Assets filter options | 5,309 ms | 29 ms | 137 ms |
| Findings filter options | 4,495 ms | 33 ms | 101 ms |
| Findings common search `Deprecated` | 7,933 ms | 4,931 ms | 4,468 ms |

The facet baseline was captured before migration. A second baseline using old
routes on the newly indexed database measured 3,395/915 ms respectively. The
common-search comparison used old/new routes on the same indexed database and
returned **309,997 exact matches** throughout. Additional final query samples
were 37/92 ms for facets and 4,286 ms for common search. The ordinary timings
exclude authentication, HTTP/serialization and browser rendering; Chrome request
measurements include the HTTP path but do not measure full page rendering.

Broad Assets no-match search remained about **5.5–7.7 seconds**. It still inspects
tags/metadata and is an explicit follow-up, not a closed performance item. A
selective hostname filter remained about 70 ms. Broad Findings text-only filter
was about 1.9 seconds. Deep-offset paging and arbitrary sorts also remain bounded
by their existing query costs. No general subsecond search claim is made.

## Storage and activation

The eight new indexes occupy **291,241,984 bytes (about 278 MiB)** across the
whole demo schema. They add write and disk maintenance costs; large-import
throughput with these additional indexes has not been benchmarked.

The local demo was upgraded from 0035 to 0036 after confirming import/archive/
report/document/evaluation/Dashboard queues and organization purges were idle.
Concurrent index builds preserve ordinary writes. Interrupted invalid indexes
are rejected explicitly and must be dropped concurrently before retrying.
Before/after exact counts and account/Platform-setting digests matched. Alembic
metadata drift check passed. Only the API was restarted; worker and frontend
were retained. Readiness and signed-in Chrome checks pass. No credentials,
scoring enablement, concurrency setting or organization evidence was changed.

## Verification and reproduction

- 60 PostgreSQL paging, workflow/filter and migration tests passed in 64.09 s.
  A subsequent focused search-filter regression test passed after final assertions.
  After retaining the original date-text branches, all 20 paging tests passed
  again in 21.64 s; common search measured 4,508 ms with the same exact total.
  High-severity Bandit and whitespace checks passed.
- Coverage includes duplicate candidate paths, domain counts under excluded-domain
  filters, other combined filters, date fragments, NULL/empty/duplicate options,
  tenant/archive isolation, facet limit, migration downgrade/re-upgrade and drift.
- Installed Chrome verified authenticated Assets/Findings facets, the common
  search total and the Findings page without JavaScript errors.
- No fresh full-backend, full-browser-suite or hosted CI result is claimed for
  this increment. Frontend source was unchanged.

From `backend`, the helper refuses remote/test database targets, explicitly uses
the isolated demo schema, and runs each query in a read-only transaction with a
45-second statement timeout. It never prints credentials or row contents:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py --baseline --case assets_facets --case findings_facets --case findings_common_search
```

`--baseline` loads route definitions from committed `1b2286f`, using the same
database/indexes as the new code. Do not run timing comparisons during imports,
index construction or other heavy database work.
