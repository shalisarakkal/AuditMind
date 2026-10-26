# Findings search performance — 25 October 2026

Migration **0024** adds `pg_trgm` and nine indexes: active-finding GIN indexes on
description/category/source; asset GIN indexes on hostname/IP/cloud ID; an active
assignee index; and two sparse active deadline-search indexes. Selective search
uses a deduplicated union of indexable branches. Display-label and one/two-character
queries retain an OR scan to avoid huge candidate-ID sets. Full UUID lookup remains
exact. Counts, filters, paging, tenant scope and active-finding visibility are unchanged.
Literal substring matching still escapes `%`, `_` and backslash; multi-column
matches count once. The UI and minimum query length did not change.

## Measured local synthetic SA01 results

Through `localhost:3000/api/v1`, including authorization and serialization; two
sequential requests per case. Dataset: **2,309,326 active findings**.

| Query | Before | Final | Matches |
| --- | --- | --- | --- |
| `ssss` | 16.241s / 12.472s | 2.299s first post-restart / 0.031s repeated | 2 |
| Absent synthetic term | 8.392s / 8.667s | 0.019s / 0.017s | 0 |
| IP `64.217.7.147` | 11.749s / 11.000s | 0.046s / 0.059s | 1 |
| `manual` | Not baselined | 2.058s / 0.022s | 2 |
| `Open` | Not baselined | 1.327s / 1.230s | 2,309,326 |
| Two-character `ss` | Not baselined | 7.496s / 7.601s | 737,760 |

A live installed-Chrome check typed `ssss` and displayed **2 findings match in
1,127ms**, including debounce/render, while regressions ran. Result counts were
unchanged for the before/after cases. First-request/cache effects are included,
not omitted. These small local samples are not production/load/SLA certification.
Short/broad queries remain costly; prefer specific terms or column filters.
Temporary diagnostic sessions were removed; no passwords were reset.

An `EXPLAIN (ANALYZE, BUFFERS)` of the actual `ssss` domain/severity count query
confirmed all six trigram indexes and the sparse deadline/assignee support indexes
in the plan, followed by primary-key lookup of two deduplicated findings. Measured
count-query execution was **0.797ms** in that warm sample; this is SQL count timing,
not HTTP/browser latency and not a replacement for the measurements above.

## Migration operations

- Requires PostgreSQL's trusted `pg_trgm` available in `public` and extension
  installation permission (or prior administrator installation).
- Indexes build **CONCURRENTLY**, outside transaction blocks. Do not wrap the
  migration in an external transaction. Allow build I/O and disk: approximately
  **471 MB** for these nine indexes in this demo. Index maintenance adds write cost;
  sustained import throughput has not been separately certified.
- Valid completed indexes survive interruption and reruns skip them. Invalid
  indexes are explicitly refused. After inspecting schema/name and `indisvalid`,
  an operator may drop only that invalid index with schema-qualified
  `DROP INDEX CONCURRENTLY`, then retry. Never broadly delete indexes/schemas.
- Long transactions can delay the old-snapshot phase. Inspect
  `pg_stat_progress_create_index` and transaction ages; do not terminate unrelated
  sessions. This demo's owned services were briefly stopped to release an old
  worker snapshot, then restarted with existing data/passwords retained.
- Worker queue metrics now open/close their own managed session instead of
  reopening a previously closed Session and leaking an idle read transaction.
  A post-restart database check found zero idle transactions older than 30 seconds
  and zero invalid demo indexes.
  A regression checks that the metric transaction is released.
- Downgrade removes these indexes concurrently but retains shared `pg_trgm`.

Only the local synthetic **auditmind_demo** schema was migrated here. Installing
the database-level extension is shared; the normal application schema was not
migrated. The disposable test database is migrated and validated separately.

## Reproduce correctness checks

Final validation: **1,203 full PostgreSQL tests passed in 607.28s**, warnings as
errors; **367 frontend tests**, lint and normal production build passed; **35
installed Chrome checks** passed (`phase3_browser_cd6dcb1ec3c4`), plus the live-SA01
search smoke above. Focused runs overlap and are not added to this full-run count.
Test DB restored to **0024**, 30 tables, no browser schemas and clean Alembic check.
No paid inference calls. Validation preceded the later scoped commits; see
[check-in record](CHECKIN_PREPARATION.md). No push is implied.

From backend:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_paging_api.py tests/integration/test_finding_workflow_filters.py tests/integration/test_migrations.py tests/integration/test_worker_review_fixes.py --require-postgres -W error -q
.\.venv\Scripts\python.exe -m pytest --require-postgres -W error -q
```

Migration tests cover upgrade/downgrade/re-upgrade, legacy data, index validity and
metadata drift. Search regressions cover deduplication, escaped literals, date
fragments, labels, UUID lookup, tenant boundaries, combined filters and counts.
Correctness tests do not use fragile elapsed-time assertions.
