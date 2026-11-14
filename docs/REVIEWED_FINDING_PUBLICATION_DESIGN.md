# Reviewed finding consolidation and payload publication

Current checkpoint (14 November): Stage A is locally activated through 0055
and remains default-off; manual acceptance is deferred. Stage B preview is
hosted-verified at 531d8e9, and reserved storage is committed in 2751c3b.
[Storage review](OBSERVATION_PUBLICATION_STORAGE.md) records full local checks.
Migration 0056 is not activated; payload publication and Undo remain unavailable.
The earlier design checkpoints below are historical, not current delivery status.

PB-1.3 staged design, 11 November 2026.

12 November checkpoint: the schema/read-only preview foundation is implemented
locally. The follow-up adds reserved membership/dependency schema and a bounded
read-only source manifest. Actual consolidation and publication remain unavailable. See
[foundation scope and validation](CONSOLIDATION_FOUNDATION_REVIEW.md).

This document defines the full proposed publication contract. The read-only
foundation described above is delivered; consolidation and payload publication
operations are not implemented or enabled. The delivered native
suppression/clear contract remains in
[IMPORTED_FINDING_SUPPRESSION.md](IMPORTED_FINDING_SUPPRESSION.md).
The application baseline is `e4c7488`; `950de8f` is documentation-only.

## Code findings that constrain the design

- [Canonical designation](CANONICAL_FINDING_REVIEW.md) preserves two independent
  records and does not merge counts or grant publication authority. Its saved
  context can become stale after workflow, observation or identity changes.
- [Finding](../backend/app/models/finding.py) retains source scan/asset foreign
  keys with cascading source ownership. Moving a finding or its observations
  between sources would change retention and provenance, not just presentation.
- [Observation snapshots](../backend/app/services/finding_observations.py) retain
  scanner fields independently of skipped duplicate finding updates. Uploaded
  identity claims are not trusted bindings. Payloads currently have no dedicated
  publication-schema version; identity mapping alone does not validate payloads.
- An observation's live scan link uses SET NULL, while its finding link cascades.
  A retained occurrence with a missing scan is not a publishable completed source.
  Keeping a later upload does not change the original finding's retention owner.
- [Scoring exclusions](../backend/app/services/status_scoring.py) currently count
  observations attached directly to each finding. That count alone cannot bind
  a future logical group or a new published payload to an approval.
- Archive duplicate cleanup already protects suppression history. Consolidation
  and publication history will need equivalent protection, including after undo.
- Active list predicates, partial indexes, count revisions, Dashboard capture,
  evidence source digests and report capture must all agree about visibility and
  effective fields. A UI-only merge or projection is insufficient.

## Recommended scope and sequence

| Stage | Proposed behavior | Excluded from that stage |
| --- | --- | --- |
| A: pair consolidation | Count one explicitly reviewed native Nessus pair under its designated canonical finding; keep both physical records and histories; support explicit undo | Payload replacement, automatic grouping, groups larger than two, merging edited alias workflows |
| B: source-payload publication | Publish a reviewed observation onto its own retained, non-consolidated finding; preserve source ownership and workflow; support guarded undo | Publication from another finding, publication onto an active consolidated pair, automatic latest-scan refresh |
| Later integration | Review how publication and active consolidated pairs compose | No implicit authorization from completing A or B |

Deliver A before B. Separate proposed organization opt-ins should default Off;
they must not reuse or change evidence-qualified or status-aware scoring settings.
Generic CSV/JSON, profiles and additional identity mappings remain excluded.
Implementation must not infer identity from filenames, descriptions, CVEs,
hostnames or IP similarity. No source payload or observation is physically moved.

## User stories

1. Two separately imported host aliases have independently reviewed bindings to
   the same scanner, canonical asset and native plugin/port/protocol. An admin
   selects a canonical finding using the existing designation flow, then reviews
   a new consolidation preview. On confirmation, the pair contributes one finding
   to active counts. Both UUIDs, original source ownership and histories remain.
2. The alias has its own assignment, notes or verification history. Consolidation
   is refused in stage A. The application identifies the blocker; it does not
   discard that work or choose which person's decisions should win.
