# Finding source observations (PB-1.1)

7 November 2026: PB-1.3 adds a read-only [identity foundation](FINDING_IDENTITY.md).
Migration 0046 adds optional administrator-reviewed tool/asset bindings;
observations still remain ineligible for reconciliation.
Candidate diagnostics do not change import matching or authorize reconciliation.

PB-1.1 records per-import finding provenance. Migration `0040` adds
`finding_observations`; it does not backfill or infer historical observations.
Current finding matching, source payloads, workflow decisions, scores and saved
reports retain their existing behavior. Comparable scans (PB-1.2) and
reconciliation (PB-1.3) remain separate work.

## Recording and identity

Each accepted parsed finding occurrence creates one observation, including
duplicate occurrences in the same file and later uploads. Invalid/skipped rows
and rejected all-or-nothing imports create none. Inventory-only rows have no
finding observation. All finding-producing parser paths use the same publisher:
generic CSV/JSON, Nessus, asset-bearing profiles and event aggregates.

Each record captures organization, canonical finding UUID, original import UUID,
live scan link, filename, parser/profile, source row, import occurrence sequence,
recording time, source-observed time when available, asset identifiers, supplied
source identifiers and a snapshot of the imported finding payload. Recording
time is not substituted for an unknown observation time. Explicit `observed_at`
values must include a timezone offset and convert to a valid UTC timestamp;
invalid, naive or out-of-range values stay in the raw
snapshot while the observation timestamp is null with an explanatory reason.
Event aggregates retain their source-provided first/last times.

Native Nessus records plugin ID, port and protocol. Explicit generic
`source_instance_id`, `source_finding_id`, `instance_discriminator`, `port` and
`protocol` fields are retained as supplied, not validated identities. A CVE,
category, description, filename or row number is never promoted to a stable
finding/tool-instance identifier.

**All current observations are ineligible for automated reconciliation.** Current
imports do not automatically configure tool-instance namespaces or canonical
asset mappings. Migration 0046 adds explicit per-observation administrator review;
a resulting identity candidate still grants no reconciliation authority. Each observation carries `reconciliation_eligible=false` and
specific reasons. Even supplied identifiers and native plugin IDs do not grant
comparability or authorize automatic updates. Existing duplicate keys associate
observations with the finding chosen by current matching; this association is
not proof that the rows share a stable external identity. Ambiguous matches and
missing identifiers never become reconciliation eligible.

## Compatibility, atomicity and retention

- Update and Leave unchanged preserve their asset behavior and still record
  finding occurrences. Add a duplicate keeps creating separate assets/findings;
  observations do not merge them or transfer workflow decisions.
- Changed severity/details on a duplicate are visible in its new observation;
  they do not overwrite the canonical finding, notes, assignee or deadlines.
- Findings and observations publish in the same transaction under the existing
  organization import lock. Bounded COPY batches include duplicate-only imports.
  Failure rolls back both; restart republishes from authenticated staging. The
  unique `(import_id, occurrence)` constraint guards accidental double recording.
- Observations are append-only through the application: no create/update/delete
  observation API is exposed. Database administrators retain normal maintenance
  authority. Lifecycle foreign keys are an explicit retention exception.
- Soft archive/restore leaves observations intact. Existing matching excludes
  archived findings; a later import may create a separate active finding. This
  increment adds no suppression, absence flag or individual imported archive.
- Purging a finding cascades to its observations, just as its workflow history.
  Purging an upload that owns that finding can therefore remove its observation
  history, including later occurrences. Independent canonical finding ownership
  and suppression retention remain PB-1.3 work, not a guarantee of PB-1.1.
- If a duplicate-only upload is purged while its finding survives, its scan link
  becomes null. Its immutable original import UUID, filename and payload remain.
  Organization deletion removes its observations. Observation payloads have the
  same data sensitivity as imported findings and increase retained DB storage.

The publisher reuses its matching index, now retaining canonical finding IDs in
the same dictionary rather than issuing a query for every occurrence. History
has a dedicated page index and foreign-key indexes for purge. It is not joined
into the normal Findings list, count or sort queries.

History COPY batches are bounded separately from pending existing-asset updates.
Repeated source rows retain one coalesced update per asset until the update
buffer limit or final flush; recording history does not force asset rewrites
for every history batch. Parents are inserted before dependent history, and the
whole publication still rolls back together on failure.

## Inspection and Chrome verification

1. Import a small findings file. On Findings, open its row's **Workflow** action.
2. At the bottom, select **Show source observations**. Check filename, row,
   source, recorded time and payload. Browser-local formatting applies to times.
3. Change workflow status/assignee with a rationale. Reimport the same file
   using Ask/Reimport when prompted; Skip intentionally creates no new import.
4. Reopen Workflow and source observations. A later occurrence should appear,
   while the saved workflow and its separate history remain unchanged.
5. Reimport a changed severity/description with the same existing matching key.
   The observation shows the new source payload; the canonical finding retains
   its existing payload. This is observation history, not reconciliation.
6. Existing/manual findings show no invented history. Imports processed before
   installation have no observations until imported again. Bulk workflow dialogs
   do not show per-finding source history.

The view loads only when expanded, lists 20 records at a time and offers
Newer/Older navigation. Closing it changes no data. API:
`GET /api/v1/orgs/{org_id}/findings/{finding_id}/observations?limit=20&before={observation_id}`.
The optional cursor must belong to that organization and finding. Ordering is
recorded time descending, then UUID descending, with seek pagination so newer
inserts do not shift an older page. All organization members can read; foreign
organization access follows existing membership/404 rules. No write route exists.

Local validation and activation status are recorded in
[Phase 4 validation](PHASE4_VALIDATION.md). Production rollout, capacity and hosted
CI for this new increment must not be inferred from earlier verification.
