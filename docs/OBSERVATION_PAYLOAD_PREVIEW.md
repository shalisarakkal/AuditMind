# Stage B: native observation payload contract and read-only preview

Status: first engineering increment implemented and locally verified. Stage B is
not complete. Publication, Undo, snapshots/decision ledgers, consumer invalidation
and a guarded publication UI remain unavailable. Stage A manual acceptance remains
TODO/deferred at the user's request; automated verification is separate.

## Captured mapping

New observations captured by the native Nessus importer, with source `nessus`
and no profile, receive `payload.mapping_version = nessus-observation-payload-v1`.
The server constructs this marker; uploaded generic JSON/CSV cannot opt in through
an input field. Generic/profile sources remain unversioned. Existing observations
are neither backfilled nor rewritten, and existing group proof/source hashes do
not change merely because this code is deployed. A legacy snapshot remains readable
but requires a new native import before this publication preview can accept it.

There is no column/index migration, per-row trigger, counter or additional import
query. The marker is captured inside the existing source-owned observation JSON.
It identifies a parser contract, not trusted identity, evidence approval or scanner
chronology. Current independent identity review is still mandatory.

The strict mapping has exactly these keys: mapping_version, domain, category,
severity, description, event_count, first_seen, last_seen, details and raw_data.
Raw data must have the native parser's exact field allowlist and scalar/list
shapes. Plugin/port/protocol must agree with retained source identity. Category,
description and numeric severity must agree with the native mapping. Plugin output
retains the native 4,000-character ceiling. Native aggregate event_count/details
are null in this version. Timestamp values must carry offsets and are normalized
to UTC; first_seen cannot follow last_seen. No workflow/client extras are accepted.

## API

POST `/api/v1/orgs/{org_id}/findings/{finding_id}/observations/{observation_id}/publication-preview`

Authenticated request body: `{}`. Additional request properties are forbidden.
The response has `Cache-Control: no-store`. Only an active actual organization
administrator can request a preview; auditor/viewer/platform-only access cannot.
Auth reads are released before the independent read-only repeatable-read snapshot,
so the route does not hold two connections from the same pool during preview.

The endpoint has no Publish/Apply/Undo counterpart. It returns
`publish_available: false` and `apply_available: false`. Its actor-bound
`review_token` is a snapshot fingerprint under `observation-publication-preview-v1`,
not a token accepted by any writer. Future write admission must use its own reviewed
publication contract and freshly validate authorization, context and version.

## Admission and bounded reads

- Finding and selected observation must belong to the requested organization;
  the observation must already belong to that exact finding.
- Require a live ordinary native Nessus finding, with no active consolidation,
  materialized suppression or standing identity suppression. Approved proof must
  be explicitly revoked, including expired approval; preview never revokes it.
- Require the selected observation's independently reviewed scanner/canonical
  asset binding to be current. Generic sources and unknown/unversioned mappings
  are rejected, not silently upgraded.
- Select latest server-recorded retained context using the existing
  `(org_id,finding_id,recorded_at,id)` index and a limit of two. A selected older
  observation or equal latest timestamps is rejected, even when newer context is
  unreviewed or incomplete. An older observation is not a fallback candidate.
- Validate original and selected source scans, source/canonical assets and asset
  creator uploads as live same-tenant retained owners. Both original/selected
  scans must be native; creators may be other supported scan kinds. At most 100
  creator links are supported for this review. Missing owners fail closed.
- Reject affected unfinished archive/restore/purge operations and pending/running
  imports. Preview takes no publication/admission locks or write transactions.
- Database-side size gates precede full payload fetches. Observation JSON and
  current scanner fields each have a 16 MiB limit. No full inventory payload scan
  or arbitrary historical observation sweep is needed.

## Field differences and provenance

The proposed replacement allowlist is severity, description, details, raw_data,
first_seen and last_seen. Domain/category/native identity must agree with current
classification. Event aggregates are outside this native scope. Finding UUID,
organization, original scan/asset ownership, created_at, workflow, assignments,
notes, deadlines and approval fields are never proposed as replacement values.

Each changed field includes bounded before/after summaries, complete-value SHA256,
byte sizes and truncation indicators. Payload hashes use canonical captured JSON;
upload file SHA256 values are separate provenance fields and token inputs. Null/removal differences are explicit. Text
and serialized JSON previews are limited to 2,000 characters each; full values
are hashed without replacing them by their displayed prefix. Identical effective
payloads return `no_op: true` with no changed fields and no write/version/event.
All text is untrusted source data and must be escaped by a later UI.

Provenance distinguishes the original owning upload/asset and finding creation
from the selected observation/import filename. Scanner observed time and server
recorded time are separate. Most recently recorded does not prove most recent
real-world scan, and no synthetic source time is filled in when absent.

Tokens bind actor/security context, exact target, mapping/native identity, current
identity review, before/observation hashes, retained observation metadata and
asset-creator links, workflow/proof versions, original
ownership and live source/asset/configuration context. Preview never materializes
scanner fields or captures permanent before/after publication snapshots.

## Verification and next gates

Focused tests cover real native reimports retaining original workflow/ownership,
read-only/no-op semantics, absent writer routes, request allowlisting, role/tenant
checks, stale identity, missing/archived sources, creator dependencies, pending
operations, approved proof, grouping/suppression, old/tied observations, oversized
payloads, null removals, full hashes, bounded responses and actor/context drift.
The database READ ONLY guard is tested against an injected accidental update.
The latest-row plan is checked with a large unrelated and target observation set.
The final 50 unit/integration checks passed in 75.96 seconds, including the
upload-content-hash drift check. The existing complete Chrome workflow passed
all 106 checks with new version-stamped imports. Initial broader coverage passed
128 cases with one over-specific plan fixture assertion; the corrected fixture
uses 100,000 target-history rows plus 100,000 unrelated observations and requires
the ordered observation index with no sequential scan or sort. Its latest-row
lookup measured 0.086 ms in one local warm run, not overall API latency or a SaaS
capacity claim. Review also reproduced two retained-metadata fingerprint gaps before the fix.
The final 52-check rerun passed after hashing observation metadata and creator
links; all three metadata drift cases (including creator-link changes) passed
separately. These scopes overlap. The complete backend regression passed all 1,960 tests in 2,078.39 seconds
(34 minutes 38 seconds). The additional metadata-drift cases were added after
that full run was collected; the final focused rerun passed 52 checks and the
three-case metadata rerun passed all three (overlapping scopes). High-severity
Bandit, changed/new-source secret-pattern and whitespace checks passed. Scopes overlap and
must not be added together.

Next: review source-owned publication snapshot/decision storage and a single-active
publication/version contract. Only then implement the atomic publish/undo service,
retention guards, indexed list/count/Dashboard/scoring/evidence invalidation and
safe UI. No current proof approval may be inherited or revived. Saved reports
remain immutable. Manual acceptance is not being represented as completed.

The running application has not been restarted for this increment. Normal data,
organization opt-ins and the pending manual acceptance task remain unchanged.
