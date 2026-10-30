# SaaS background processing: three-phase design review

Status: proposed design based on the current implementation and the user's
three-phase targets. This document does not enable parallel operation, provision
hosting or claim measured capacity. Normal processing remains one slot. Phase 1
has a scheduling foundation and two-slot correctness evidence; Phases 2 and 3
require implementation changes.

## Targets and completion criteria

| Phase | Required behavior | Principal change |
| --- | --- | --- |
| 1 | Up to 32 ready jobs from 32 organizations executing concurrently | Platform-admin setting, resource budgeting and representative 32-slot verification |
| 2 | Scale beyond 32 toward 1,000 concurrent jobs from 1,000 organizations | Distributed worker fleet, shared durable storage, distributed reservations and measured database capacity |
| 3 | More than one job from the same organization executing concurrently | Separate preparation from publication, then permit concurrent publication only for proven independent work |

The Phase 2 target means **1,000 actually executing jobs**, not merely accepting
1,000 uploads into a queue. Queued jobs, executing preparation, waiting to publish
and actively publishing must be separately observable. Jobs waiting for capacity
must not appear to be processing. Concurrency is distinct from completion rate:
more active jobs may slow each job when they share a saturated resource.

All concurrency limits are platform-admin controls, not organization-count
limits. Requested limits must be checked against provisioned capacity. Registered
organizations, signed-in users, API request capacity, concurrent file transfers
and background execution slots have separate budgets.

## Current implementation and constraints

- `app/worker/runner.py` runs one CLI process with 1–32 threads and deliberately
  refuses a second pool for the same database/schema. This must change before
  horizontal execution; simply removing the startup guard is unsafe.
- `app/worker/scheduler.py` atomically claims jobs across five tables under a
  short global admission lock, counts running reservations and excludes busy
  organizations. Durable dispatch state provides fairness. This is a useful
  Phase 1 baseline, not a verified 1,000-slot scheduler.
- `app/services/org_lock.py` protects bulk inventory mutations and retains a
  separate session-level connection for job liveness. The organization lock
  protects lookup-then-insert matching, including policies allowing duplicates.
- Imports stage rows, then load matching inventory and publish while holding the
  organization transaction lock (`ingestion_service.py`). Concurrent large
  imports multiply matching-index memory and database work.
- The configured connection-pool ceiling above one slot is `3 * slots + 4`.
  At 32 it is 100 worker connections before API connections. It is a ceiling,
  not an assertion that all connections are always open. Extending this formula
  to 1,000 would allow 3,004 connections and is not the Phase 2 design.
- Uploads currently use a filesystem path. A fleet needs storage every eligible
  worker can access, including retrying jobs after a machine is lost.

## Phase 1: make 32 cross-organization jobs a verified feature

1. Add platform-admin concurrency configuration with version conflicts, audit
   events, desired/effective values and an explicit default of one. Keep the
   operator resource ceiling separate from the admin-selected execution limit.
   Lowering a limit stops new admissions until active jobs drain; do not kill
   active imports. Increasing it must respect database and memory budgets.
2. Measure one representative job's peak memory, CPU time, database occupancy,
   write throughput and elapsed time. Establish reserved API capacity and a
   response-time target before the test, rather than inventing a hardware size.
3. Exercise 2, 4, 8, 16 and 32 slots, with the final 33-organization/five-file
   scenario. At a barrier with all work ready, assert 32 distinct organizations
   active and 133 jobs pending. The unserved organization receives the next
   free slot; no organization has two active queued jobs.
4. Verify actual simultaneous execution with job start/finish observations,
   not only `running` database flags. Record API p95/p99 latency, scheduling
   delay, throughput, peak memory, connection usage, lock waits, disk/WAL load,
   correctness, forced interruption and resume outcomes.

Passing validates this workload on the tested hardware, not all file types or
1,000-organization SaaS capacity. Keep API and worker resource reservations
separate so background work cannot consume all request capacity.

## Phase 2: distributed execution toward 1,000 organizations

Use stateless API instances, shared upload/artifact storage, durable job state,
and a fleet of bounded worker processes across machines. CPU-heavy preparation
should be able to use separate processes, not a single 1,000-thread interpreter.
An illustrative 40 instances with 25 slots each totals 1,000 slots; this is
arithmetic, not a sizing recommendation or evidence of achievable throughput.

Keep PostgreSQL job state authoritative initially. Introduce indexed execution
records and organization admission rows instead of repeatedly scanning all job
tables to count global work. Workers reserve capacity through short atomic
transactions, with leases, worker identity, attempt number and fencing tokens.
A resumed attempt must not allow an expired worker to publish or mark success.
Claims and per-organization reservations must be atomic, including absent rows.
Bound admission by deployment-wide capacity as well as per-worker limits; avoid
a single long-held global scheduler lock. Measure claim contention before
choosing coordinator partitioning by organization.

Delivery/recovery is treated as at-least-once. Preserve staged checkpoints and
make each publication idempotent; commit outcomes, associations and progress
consistently. A worker crash after database commit but before acknowledgement
must not create a second inventory update. If a message broker is introduced,
use a transactional outbox or equivalent reconciliation to avoid lost work
between database commit and enqueue. A broker is an implementation choice, not
an automatic requirement or a cure for database bottlenecks.