3. The canonical workflow changes after consolidation. Undo restores the alias's
   independent visibility and original workflow; it preserves the canonical
   workflow as it now stands. Undo is not restoration of an old workflow snapshot.
4. A later native upload adds an observation to an existing finding while its
   displayed scanner payload remains unchanged. In stage B, an admin previews
   the source-field differences and publishes that exact observation. Severity
   and description may change; status, assignee, notes and deadlines do not.
5. Two admins act on an old preview. One operation wins. The second receives
   409, retains the rationale and must reload. An unknown response can be retried
   with the same request identifier without repeating the operation.

## Common authorization and context contract

Organization admins alone may consolidate, undo or publish in these first stages.
Members with existing read access may inspect history; platform administration
alone does not grant organization write authority. Rationale and explicit review
acknowledgment are required. Reads return no-store and do not mutate state.

Preview and write both validate organization/account/membership, native mapping
version, current independent bindings, scanner namespace, canonical asset,
completed retained source scans and active source/canonical assets. Include the
canonical asset even if it is not either finding's physical source asset.
Reject related pending archive/restore/purge work and unsupported identities.
Bound retained observation validation to at most 1,000 observations across the
selected targets; larger cases require a separately designed review path.

The preview token pins operation, target IDs, canonical designation receipt and
version, identity/binding versions, observation references/counts, scanner-field
hashes, workflow/proof versions, lifecycle, group/publication version and feature
setting version. Hash full retained text while returning bounded previews; do not
send complete raw payloads to the dialog. Writes accept IDs and a token, not an
arbitrary client-supplied replacement payload.

Use fresh authorization, job admission, a try-only organization publication lock
and sorted target-row locks in the existing lock order. Busy imports return a
prompt conflict. Allocate any new advisory-lock namespace after auditing existing
uses. Revalidate context inside the transaction before publication. Request IDs
are organization-scoped; identical authorized retries return their original
receipt, while changed request reuse conflicts. No stale-version bypass for a
request that was not previously recorded.

## Stage A: admission and ownership

Exactly two different retained findings must have current independently reviewed
matching native identities and a fresh selected canonical designation. The admin
does not choose a different canonical finding inside consolidation: change the
designation first if necessary. Reject overlap, chains, another retained matching
reviewed finding outside the pair, or an existing active group for the identity.

| Concern | First-stage rule |
| --- | --- |
| Scanner classification | Domain and severity must agree. Different values block consolidation; designation alone cannot choose the lower risk |
| Non-canonical workflow | Must be pristine: Open, workflow version 0, no assignee/deadlines/notes/history or verification decisions. Inspect actual fields and history, not only a version number |
| Canonical workflow | Preserve existing non-terminal workflow, owner, notes and dates. Resolved/False positive must be explicitly reopened before admission |
| Approved proof | Reject if either finding has a current approved scoring decision. Require explicit revocation through the existing review flow; do not revoke it silently |
| Suppression | Reject suppressed members or an active standing suppression for the reviewed identity. Consolidation is not suppression or clearance |
| Source ownership | Keep finding scan/asset IDs and every observation's finding/scan link unchanged |
| Alias actions | While consolidated, show its source/history and canonical link; block direct workflow, proof and suppression mutation on the alias |

The latest retained native observation on each member must also agree with its
displayed domain/severity. Unpublished classification differences, malformed
metadata or ambiguous latest-observation ordering block consolidation. An identity
review does not approve an older, lower-risk payload; resolve source publication
separately rather than hiding the discrepancy inside consolidation.

A dedicated versioned group owns the visibility relationship. Ordinary canonical
workflow edits do not invalidate the group merely because the older designation
receipt's workflow summary is now stale. The group has its own admission receipt
and validation contract. Revoke/reselect of its designation, affected identity
binding changes and tool retirement must require undo first in this first scope.

Keep a durable consolidation-history marker on both physical findings. Undo
removes only the active membership/exclusion and appends a receipt; it does not
erase the marker, group history, original source rows or either workflow history.

## Stage A: scoring and evidence prerequisites

