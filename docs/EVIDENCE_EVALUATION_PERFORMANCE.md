# Evidence evaluation performance and progress

Updated 28 October 2026. Local synthetic SA01 benchmark; qualified scoring remains off.

## Implementation

Current evaluation delivery (migration 0031): explicit organization-wide evaluation
is a durable worker job, not a long-lived browser request. Progress and results
survive navigation; simultaneous requests share one active organization job.
Transactional database revisions invalidate completed eligibility on material
input changes; policy and expiry are checked on every cached read. Dashboard
refreshes only read cheap state/cached eligibility plus existing score counts;
they never run the fingerprint. The setting is available but remains off by
default. See [background contract](BACKGROUND_EVIDENCE_EVALUATION.md).

The streamed browser-evaluation protocol/timings below describe the earlier
0030 checkpoint. Inventory **binding** still uses that streaming protocol, and
the same complete fingerprint algorithm is used inside durable worker jobs.
Durable-job full-size measurements are recorded below, separately from those streams.
The terminal progress batch is persisted even when ordinary updates are throttled;
the first durable run found that a fast final lifecycle batch could otherwise leave
the completed progress display short. A deterministic 44-record regression covers
that reporting defect. Inventory fingerprinting itself did not omit those records.

PostgreSQL hashes the complete existing semantic row projection using SHA-256
over canonical JSONB. A materialized compact UUID/hash projection is sorted by
UUID before streaming fixed-size row hashes to Python in batches of 5,000.
This avoids transferring/decoding millions of full JSON payloads and avoids the
base-table random-UUID-order heap scan. Python retains the ordered SHA-256
inventory/lifecycle fingerprint. Memory use in Python remains batch bounded;
PostgreSQL can spill the compact materialization/sort to temporary disk.

The fingerprint format is explicitly `dashboard-organization-inventory-v2`.
Old v1 bindings are not silently accepted: rebind/save/review before qualification.
No source records are deleted or rewritten by this change. Each explicit scan
computes the exact count/fingerprint afresh, without sampling or omitted inventory
fields. Completed eligibility results are cached only with revision/policy/expiry
validation; that is separate from computing a scan's inventory fingerprint.

At the 0030 checkpoint, Load current inventory and Evaluate evidence across all domains used authenticated,
no-store NDJSON progress responses. Each operation uses one repeatable-read
snapshot for counts, inventory and qualification/source checks. Progress reports
actual processed/total records, phase and elapsed time. The browser timer keeps
updating during counting/sort preparation; counts advance only on completed
batches. The final result is accepted only after an explicit result event;
truncation/errors/cancellation cannot qualify partial output. Cancel/navigation
aborts the browser request; a currently running database fetch may finish before
server-side cleanup, so cancellation is not an instantaneous database kill.

Existing JSON endpoints remain compatible. Save/review still perform authoritative
scope checks synchronously, using the same faster fingerprint algorithm. They
do not currently stream write progress. At that checkpoint scoring activation was unavailable.

## Local observations

### Durable worker acceptance (28 October, migration 0031)

Real Chrome → Next proxy → API → worker, idle local SA01; no concurrent builds,
regression suites, imports, cache flush or other inventory scans during timing.
The second viewer joined the first job (same UUID), rather than starting a second
expensive scan. Navigation away and back retained its progress/result.

| Durable job | HTTP 202 acknowledgement | Browser-observed completion | Worker elapsed | Records |
| --- | ---: | ---: | ---: | ---: |
| First pass, shared with another viewer | 70.5 ms | 115.353 s | 112.8 s | 6,374,205 |
| Repeat | 115.0 ms | 111.645 s | 110.2 s | 6,374,205 |

Both fingerprints/counts agree: 2,798,320 assets + 3,575,841 findings + 44
lifecycle records, zero qualified domains. The final progress reaches the exact
total after the terminal-batch reporting fix. The first nonzero browser-observed
counts arrived after 39.7/37.1 s; phase preparation is still real work, not a hang.
A cheap Dashboard-state read by the other viewer during the first scan took
64.5 ms. These are first/repeated local observations, not controlled cold/warm
measurements, sustained-load acceptance or a production guarantee.

Real running-worker cancellation acknowledged in 68.4 ms and drained its current
database fetch in 25.756 s (including polling). It published no partial result.
An earlier completed result is not revoked merely by cancelling a retry; revision,
policy and expiry checks still decide its usability. All inventory counts and AI
usage stayed unchanged; no jobs/cursors remained and both temporary viewers were
removed. The setting remained off. Database-wide temporary bytes grew by about
1.90 GB over the two scans plus cancellation; this is cumulative, not peak disk.
Artifact: `temp/testing/evidence-http/9848f5c3a47cc455fd194e33/results.json`.

