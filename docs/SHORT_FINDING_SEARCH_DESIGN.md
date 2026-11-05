# Short Finding-column search: design and benchmark

5 November 2026. Step 1 is a prototype/design exercise. The running application,
its indexes, settings and API contracts are unchanged. Experimental functions
and indexes exist only in disposable clone schemas and are removed afterward.

## Recommendation

**User disposition, 5 November:** retain current search behavior and defer index
implementation. The write overhead is material. The research below remains a
reference for later reprioritization; it is not an active implementation plan.

The technically preferred candidate is a **bounded ASCII-punctuation index**,
subject to the write-cost gates below. It addresses the reported single-backtick
filter and other literal symbols. Existing paths would remain for alphabetic/
Unicode queries and broad candidate sets. A general one/two-character index is
too costly for this increment.

This is a targeted improvement, not a guarantee that every one-character search
becomes fast. In particular, common letters still require exact counting, and
rare alphabetic/Unicode terms keep the existing fallback.

## Why the current index struggles

PostgreSQL documents that patterns without extractable trigrams can require a
full index scan. A literal backtick is such a pattern. The current application
already caches bounded match metadata, but data/workflow changes correctly
invalidate it. Fresh evaluation can therefore still scan millions of findings.
See [PostgreSQL pg_trgm](https://www.postgresql.org/docs/18/pgtrgm.html).

The prototype represents distinct ASCII punctuation present in description or
category as a small text array. A GIN array index finds candidates through
containment; the original escaped LIKE/ILIKE condition makes the final decision.
PostgreSQL's built-in GIN array operator class supports containment.
See [GIN operator classes](https://www.postgresql.org/docs/18/gin.html#GIN-BUILTIN-OPCLASSES).

## Method and limits

- Stable hash samples of 100,000 and 500,000 active SA01 findings, plus explicit
  rare-symbol, escaped wildcard, repeated-letter, Unicode, cross-field, archived
  and foreign-organization probes.
- Full finding-row clones with all **31 current source indexes**. No foreign
  keys or statement triggers are copied: write times isolate index maintenance,
  not parsing, authorization, job scheduling or complete import throughput.
- Three repetitions per read/write case; application-cache misses with database
  buffers already warm. No OS-cache eviction, server restart or global planner
  change. Primary controlled runs force custom plans only in their private
  benchmark connection; separate PREPARE/EXECUTE probes inspect generic plans.
- Reads mimic bounded 1,001-row discovery, exact grouped counting when necessary,
  and a 100-row page. Equality checks use EXCEPT in both directions against the
  original filter, without returning user finding text or IDs in output.
- Before/after baseline runs expose cache, bloat and shared-machine variation.
  These are local observations, not p95/p99 or production latency guarantees.
- The 500,000-row sample averaged 85 description/category characters, maximum
  190. Long-text extraction is exercised separately; it is not represented by
  the ordinary import-write sample.

## Measured larger-sample results

500,000 sampled findings, original punctuation extractor:

| Measurement | Existing path | Punctuation prototype |
| --- | ---: | ---: |
| Backtick discovery/count/page median | 1,023–1,295 ms | 1.88 ms |
| Literal percent | 991–1,322 ms | 1.74 ms |
| Literal underscore | 1,004–1,464 ms | 1.39 ms |
| Literal backslash | 995–1,308 ms | 1.08 ms |
| Added index, immediately after build | — | 2,310,144 bytes (2.20 MiB) |
| Added index after write/churn exercise and cleanup | — | 6,791,168 bytes (6.48 MiB) |
| Index build | — | 25.95 s |

The clone's existing indexes occupied 645.9 MiB; the table occupied 262.5 MiB.
Index growth after churn includes reusable/pending-list pages, not a steady-state
storage guarantee. GIN pending-list cleanup took 24.79 ms in this run, and a
backtick count immediately after writes took 7.64 ms.

### Write cost

Median milliseconds per 5,000-row batch, including commit:

| Operation | Baseline before/after | Punctuation prototype |
| --- | ---: | ---: |
| Insert | 1,002–1,460 | 1,864 |
| Workflow update | 1,193–1,333 | 2,039 |
| Description update | 1,289–1,483 | 2,097 |
| Archive | 208–233 | 283 |
| Restore | 1,288–1,305 | 2,143 |
| Delete | 93–146 | 132 |

Insert overhead was **28–86%**, depending on which baseline is used. This is
material and must not be described as a free improvement. Actual ingestion also
includes parsing, matching, foreign keys, revision triggers and other work not
measured here. Expression indexes have costs on insert and non-HOT updates, as
documented in [PostgreSQL expression indexes](https://www.postgresql.org/docs/18/indexes-expressional.html).

## Broader index rejected for this increment

On 100,000 short findings, a general distinct unigram/bigram GIN index initially
used 13.25 MiB versus 0.50 MiB for punctuation. It accelerated rare alphabetic and
Unicode searches as well, but ordinary insert batches took 798–916 ms per 1,000
rows versus approximately 168–178 ms baseline. Description updates took
953–1,001 ms versus approximately 222–227 ms. These are roughly 4–5 times the
baseline costs. Common `a` searches did not improve.

The naive SQL gram extractor also ran for more than 140 seconds on 100 long
descriptions before its verified private benchmark query was cancelled. The
schema was cleaned up. Later benchmark versions cap each long-extraction probe
at ten seconds. This extractor is unsuitable for unrestricted imported text.

## Planner and long-text findings

A combined presence predicate plus the original text predicate is insufficient
on its own: PostgreSQL sometimes chooses the old trigram index. The 500,000-row
mixed backtick-plus-letter case took 725.6 ms with a custom plan, versus 7.3 ms
with the prototype index under a generic plan. Do not change the server's global
plan-cache mode to address this.

A bounded, materialized candidate stage kept the prototype index in both plan
modes on 100,000 rows: the mixed-symbol probe fell from about 106 ms to about
4.9 ms after writes. PostgreSQL describes how explicit materialization controls
query folding in [WITH query materialization](https://www.postgresql.org/docs/18/queries-with.html#QUERIES-WITH-CTE-MATERIALIZATION).

The regex-only punctuation extractor did not eliminate write overhead and took
2.23 seconds to process 100 punctuation-dense descriptions of at least 20,000
characters. It does not by itself solve worst-case import cost.

The proposed bounded extractor checks byte lengths first. Above a proposed
4 KiB combined description/category threshold, it emits **all 32 supported ASCII
punctuation keys**. This is a conservative candidate superset: punctuation-free
long text may be considered, but a true punctuation match cannot be excluded.
The full original text is always rechecked. The threshold limits extraction
work; it never truncates, rejects or changes stored text or search semantics.

The bounded prototype was separately exercised on 100,000 sampled rows plus
long-text probes up to 21,000 characters. Backtick reads took 1.21 ms median;
the index initially occupied 0.50 MiB and built in 6.37 s. Its two long-extraction
cases (100 descriptions of at least 16,000 or 20,000 characters) took 12.12 and
11.39 ms respectively. A long punctuation-free value was a false candidate,
then correctly excluded; punctuation near the end of another long value was
correctly retained. Exact-set checks against the original filter still passed.
The bounded mixed-pattern materialized probe stayed around 5.2 ms under both
prepared-plan modes after writes. Ordinary 1,000-row inserts took 300 ms versus
154–202 ms in that run's before/after baselines (48–95% insert overhead); these
short-row write costs are still material. The final bounded design has not yet been measured on the full source
inventory or in real ingestion.

## Proposed application contract for step 2

1. Add a versioned immutable, schema-qualified key extractor and one partial GIN
   index for active findings. No stored description/category changes or new
   external dependency. Index creation/removal needs a migration and a measured
   maintenance plan; use concurrent construction where supported by the migration.
2. For short Finding-column patterns containing supported ASCII punctuation,
   discover at most 1,001 organization-scoped active candidate IDs in a separate
   bounded stage. For at most 1,000 candidates, apply all original literal and
   column filters, compute exact domain/severity totals and sort the matching IDs.
3. If the candidate bound is reached, use the current exact path. Never return a
   capped total or treat an incomplete candidate sample as all matches. Long
   descriptions conservatively contributing every key can trigger this fallback.
4. Retain current revision/epoch/tenant/schema/TTL invalidation and overdue
   boundaries. PostgreSQL maintains the expression index transactionally through
   imports, edits, archive, restore and purge. Cache reuse must not bypass role or
   tenant checks.
5. Preserve single-character input, literal `%`, `_` and backslash, current
   case behavior, NULL/empty distinctions and description/category separation.
   The index supplies candidates only; it does not redefine substring matching.

## Implementation and acceptance gates

- Measure the final bounded extractor/query on the full local inventory and
  representative long descriptions before enabling its query path broadly.
- Proposed read target: rare-punctuation browser response below 250 ms after
  invalidation on that inventory, with accurate totals and no common-query
  regression. This is an acceptance proposal, not an achieved full-size result.
- Compare real import throughput, workflow edits, archive and restore against
  the current build. Agree a write-overhead budget before broad rollout; the
  isolated 28–86% insert increase is not automatic acceptance.
- Test candidate overflow, long text with punctuation beyond 4 KiB, Unicode,
  mixed-field false positives, tenant isolation, every supported sort/cursor,
  concurrent edits and invalidation. Final CTE plans must be checked in both
  custom and generic prepared modes.
- Confirm index growth and GIN pending-list cleanup under sustained imports;
  verify rollback can disable the query path and remove the index safely.
- Run Chrome regression and hosted Linux CI for the actual implementation.
  This design exercise does not replace those checks.

## Reproduction and artifacts

From `backend`, while other heavy benchmarks/tests are idle:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_short_finding_search.py --rows 500000 --batch 5000 --variant punctuation
.\.venv\Scripts\python.exe scripts/benchmark_short_finding_search.py --rows 100000 --batch 1000 --variant punctuation_bounded --variant grams
```

The script requires the local demo connection, asserts the source schema,
changes only a randomly named `short_search_bench_<uuid>` clone and removes it
in `finally`. Functions/indexes are prototype-only, with no production migration.
Local JSONL artifacts under ignored `temp/` retain baseline, refined and bounded
runs, including the cancelled long-extraction experiment. No source credentials
or finding payloads are printed.

- `short-finding-search-100k.jsonl`: initial comparison, automatic plan selection.
- `short-finding-search-500k.jsonl`: completed controlled larger-sample comparison.
- `short-finding-search-100k-refined.jsonl`: partial run, deliberately cancelled
  during the unbounded gram long-text stress query after more than 140 seconds.
- `short-finding-search-100k-bounded.jsonl`: final bounded comparison, explicit
  prepared plans and ten-second guards on unsafe long-text probes.
