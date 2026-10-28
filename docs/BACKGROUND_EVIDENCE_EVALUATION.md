# Background evidence evaluation and opt-in Dashboard scoring

28 October 2026. Local pilot implementation; not a production rollout. The
organization setting remains **off by default**. Saved audit reports, risk
snapshots, finding workflow assertions, severity deductions and domain weights
are unchanged. No AI or embedding provider is called.

## Job lifecycle and access

Migration `0031` adds durable evaluation jobs and organization evidence revisions.
**Settings → Scoring and evidence review → Evaluate evidence across all domains**
queues a job; opening Settings only reads its status. Evaluation always covers all
seven domains and the whole organization, not the domain selected in the editor.
Only saved inputs are included. Navigation and browser closure do not stop the
worker. Reopening Settings reconnects to the latest job.

Members and read-only platform administrators may request/read this compute-only
operation; only organization administrators may edit/review qualifications or
change scoring mode. Cancellation requires the requester or an organization admin.
Admission rechecks access and organization lifecycle after lock waits. An active
job prevents organization archiving; organization purge removes its job metadata.
One pending/running evaluation per organization is enforced by both admission
locking and a partial unique database index. Concurrent requests share that job.

The existing worker claims jobs with `SKIP LOCKED`, records progress/heartbeat,
and uses a job advisory lock during processing/recovery. Interrupted jobs may be
requeued up to three times; exhaustion fails safely. Pending cancellation is
immediate; running cancellation waits for the current database fetch to finish.
Failed/cancelled jobs publish no partial result. A previously completed result
may still authorize scores if it independently passes every current validity check.

API paths, relative to `/api/v1/orgs/{org_id}/scoring`:

| Request | Purpose |
| --- | --- |
| `POST /evaluations` | Queue or join the active job; HTTP 202. |
| `GET /evaluations/current` | Latest job, or null. No inventory scan. |
| `GET /evaluations/{job_id}` | Read that organization's job; foreign IDs return 404. |
| `POST /evaluations/{job_id}/cancel` | Authorized cancellation request. |
| `GET /dashboard-state` | Cheap mode/version/revision/current-evaluation identity. |
| `PATCH /settings` | Admin-only expected-version mode change, with audit event. |

All status/state responses are `no-store`. Existing synchronous/streaming read
endpoints remain compatible; the UI uses durable jobs for organization evaluation
and streaming only for explicit inventory binding. Save/review still perform
authoritative synchronous scope checks; they are not backgrounded by this increment.

## Safe invalidation

The worker evaluates inventory, source integrity and qualifications in one
repeatable-read snapshot. Counts and the full v2 inventory/lifecycle fingerprint
retain the existing algorithm; there is no sampling or approximate count.
It captures the organization's revision and evaluator/policy identity.

Schema-qualified PostgreSQL statement triggers increment the affected organizations'
revisions transactionally for asset/finding material changes, relevant lifecycle
events, operational document/version changes and qualification changes. Inserts,
deletes, bulk statements/COPY, organization moves, primary-ID changes and cascades
are covered. A bulk statement bumps each affected organization once, not once per
record. Rollback rolls back invalidation; TRUNCATE conservatively invalidates all
organizations. Workflow status/assignment/deadlines/notes and organization branding
do not alter evidence source hashes or this baseline scoring policy, so updates
limited to those fields do not invalidate evidence. Lifecycle events are filtered
to the same material event types included in the inventory fingerprint.

The worker discards a known-changed snapshot as **superseded** before publication.
Every subsequent Dashboard/cache read also checks the current revision, evaluator
identity, structured result integrity and review expiry. Therefore a writer that
commits just after the publication check still invalidates the cached revision;
there is no time-only cache window or stale baseline fallback. Revision checks
do not require another inventory scan. The evaluator version must be bumped when
validation semantics change; the policy identity includes profiles, binding version
and maximum age. Trigger changes require a new migration/versioned installer.

Direct DBA writes that bypass/disable triggers are outside the application write
contract. Maintain triggers on deployment and validate migration round trips. The
transition-table mechanism follows PostgreSQL's [trigger definition](https://www.postgresql.org/docs/current/sql-createtrigger.html).

## Dashboard behavior

**Off:** existing findings-based baseline, explicitly labeled as such. Empty
organizations still display Not assessed. Existing nonempty unobserved domains
can score 100; this is not evidence-qualified coverage.

**On:** only currently eligible domains receive the existing deterministic score.
Missing, stale, expired, revoked or conflicting evidence stays unscored, never
silently 0 or 100. A genuine score of 0 remains visible. The overall score requires
all seven qualified domains with compatible declared scope; otherwise it is null.
Weights are not renormalized over the available subset. Domain provenance includes
qualification/version/scope, review/expiry, observation dates and source references.
The earliest eligible review expiry invalidates the complete cached evaluation;
reevaluate to establish which remaining domains still qualify.

The browser polls cheap state every ten seconds and on focus, matching mode,
settings version, evidence revision and evaluation identity before displaying a
Dashboard response. Old-organization/out-of-order responses cannot replace current
state. Failed state verification hides scores. A change in another session may
remain visible until that next poll; this is not real-time server push. Dashboard
requests count findings as before but never fingerprint the inventory or autoqueue
expensive evaluations. Settings polls active jobs every second, terminal jobs
every ten seconds, without extending idle login sessions.

Admins confirm mode changes in the application dialog. Switching off restores
baseline interpretation without deleting reviews/jobs or rewriting saved reports.
Migration downgrade to `0030` disables any enabled mode and increments its settings
version before removing unsupported job/revision structures. Re-upgrade starts off.

## Pilot limits and next gates

Manual evaluation, existing shared worker capacity, and full inventory scans remain
intentional. Queue time depends on other jobs. No scheduler, dedicated worker pool,
incremental fingerprint, real-time push or automatic job-history retention policy
is delivered here. Terminal metadata remains until organization purge; evaluate a
bounded retention policy before high-frequency scheduled use. Measure sustained
multi-tenant load and peak PostgreSQL CPU/temp-disk cost before broader rollout.
The full-size local timings are not production capacity guarantees. Keep default
off; global default/switch removal and production deployment need later approval.
For a future rolling deployment, keep this mode off until API, worker and frontend
versions are all compatible with 0031. Disable it before a code-only rollback;
the migration downgrade also disables it, but cannot protect mixed old API nodes
that ignore the new setting. Local activation restarts the stack together.

See [Chrome verification](EVIDENCE_USER_VERIFICATION.md),
[performance measurements](EVIDENCE_EVALUATION_PERFORMANCE.md), and
[dated validation](PHASE4_VALIDATION.md).