Replace local upload dependencies with tenant-scoped immutable object keys,
bounded transfers, retention and checksum verification. Store references in
jobs; verify tenant access on every fetch. Preserve exact-file Skip/Ask/Reimport
semantics. An Ask decision parks the job for user action and releases execution
capacity; it must not hold a worker waiting for a dialog.

Introduce separate budgets for CPU preparation, inventory publication,
document indexing, report/provider calls and evidence evaluation. Fair admission
and per-tenant queue/byte quotas prevent one tenant's backlog dominating the
fleet. Autoscale against oldest-ready-job age, CPU/memory and database pressure;
do not autoscale solely because queue length grows. Suspend admission or reduce
write concurrency when the database is saturated while preserving queued work.

Database access must use bounded pools and short transactions where semantics
allow. Current session-level advisory locks are incompatible with PgBouncer
transaction pooling: retain a dedicated session-compatible path until those
locks are replaced by reviewed lease/fencing mechanisms. Do not introduce
transaction pooling underneath the existing locks without that migration.

Validate 64/128/256/512/1,000 concurrent organizations on suitable isolated
infrastructure, including burst, sustained load, worker/node loss, deployment
draining, database interruption and noisy-tenant cases. Validate settings changes
across replicas, tenant isolation, deduplication and UI latency throughout.
The full 1,000-job target is complete only when observed with representative
files and agreed latency/recovery objectives. If one database cannot sustain the
measured workload, route tenants to independent database/worker groups; each
group needs its own fair scheduling and a share of the platform capacity budget.

## Phase 3: concurrency within an organization

### 3A: parallel preparation, serialized inventory publication

Split accepted jobs into explicit stages: receive/checksum, parse/validate,
stage, ready to publish, publish, complete. Permit several preparation tasks
for one organization while maintaining one publisher. Preparation must not
allocate canonical inventory identities or assume a matching-index snapshot
remains valid. Re-read matching inventory and apply the configured policy at
publication. A prepared job waiting for the publication slot releases its
preparation worker; it must not deadlock the pool by occupying every slot.

This is useful same-organization parallel processing, but **not concurrent
inventory writes**. UI and acceptance tests must say which stage runs in
parallel. Preserve current import visibility/atomicity and resume guarantees;
do not silently expose partially committed imports as a performance shortcut.

### 3B: concurrent publication for independent work

Define canonical asset/finding identity and conflict rules before narrowing the
organization lock. File names, source names and arbitrary file hash partitions
do not establish independence: different files/sources may update the same host.
Overlapping hostname/IP/cloud-ID aliases must resolve consistently, including
assets first created concurrently. Existing policies that deliberately allow
duplicate assets must remain valid; adding a blanket hostname unique constraint
would change their meaning.

For proven independent target sets, reserve stable target identities and apply
ordered row/key locks, version checks or deterministic routing. Overlapping
updates serialize or return a defined conflict; retries must be bounded and
idempotent. Define ordering when two imports provide different values for the
same property, including source precedence and observed timestamps. Reapply the
organization's **Asset already in inventory** policy at commit time. Preserve
finding workflow notes, assignments, source associations and archive ownership;
imported-finding reconciliation is a separate approved design boundary.

Archive/restore/purge and organization deletion need exclusion barriers against
affected publishers. Configuration changes require a captured policy version
and an explicit choice of snapshot versus conflict/revalidation semantics.
Evidence evaluation/report reads need consistent snapshots and revision-based
invalidation while writes continue. Set a lock acquisition order across all
operation types to prevent deadlocks. Partitioning or chunk commits that change
whole-file atomicity require an explicit design decision and separate validation.

Start with a per-organization preparation limit of two, then four if measured
beneficial. Concurrent publication stays off until overlapping and disjoint
target tests pass: duplicate prevention, intentional duplicates, conflicting
values, archive races, settings changes, report/evidence snapshots and recovery
after commit-before-acknowledgement. Setting a limit above one alone is not enough.

## Settings and implementation order

Proposed platform-admin controls: deployment-wide active-job limit, per-tenant
preparation limit, per-tenant publication limit, workload-specific budgets and
queue/byte quotas. Per-instance capacity remains deployment configuration,
reported to the control plane. Desired capacity is distinct from currently
available/effective capacity; tenants cannot enlarge deployment-wide limits.
All changes are authorized, audited and safe during draining/failover.

Deliver Phase 1's platform control and measurement harness first. Then introduce
Phase 2's fleet/lease/storage foundation with small tests before any costly
1,000-job exercise. Phase 3A can follow that foundation without waiting for a
1,000-job benchmark; Phase 3B requires its own identity/conflict design review.
No cloud deployment, large load test or concurrency activation is performed by
this design review.

## Primary technical references

- [PostgreSQL SELECT](https://www.postgresql.org/docs/18/sql-select.html):
  SKIP LOCKED is suitable for queue consumers, not consistent inventory reads.
- [Python 3.12 threading](https://docs.python.org/3.12/library/threading.html):
  threads overlap I/O; separate processes can use cores for Python CPU work.
- [PgBouncer feature compatibility](https://www.pgbouncer.org/features.html):
  session advisory locks require session-compatible pooling.