### Earlier synchronous/streaming observations (0030)

| Measurement | Inventory | Lifecycle records | Time |
| --- | ---: | ---: | ---: |
| Original Python/full-payload HTTP evaluation | 6,374,161 | Not separately logged | 462.203 s |
| New DB row hashes, base UUID scan diagnostic | 6,374,161 | 44 | 411.719 s |
| New compact materialized/sorted projection, evaluation | 6,374,161 | 44 | 100.203 s |

Population: 2,798,320 active assets and 3,575,841 active findings. Total progress
denominator includes lifecycle rows: 6,374,205. Both new query plans produced the
same v2 fingerprint. The final plan reached the findings phase at 45.2 s and
lifecycle phase at 100.2 s. Qualified domain count remained zero.

The 100.203 s run used the service directly with a repeatable-read demo connection,
not a new authenticated end-to-end HTTP timing. The original time came from HTTP
request logs. Cache warmth was not controlled; the revised run initially overlapped
the preceding read-only diagnostic and some test/build activity. The observed
4.6× speedup (~78% reduction) is indicative only. No demo rows were modified.

## Authenticated Chrome / HTTP acceptance (28 October)

Installed Chrome 155, the running Next proxy and API, and local PostgreSQL;
two separate temporary viewer accounts signed in through the normal login API.
No restart/cache flush preceded these timings, so **first-pass/repeated**, not
controlled cold/warm, is the appropriate description. No builds or regression
suites ran during the four complete scans.

| Real browser evaluation | Completion | Records processed |
| --- | ---: | ---: |
| First pass | 116.524 s | 6,374,205 |
| Repeat | 110.537 s | 6,374,205 |
| Two simultaneous viewers: viewer 1 | 135.653 s | 6,374,205 |
| Two simultaneous viewers: viewer 2 | 133.253 s | 6,374,205 |

All four streams contained 1,281 counted progress events, reached the exact total
monotonically, returned zero qualified domains and agreed on the complete v2
inventory fingerprint. An unrelated profiles read during simultaneous scans took
17.1 ms. First nonzero progress in the first/concurrent runs appeared after
approximately 32.5–33.6 s: materializing/sorting still takes time before a batch
can be counted. The repeat's original first-progress DOM timing read a retained
completed progress bar and is excluded; the harness now requires Processing
state. Final-response timings/counts/fingerprints were not affected.

Database-wide temporary bytes increased by about 3.11 GB over this run, including
four complete scans and an early cancellation. This is cumulative PostgreSQL
spill/write accounting, not peak disk capacity, and is not isolated per request.
No controlled CPU profile, sustained load, production or hosted-Linux performance
claim is made. Artifact: `temp/testing/evidence-http/ac002e283bcb407b6e722576`.

### Cancellation defect found and fixed

An additional cancellation during real database work exposed an idle transaction
remaining open beyond 180 s. Starlette's synchronous-iterator adapter did not
explicitly close the underlying generator after disconnect. The response now
closes that iterator in shielded cleanup, releasing its cursor, repeatable-read
transaction and connection even on disconnect/send failure. Two PostgreSQL/ASGI
regression cases cover both supported disconnect branches.

After loading the fix locally, the real Chrome Cancel action recovered the UI in
38.9 ms; the other viewer's profiles read took 17.4 ms. The cancelled database
reader drained in 27.795 s, including polling overhead, after its current fetch
returned. Cancel **does not kill an executing database statement instantly**.
Artifact: `temp/testing/evidence-http/447bbaf0ba1f93a7628b3de7`.
SA01 inventory counts and AI usage stayed unchanged; each run removed its own two
temporary accounts. The fix was activated only after confirming no active import,
report or archive jobs; the demo restart retained existing data/accounts.

## Remaining rollout gates

Durable background jobs and safely invalidated revisions are now implemented;
manual full-inventory scans remain explicit. Before broader rollout, measure peak
temporary-disk/CPU use and sustained multi-tenant load. Hosted functional CI is
green for implementation `5ce836b`
([run 40749424003](https://github.com/shalisarakkal/AuditMind/actions/runs/40749424003));
that is not hosted performance acceptance. Future implementation changes need
their own hosted verification. Controlled cold-cache measurements remain unperformed.
Keep the setting off by default and do not add automatic Dashboard scans on the
strength of these local measurements.
