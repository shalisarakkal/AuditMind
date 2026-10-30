# Single-organization Dashboard count optimization

Historical 29 October measurement record. Its count-index changes are now
committed/pushed and covered by hosted Linux run 40984969686; normal frontend
startup and signed-in Chrome checks are complete. The launch/check-in blockers
below describe that earlier checkpoint. See the separate
[30 October large-list query increment](LARGE_LIST_PERFORMANCE.md) for current work.

29 October 2026: implemented and applied locally at migration **0033**. This is
a focused exact-count improvement, separate from the SaaS scaling proposal.
Application changes remain uncommitted at this checkpoint; no new hosted CI or
Chrome runtime verification is claimed.

## Change

Two compact partial B-tree indexes cover active-row counting:

- Findings: `(org_id, domain, severity) WHERE archived_at IS NULL`.
- Assets: `(org_id) WHERE archived_at IS NULL`.

Queries, scoring deductions, evidence-mode rules, exact totals, tenant filters and
repeatable-read Dashboard snapshots are unchanged. These are additional indexes;
no previous index is removed and no data is rewritten. All columns are index keys
so repeated groups can use B-tree deduplication rather than disabling it with
INCLUDE payloads. See PostgreSQL's [index-only scan documentation](https://www.postgresql.org/docs/18/indexes-index-only-scans.html)
and [CREATE INDEX reference](https://www.postgresql.org/docs/18/sql-createindex.html).

Migration 0033 builds/drops concurrently in Alembic autocommit blocks. It refuses
to silently skip an invalid interrupted index, with an explicit recovery message.
Existing valid indexes support retry; full schema drift verification still
checks their definitions. Concurrent construction keeps ordinary writes possible
but consumes I/O/CPU and can wait for old transactions; it is not zero-impact DDL.

## Local measurements

Read-only `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` against the existing SA01
organization, without changing planner settings, clearing caches or running
manual VACUUM. A 45-second per-statement limit bounded measurements. Initial
observations were 9,542.615 ms / 5,134.192 ms for findings/assets; a repeat baseline
was substantially faster, so those initial values are not used as a stable
before/after guarantee.

| Query | Repeat baseline | First indexed sample | Plan change |
| --- | ---: | ---: | --- |
| Exact findings by domain/severity | 1,910.974 ms | 476.316 ms | Parallel sequential scan to index-only scan |
| Exact active assets | 997.461 ms | 555.104 ms | Existing IP index to compact organization-count index |
| Top five critical findings | 0.197 ms | 1.718 ms | Existing index retained; already inexpensive |

The findings query's shared-read blocks fell from **481,432 to 465**. The asset
query's shared-read blocks fell from **115,435 to 64,036**, with remaining heap
visibility checks. Cache conditions, recent writes, autovacuum and machine load
affect timings. This is a small number of local observations, not an endpoint
SLA, controlled cold-cache experiment or concurrent load test.

The complete `build_dashboard` path subsequently took **1,657.14 ms**, including
normal ORM mapping and score assembly, for **2,798,320 active assets** and
**3,581,221 active findings** in SA01. It was called in a read-only repeatable-read
transaction, not through browser/auth/network. There is no matching whole-builder
pre-change baseline, so do not calculate an endpoint speedup from this result.
One preliminary standalone builder attempt omitted normal model registration;
the corrected harness imported `app.db.base` and completed successfully. This was
a measurement-harness setup error, not a failing application API test.

New indexes use **30,416,896 bytes** (assets) and **43,220,992 bytes** (findings)
across the full demo schema. Every relevant insert/archive/change maintains them;
large-import write overhead has not been benchmarked. Counts still scale with
active index entries, and index-only efficiency depends on visibility metadata.
Broad Findings searches, facets and approximate/cached totals are not delivered
by this change and remain separate work.

Local artifacts (ignored runtime files):

- `temp/testing/dashboard-counts-baseline.json`
- `temp/testing/dashboard-counts-indexed.json`
- `temp/testing/dashboard-build-indexed.json`

## Validation and activation

**48 focused tests passed in 54.53 seconds**, warnings as errors, real PostgreSQL:

```text
python -m pytest -W error --require-postgres tests/integration/test_migrations.py tests/integration/test_dashboard_api.py tests/integration/test_background_evidence.py tests/unit/test_scoring_service.py -q
```

Migration tests inspect both index keys/predicates, downgrade to 0032 and verify
removal, upgrade again, and exercise existing legacy-data preservation and
metadata drift checks. API tests cover exact scores/counts, archived/foreign-tenant
exclusion and evidence-mode behavior. No full-suite rerun or new hosted CI result
is implied by the focused count.

Applied only to the existing local `auditmind_demo` schema after all queues,
staging and organization purges were idle. Alembic upgrade 0032 → 0033 and metadata
check pass. Before/after global counts match: 5 organizations, 6 users, 5,324,472
assets, 7,338,410 findings, 48 scans, 9 reports and 5 document versions. Account
and settings digests match; no seed/reset, scoring enablement or concurrency
change. `/ready` passes; API and one-slot worker were not restarted.

The normal frontend remains stopped: automatic approval review again rejected
`npm start` as "blocked by policy", without a more specific reason. Its last
production build is retained. Manual start from the frontend directory:

```powershell
npm.cmd run start -- --hostname 127.0.0.1 --port 3000
```

After startup, refresh the Dashboard in Chrome. Compare exact displayed counts
with the organization's active lists. Chrome Network timing includes API and
network overhead beyond the SQL samples; loading indicators remain useful.