Group-aware proof validation is a release prerequisite, not an optional follow-up.
The existing physical-finding observation count is insufficient. New proof must
bind the canonical finding, group generation/version, both members' retained
observation set and relevant source digests. Later observations, membership or
source changes make the exclusion ineligible until reviewed again.

Domain evidence observations that reference the alias remain historical references;
they are not redirected to the canonical UUID. Invalidate current evaluations and
source digests. Rebinding and renewed review are explicit, and an old Approved
label alone never establishes current coverage after consolidation/publication.

Do not transfer an alias approval or restore an earlier approval on undo. A
current group-bound approval must be explicitly revoked before undo. Subsequent
independent approvals require their own current source context. If group-aware
proof handling is incomplete, the new feature must remain unavailable; do not
silently run the existing exclusion predicate on grouped findings.

New imports do not inherit membership or trusted bindings. Alias findings are
excluded from legacy active import matching, so an alias reappearance can create
a visible independent finding. A normal legacy-key match on the visible canonical
finding may still append an observation; that must invalidate group-bound proof.
No third finding is silently added or hidden. Additional reviewed conflicts need
explicit undo and a new bounded review.

## Stage B: publication contract

Only ordinary, retained, non-consolidated native Nessus findings are eligible.
The selected observation must already belong to that finding, have a current
independent identity review and come from a completed active source scan.
Use a version-stamped, strict native payload mapping for newly captured eligible
observations. Older unversioned payloads remain readable; do not retroactively
declare arbitrary historical JSON publishable.

The preview must identify the most recently server-recorded retained observation
and reject a selected older one while newer unreviewed/incomplete source context
exists. Ambiguous equal timestamps do not establish chronology. Display scanner
observation time separately from server import time: latest ingestion does not
prove that a file represents the most recent real-world scan.

| Fields | Publication policy |
| --- | --- |
| Severity, description, details, raw_data, first_seen, last_seen | Strict native mapped replacement, including explicit null/removal differences; show a bounded before/after preview and full hashes |
| Domain, category and native identity key | Must agree with the current supported classification/identity in this first scope; a difference requires another design |
| Finding UUID, organization, source scan/asset ownership and created_at | Never rewritten |
| Workflow/status, version, assignment, notes, deadlines, review dates | Never copied from scanner fields or an older snapshot |
| Proof and qualification approval | Never inherited; current approved proof must be explicitly revoked before publication or undo |

Materialize the reviewed scanner fields on the canonical physical finding so
existing list/filter/sort/scoring indexes describe the same effective values.
Store original source ownership separately from the displayed publication's
observation/import reference and mapping version. APIs, UI and new exports must
name that distinction; the original upload must not be mislabeled as the source
of the new severity. No client can assign workflow fields through publication.
The preview must explain that the original upload still owns the finding:
publication is not a transfer of retention ownership to the newer upload.

Before/after full payload snapshots are source-owned retention data, not immortal
audit tombstones. Their ownership must cover both the canonical finding and the
scan supplying each snapshot, with appropriate cascading removal. The independent
decision ledger retains only bounded summaries, IDs and hashes after purge.
Capture the actual pre-publication scanner fields as the baseline; do not guess
an original observation if provenance cannot be established.

First scope permits one active publication per finding. Undo requires the exact
current publication and retained, unchanged source snapshots; otherwise refuse
with a recovery explanation. It restores only scanner fields/provenance, advances
the publication version and preserves current workflow. It never reactivates an
old proof. A different publication requires undo and a fresh review. An identical
effective payload with the current version is a no-op, not version/audit noise.

Proof/source-digest validation must include publication version and payload hash;
observation count can remain unchanged when publishing an already retained
observation. Include that dependency before allowing subsequent proof approval.

## Atomic consumers and retention

One transaction must publish the state/fields, versioned receipt, Activity event,
list/count revision and evidence/Dashboard invalidation. Failure rolls all of it
back. Dashboard capture must compare the new publication revision before commit
and refuse an older in-flight result. Read paths must not mix old counts and new
rows while a snapshot refresh is pending.

Integrate Findings lists/detail/search/facets/pagination, asset-linked findings,
Dashboard counts/top issues, risk/verification and evidence inputs, source
digests, and new report/AI-context/export capture. Saved reports remain immutable.
Show consolidated aliases separately from suppressed and verified exclusions;
verification exclusions are a subset of visible findings, not another copy of a
hidden-count deduction. Never turn zero assessable findings into a healthy 100.

