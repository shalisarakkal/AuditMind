# Background worker concurrency

`WORKER_CONCURRENCY` controls simultaneous queued background jobs in one
installation. It defaults to **1**, accepts **1–32**, and does not limit the
number of organizations, users or registered assets. `start-demo.ps1` also
defaults to **1**. Parallel rollout is on hold while single-organization behavior
is validated. The two-slot setting is used only by the isolated acceptance test.

Requested next control: a **platform-admin setting** for worker concurrency,
with a default of one, bounded validation, safe changes while work is active,
and audit history. That UI/database control is not implemented yet; an environment
variable or launcher argument is not a substitute for it. Keep normal operation
serial until that control is reviewed and verified.

Different organizations can process concurrently. Each organization has at most
one active queued job across imports, archive/restore/purge jobs, reports,
document indexing and evidence evaluation. Its other jobs stay pending instead
of consuming slots waiting for its inventory lock. Shared-standard indexing has
its own shared scope. Small synchronous API operations retain their existing
inventory locks; they are not worker-pool reservations. Uploading file bytes from
the browser and processing accepted jobs are separate operations.

Admission uses a short database lock and durable dispatch metadata. Organizations
never served are considered first, then those least recently dispatched; jobs
within a scope use their existing queue timestamps. Existing low-priority
automatic archive cleanup remains behind user work until its configured maximum
wait. Organization deletion runs only when the worker has no other active jobs.

## Running and changing the limit

Apply `alembic upgrade head` before starting the updated worker. Migration **0032**
adds the `worker_dispatch` scheduling table; it does not rewrite inventory.
The worker refuses startup if that table is missing. Stop admission and let
running jobs finish before changing the limit, then restart the worker with the
new environment value. Only one healthy worker pool may run per database schema;
a duplicate launch exits with an error.

The pool uses threads with independent database sessions. This permits overlapping
database and file I/O; it does not promise linear speedup for CPU-bound parsing.
For more than one slot, the CLI reserves a database connection pool of
`3 * WORKER_CONCURRENCY + 4` connections. Budget those connections alongside API
connections and PostgreSQL's limit. Concurrent large imports also multiply
working memory and inventory-matching costs. Start conservatively and measure.
This increment is not a distributed worker fleet or a SaaS capacity certification.
The representative SaaS scale test remains on hold.

The startup log records the slot count. Heartbeats cover all active jobs.
The first Ctrl+C stops new admission and drains running jobs while heartbeats
continue. A second Ctrl+C terminates immediately; existing stale-job recovery
handles interrupted jobs on restart, subject to its retry limit. Loss of the
pool's database leadership connection stops new admission. Existing job and
organization locks continue protecting running operations.

## Verification

Run the focused PostgreSQL tests with the backend virtual environment:

```text
python -m pytest -W error --require-postgres tests/unit/test_worker_pool.py tests/integration/test_worker_pool.py -q
```

From the repository root run:

```text
node scripts/worker-pool-acceptance.cjs
```

The acceptance script creates a guarded temporary local schema and starts the
actual API and two-slot worker. It checks cross-organization concurrency,
same-organization queuing, duplicate worker rejection, interrupted-job recovery
and tenant-safe asset updates. It uses small files and no external inference.
Artifacts go to `temp/testing/worker-pool/`; fixtures and owned processes are
removed afterward. CI runs this check on Linux as well. Passing local checks
does not establish that a particular pushed commit has passed hosted CI.
