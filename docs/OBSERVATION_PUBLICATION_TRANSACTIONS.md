# Stage B private Publish/Undo core

14 November 2026 engineering increment after the hosted-verified storage
foundation (`2751c3b`, documentation `62e86e6`). This is a separate private-core checkpoint. No normal database migration or application restart was performed.

## Availability

There is no Publish, Undo or publication-setting HTTP write route. The public
service entry points reject every call, including calls with client flags or an
enabled database setting. Only private integration primitives exist. Do not wire
them directly to HTTP, a worker or an operator command: the remaining proof,
consumer, provenance and lifecycle work must join the same transaction first.
There is no new GUI or manual customer verification step yet.

Migration 0057 adds separate `organization_publication_settings`, default Off
with version 0, and two receipt fields: `admission_contract` and
`source_context_hash`. Existing receipts default to `reserved-storage-v1`, not
trusted transaction receipts. Downgrade refuses retained admission or policy
history, including disabled settings whose version has advanced. The normal
installation remains on schema 0055; 0056 and 0057 are unactivated.

## Transaction contract

`observation-publication-core-v1` is an internal staging contract. Neither a
read-only preview token nor a reserved-storage receipt can be upgraded into it.
It is also not the future integrated public write contract. A later integrated
writer must distinguish its receipts from core-only receipts before accepting
retries; it must never upgrade a replay by adding previously absent effects.

Private staging uses a savepoint and never commits. It acquires the existing job
admission and organization publication locks in their established order, then
locks the selected Finding without waiting. Authorization rechecks the active
account, password-reset requirement, actual organization-admin membership and
organization availability, including before returning a recorded replay.
Database conflict waits are bounded and caller lock-timeout/timezone settings
are restored on success or rollback. Hash timestamps use UTC; that does not
change browser display rules or workflow deadlines.

The server revalidates the strict native mapping and current independent source
binding, captures actual current scanner fields, and stages before/after
snapshots, minimal receipt, typed dependencies, current generation, source-field
materialization and Activity in one transaction. Injected failures roll these
effects back together. Original Finding UUID, scan/asset ownership, creation
time, status, assignment, notes, deadlines and verification decisions are preserved.
Approved scoring evidence must be explicitly revoked; it is never copied or
silently revived by publication or Undo.

Requests contain a request UUID, expected generation, review fingerprint,
nonblank rationale and strict boolean acknowledgment. They do not accept
replacement data, actor identity, workflow fields or flags granting authority.
Recorded requests are tenant- and actor-bound: an identical normalized authorized
retry returns its original receipt without reapplying fields, even after Undo or
policy disablement. Changed request reuse conflicts. A receipt describes the
original outcome, not the current publication state; consumers must reload.

When admission succeeds and effective fields are identical, the result is a
no-op, including on an active publication. It leaves provenance, generation,
history and Activity unchanged. No-op request UUIDs are not retained as separate
receipts. A different payload requires Undo and a fresh review. Policy no-ops
also preserve version and Activity; off/on changes advance the version and fence
old previews. Disablement blocks new publications but allows authorized Undo and
recorded outcome lookup.

## Sources and Undo

The write review binds up to 1,000 retained observation references per Finding,
not only the latest two timestamps. Adding a backdated reference invalidates an
old review. All referenced scan/asset owners and their creator scans must remain
live, active, complete and in the same organization; pending source operations
block admission. The manifest reads metadata, not historical observation payloads.
Its creator-link review is also capped at 1,000. Larger histories and orphaned
source contexts require a separate review/recovery design; they are not repaired
by guessing identity or deleting history.
The selected-source preview's existing stricter 100-creator-link bound still
applies to its original/selected/canonical asset scope.

Publish still selects only the latest unambiguously server-recorded, independently
reviewed native observation on the exact Finding. New ingestion does not establish
the most recent real-world scan time. Source hashes pin the selected source,
identity binding and original retention context. Dependencies additionally record
all bounded retained observation and owner references for later lifecycle guards.

Undo requires the exact active generation, retained unchanged before/after
snapshots, unchanged original owners and selected-source context, and current
scanner fields matching the published after-hash. Missing, oversized, tampered
or unsupported snapshots are refused before restoration; purged data is never
recreated. Current workflow is preserved even if it changed after publication.
A fresh review may include new observations; their reference set fences stale
Undo requests without selecting a newer payload as the restoration baseline.
Undo previews show actual bounded source-field differences and full-value hashes.
Only the source allowlist is restored, and the publication generation advances.

## Integration gates still open

- Add atomic list/count, Dashboard and evidence invalidation, including stale
  in-flight Dashboard/evaluation capture fences and consumer provenance.
- Bind proof/source digests to publication generation **even after Undo**, so
  returning to equal fields cannot revive an earlier approval or evaluation.
- Add admission and worker guards for affected archive/restore/purge, identity
  reviews/tool changes and identity-relevant asset updates, including imports.
  Protect reviewed history during restore duplicate cleanup. Include current
  observations added after publication when checking affected resources.
- Design recovery for changed/missing source context or history growth beyond
  the supported review bound; never silently overwrite later scanner edits.
- Add the default-off settings UI, guarded single-target actions, bounded
  provenance/differences, unknown-outcome handling and Chrome verification.
- Complete final review/regression and exact-commit Linux CI before activation.

Saved reports remain immutable. Manual Stage A acceptance remains TODO/deferred.

## Verification

Final targeted verification: **210 checks passed in 397.22 seconds (6 minutes
37 seconds)** on isolated PostgreSQL, with warnings treated as errors. This
includes request/gate unit tests and private-core, storage, public read-only
preview, migrations/drift, identity binding, consolidation, workflow and Activity
regressions. It covers real two-admin contention before commit, stale contexts,
backdated observations, bounded review, retries after Undo/disablement, current
workflow preservation, no-op versions/events and injected post-Activity rollback.
Existing large observation-history and dependency-index checks passed too.
High-severity Bandit, Python compilation and whitespace checks passed.
Earlier overlapping runs passed 99, 205 and 208 checks; the final run supersedes
those scopes. Review
reproduced incomplete inactive-admission cases, active-payload no-op handling and
missing Undo differences before fixing them. A new fixture's polymorphic JSON SQL
parameter required an explicit text cast; the corrected fixture passed.
No full local backend/frontend/Chrome rerun is claimed for this private-core
checkpoint. Exact-commit hosted Linux CI is the post-push acceptance gate;
its result is recorded in the delivery confirmation. Previous complete verification belongs to
the committed storage baseline, not this change.
