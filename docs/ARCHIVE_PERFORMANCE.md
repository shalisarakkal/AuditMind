# Archive, restore and purge performance

Local review, 4 November 2026. These are service execution measurements, excluding
HTTP acknowledgement, worker queue wait and browser polling. They are not SaaS
capacity or production latency guarantees.

## Method

`backend/scripts/benchmark_archive_lifecycle.py` creates a disposable, randomly
named schema in a local PostgreSQL `*_test` database. It explicitly creates and
verifies private copies of all application tables, including current indexes and
statement triggers. No demo organization, uploaded file or setting is changed.
The schema is removed in `finally`, including on failure.

The test uses random UUIDs, one completed upload, one finding per asset, and
100 separate manual findings. It runs the real archive services with normal
20,000-row transactions and captures committed progress and SQL timings.
After upload purge it verifies that only the manual findings remain; those
then undergo archive, restore, rearchive and permanent purge as separate jobs.
This manual sequence models the existing one-job-per-selected-item behavior,
not a single combined SQL bulk update.

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_archive_lifecycle.py --rows 100000 --manual 100
```

Do not run this together with integration tests that recreate the public test
schema. Earlier exploratory timings before explicit table-isolation assertions
were added are excluded from the final results.

## Measured results

One local run, 100,000 assets plus 100,000 uploaded findings:

| Operation | Execution time |
| --- | ---: |
| Archive upload and its rows | 21.564 s |
| Restore upload and its rows, corrected query | 85.914 s |
| Archive again | 23.176 s |
| Permanently purge upload and its rows | 9.167 s |
| Archive 100 manual findings, separate jobs | 2.064 s total |
| Restore those 100 manual findings | 3.764 s total |
| Archive those manual findings again | 1.964 s total |
| Permanently purge those 100 manual findings | 2.500 s total |

The corrected duplicate check executed 30 statements in 4.925 s total,
maximum 0.652 s per statement. Restore was dominated by index writes:
asset-update statements took 4.7–11.5 s per chunk and finding updates
5.4–15.0 s. Its largest observed progress gap was approximately 19.8 s,
between the asset phase and the first committed finding chunk.

All synthetic lifecycle row-count assertions passed. Artifacts from this run:
`temp/archive-perf-100k-fixed-private.jsonl` (local, not committed).
These are single observations on a shared development machine, not percentiles.

For comparison, the committed restore implementation was loaded into a separate
benchmark process, using the same private-schema generator and 100,000/100,000
row counts. Archive took 20.928 s. Restore stopped at 62.907 s after restoring
all assets but only the first 20,000 findings: the following duplicate check
exceeded the benchmark's 20-second per-statement guard. The corrected run used
the same guard and completed. This is not a measured full legacy restore time
or a claim that production has that timeout. Its private schema was removed
after failure. Artifact: `temp/archive-perf-100k-baseline-private.jsonl`.

## Restore query correction

The former duplicate check used `IS NOT DISTINCT FROM` for asset and category
identity. That prevented efficient equality plans as successive chunks became
active. The replacement separates the six disjoint combinations of asset
presence and categorized/uncategorized/NULL-description identity, exposing exact
equality keys to existing indexes without another index or migration.

NULL remains distinct from an empty string. Source and organization must match;
description is ignored when category is present, as before. Findings with saved
workflow history remain protected by the `workflow_version = 0` deletion guard.
All statements stay in the existing chunk transaction and organization lock.

## Interpretation and remaining limits

Archive hides rows; purge permanently deletes them. They have different costs.
Restoring rows reinserts entries into active-row indexes and is substantially
more expensive than archiving them. This review does not remove those indexes.

Progress counts commit once per 20,000-row chunk. Statistics maintenance and a
slow index-writing chunk can cause a visible pause despite active work. A
smoother heartbeat or phase display would be a separate UI improvement; it must
not report uncommitted rows as complete.

The service currently collects target IDs before processing chunks. Million-row
memory use, concurrent tenant throughput, shared-asset overlap, very large
duplicate populations and sustained I/O contention remain separate load tests.

## Verification and activation

The archive API regression file passes all 57 tests, including 22 new
NULL/empty/source/organization/history cases with and without assets. These
checks exercise the real API and PostgreSQL, including bulk archive and restore.
Ten lifecycle-boundary checks and four retention-time unit checks also pass:
71 focused tests in total. No disposable benchmark schemas remain.
High-severity Bandit and whitespace checks pass for the changed service.

The review API and worker were left uninterrupted during measurement, then
restarted on 5 November after confirming no pending/running imports, archive,
report or evaluation jobs. Readiness, login and the frontend authentication proxy
pass; the archive service correction is loaded. No migration or frontend rebuild
was needed. Real Chrome against an isolated API/worker/PostgreSQL fixture verifies
the literal-backtick column filter stays at one after workflow save, falls to
zero after archive and returns to one after restore, retaining the saved rationale.

For Chrome acceptance after activation, create a disposable manual finding,
archive it, restore it from Archived, then archive and purge it. Confirm the
correct item disappears/reappears and that workflow notes survive restore.
Use a disposable upload to repeat the upload lifecycle. Wait for each job to
complete before comparing list counts. Purge is permanent, so use test data.