For active groups/publications, affected source scan/asset archive or purge must
refuse at admission until the admin explicitly undoes the operation. Recheck in
the worker before mutation to catch previously queued jobs and races. Do not
partially archive a source and only then discover the new dependency. This first
scope deliberately avoids automatic canonical promotion or mass deconsolidation.
Document/proof retirement still invalidates scoring under its existing policy.
Record indexed dependencies on every source scan/asset in the reviewed operation,
including scans referenced by its captured observations and any separate canonical
asset. Checking only the two Finding.scan_id values would miss retained evidence
with different source ownership. New proof approval must likewise bind all of its
current source dependencies; a live scan link becoming null invalidates it.

After undo, normal source lifecycle operations resume. Restore duplicate cleanup
must protect consolidation/publication history even when workflow version is 0;
it must refuse reviewed conflicts instead of deleting or merging payloads.
Restoring an unrelated source never silently joins an active group. Source purge
may remove original full histories under retention, but minimal operation receipts
survive; organization purge removes its records. No undo recreates purged data.

## Proposed storage and endpoints

These names are design proposals, not existing routes or a reserved migration.
Use the next available migration after 0050 when implementation is reviewed.

- Tenant-scoped group, current membership and append-only decision tables, with
  unique active identity/member constraints and non-cascading historical IDs.
- Source-owned publication snapshots plus an independent decision ledger,
  current publication pointer/version and sparse reviewed-history markers.
- Organization publication revision for atomic cache/evaluation capture.
- POST consolidation preview/apply/undo and payload preview/publish/undo; paged
  read/history endpoints. Writes require expected version, preview token,
  request UUID, rationale and explicit acknowledgment. Reads never apply changes.

Index tenant/native identity, member IDs, source/canonical asset, tool, source
scan and request/version history. Lifecycle dependency checks must be targeted
probes, not full inventory scans. Large snapshots load only for a selected target.
No identity backfill or per-import inventory sweep. Any active-index rebuild
requires a measured maintenance plan, backup, idle writers and drift checks;
do not promise zero-downtime migration on the current large local database.
Downgrade/code rollback requires explicit undo and retained-history export first.

## UI and acceptance gates

Use separate **Consolidate reviewed pair** and **Publish observation payload**
dialogs. Display source ownership, UUIDs, workflow/proof blockers and exact count
or field consequences. No implicit choice, mass action or combined destructive
step. Neutral Cancel/Close and primary action follow
[UI_CONVENTIONS.md](UI_CONVENTIONS.md). Freeze targets/dismissal during submission,
retain rationale after conflict and retry unknown outcomes with the same request.

Implementation acceptance must cover:

1. Two independent admins, stale previews, actor/role/org changes, concurrent
   import/workflow/identity edits, replay versus changed request reuse and rollback
   after injected Activity/invalidation failures.
2. Same native identity versus changed plugin/port/tool/asset, a third member,
   edited alias, different domain/severity, suppression and current proof blockers.
3. Atomic rows/counts/facets/seek pages, grouped proof digests, publication with
   unchanged observation count, concurrent Dashboard capture and saved reports.
4. Source/asset/canonical-asset/tool lifecycle admission and queued-worker races,
   undo followed by archive/restore, reviewed-history cleanup protection and purge.
5. Strict payload allowlist, null/removal previews, unversioned/malformed/oversized
   snapshots, older/tied import ordering, source-only undo and no approval revival.
6. Real isolated Chrome walkthroughs for roles, exact targets, busy/unknown/stale
   outcomes, history links, keyboard/mobile/Axe and visible counts/field changes.
7. Query-plan/batch-cost review, migration up/down/drift, relevant full regression
   suites and exact-tip Linux CI before delivery. No production/scale claim from
   small synthetic fixtures.

Next implementation target: stage A's schema/admission/preview and receipt
foundation, followed by the atomic visibility/proof/lifecycle integration and UI.
Do not expose enabled writes before all stage A consumers and guards are coherent.
