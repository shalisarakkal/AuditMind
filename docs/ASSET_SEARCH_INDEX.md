# Assets search acceleration — 30 October 2026

## Behavior and safety

Migration 0037 installs the versioned `am_asset_search_v1` expression and a partial
GIN trigram index for active Assets. It combines hostname, IP, cloud ID, type and
display spelling, subtype, environment, criticality and the existing joined tag
text. There is no new stored column, row backfill, UI field or scoring change.
PostgreSQL maintains the index on imports, updates, direct SQL writes, archive,
restore and delete. Original per-field matching remains authoritative: the index
only supplies candidates, including when tag search is combined with other filters.
Matches across concatenated field boundaries cannot produce new results.

The function accepts only text and varchar[] inputs. Its text concatenation is
immutable; the generic PostgreSQL array-to-text operation is not declared immutable
for arbitrary element types, so the wrapper must never be broadened to dates or
other types. Treat v1 as a frozen contract. Changing its body requires a new
function/index version and an index rebuild, not replacement under an existing index.
The function uses pg_catalog internally and does not read tables or elevate rights.

Short/non-word queries retain the original query. For candidate searches, bound
EXPLAIN JSON queries estimate the organization and original predicate without
executing a scan. Matching common-tag element frequencies supplement the planner,
because `array_to_string` otherwise underestimates common tags. Element frequencies
are scaled by the non-null-array fraction, keeping rare tags selective when most
assets have no tags. The combined index
is selected only below an estimated 5% fraction. These are query-strategy estimates,
not approximate displayed totals. Original predicates always decide matches.
Statistics can be stale or imperfect; broad searches may still scan. Maintain
normal ANALYZE/autovacuum practice after major changes. No per-user sample or
foreign-tenant row contents are returned by this strategy check.

Two failed performance approaches were rejected: unconditional combined-index use
made common terms much slower, and an expression-only estimate did not recognize
common type/tag searches. Tests now cover both indexed and scan strategies.

## Prototype and write costs

The reproducible prototype copies 100,000 local-demo rows into a random isolated
schema, creates the existing indexes, compares pre-increment routes with new
routes on identical rows, and drops only its own schema. All compared totals and
page IDs matched. The final quiet prototype run measured:

| Search | Previous query | Combined candidate |
| --- | ---: | ---: |
| No match | 249 ms | 27 ms |
| Hostname fragment | 170 ms | 14 ms |
| Existing tag | 238 ms | 22 ms |
| Tag-column filter | 73 ms | 19 ms |
| Metadata fragment | 252 ms | 21 ms |
| Type display label | 197 ms | 22 ms |

These are variable local observations, not capacity guarantees. Short and literal
wildcard searches retain scan behavior. Prototype samples are random, so rows and
timings vary between runs; each before/after pair uses the same copy.

Prototype evidence is retained in ignored `temp/testing/asset-search-prototype.json`.
The prototype index was about 13 MiB. Median direct 5,000-row SQL write probes rose
from 277 to 489 ms for inserts and 339 to 561 ms for tag/environment updates.
An actual isolated 5,000-row API import pair measured creation at 1,020 → 1,239 ms
and updates at 4,212 → 4,782 ms. The earlier pair was 989 → 1,151 ms and
4,375 → 4,008 ms, illustrating variation. The final regression pair was
1,190 → 1,228 ms for creation and 4,347 → 3,773 ms for updates. These do not establish 500k-row import
throughput. The query gains come with additional write, disk and vacuum costs.

## Full inventory trial

After idle-queue checks, the isolated demo upgraded 0036 → 0037 using a concurrent
index build. Exact table counts and account/Platform-setting digests matched
before/after: 5 organizations, 6 users, 5,324,472 assets, 7,338,410 findings,
48 scans and 9 reports. Metadata drift check passed. The full index occupies
301,383,680 bytes (about 287 MiB). No row values or credentials were changed.

SA01 query samples, excluding authentication/network/rendering:

| Operation | Baseline | New strategy | Exact matches |
| --- | ---: | ---: | ---: |
| No match | 6,527 ms | 50 ms | 0 |
| General hostname fragment | 5,228 ms | 148 ms | 1,000 |
| Most-common tag across all fields | 5,775 ms | 5,309 ms | 337,021 |
| Most-common tag-column filter | 3,374 ms | 3,208 ms | 337,021 |
| Network device display label | 5,628 ms | 4,372 ms | 143,737 |

Broad common-tag results use the ordinary scan; their small timing difference
is not an index speedup claim. Common type searches still take roughly 5–7 seconds
and short searches about 5 seconds. Exact counting, arbitrary sorting and deep
offset paging remain expensive for large result sets. Further improvement would
need a separate design for paging/count delivery or additional measured indexing;
no general subsecond-search claim is made.

## Validation and operations

Focused PostgreSQL coverage includes paging/filters, imports/re-imports, asset
matching, migration upgrade/downgrade, literal `%`, `_`, backslash and quotes,
Unicode, null/empty values, type labels, cross-field false positives, archive/
restore/delete, direct SQL index maintenance, tenant isolation and both strategies.
Final pre-commit combined regression: **70 passed in 88.03 seconds**. Earlier,
69 focused checks passed in 90.06 seconds; the final five strategy/index
checks passed after the null-array frequency correction. The final multi-label
binding assertion also passed separately. Counts overlap, not a new full-backend
run. XML evidence is retained in ignored
`temp/testing/asset-search-regression.xml`. High-severity static checks pass.
Signed-in installed Chrome verified SA01 with no JavaScript errors: no-match
search took 487 ms including debounce; `NET-499` general search returned 1,000
matches in 222 ms. Network device/server searches preserved 143,737/981,727
matches, taking 5,363/5,906 ms through HTTP. Readiness passed. Only the API was
restarted; frontend and worker were retained. After the final null-frequency
correction, Chrome again passed: hostname search 171 ms/1,000 matches and common
server search 5,915 ms/981,727 matches; no page errors. The actual most-common tag
was separately confirmed to take the scan path, and prototype cleanup was verified.
This increment does not claim a fresh full
backend suite, hosted CI result, SaaS capacity or production activation.

Apply 0037 before running the new API query. For rollback, restore the previous
API query implementation before dropping its function/index with migration
downgrade. Old query code remains compatible with the new index. Interrupted
invalid indexes are rejected explicitly; drop only that invalid index concurrently
before retrying. Never overwrite v1 under an existing valid index.

From `backend`, with the existing isolated local demo and Git history available:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_asset_search.py
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py --baseline --case assets_no_match --case assets_tag_search --case assets_tag_filter
.\.venv\Scripts\python.exe scripts/benchmark_large_lists.py --case assets_no_match --case assets_tag_search --case assets_tag_filter
```

The full-inventory helper uses read-only transactions and 45-second query limits.
Tag cases deterministically choose the most frequent eligible tag. Prototype
write tests operate only inside their random local schema, with cleanup guarded
to that generated name. Run measurements without competing imports/index builds.

For a manual Chrome check, open Assets in the same large organization. Search a
unique hostname or `no-such-host-93c7`, then clear it and compare a known tag with
its column filter. Confirm literal `%`/`_` matching, combined filters and paging.
Common terms such as server intentionally retain scan behavior; compare exact
totals rather than expecting every query to finish in under a second.
