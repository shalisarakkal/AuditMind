# Imported-finding suppression and restore

PB-1.3 bounded suppression increment - 11 November 2026.

The supported end-to-end increment is implemented locally and under final
acceptance in [the release review](SUPPRESSION_RELEASE_REVIEW.md). Migration
0050 is active in the local application; final delivery CI is pending. The historical foundation
checkpoint below is superseded by that implementation. Generic sources,
automatic identity inheritance, consolidation and payload refresh remain outside
this bounded feature.

## Current implemented contract

An organization admin or auditor can suppress a retained native Nessus finding
only after every retained observation (1-1000) has a current independent tool and
canonical-asset identity review. Suppression is an explicit human visibility
decision; an absence-candidate pair is not a prerequisite or automatic authority.
Only an organization admin can clear it. Both actions require a current preview,
expected version, rationale, confirmation and an idempotent request identifier.

Lists, facets, cached counts, Dashboard and new risk/report calculations exclude
the suppressed payload. Workflow and old saved reports remain unchanged. An
all-suppressed scope is not a healthy score. Publication, history, invalidation
and activity share one transaction; stale or busy contexts reject safely.

The standing ledger survives source purge. A matching new native upload records
a **possible** reappearance but stays visible: it has no inherited trusted
binding. Applying the standing identity to a replacement needs a new explicit
review and cannot displace a retained prior target. That reapplication updates
the current source fingerprint while retaining previous decision contexts.
Clear never recreates purged payloads; archived sources require separate restore.
Source restore cannot silently delete previously reviewed payloads or restore a
cleared reviewed payload over an active duplicate.

The UI exposes a single-row **Suppress** action and a paged **Suppressed findings**
inspector. Manual Archive is separate. It guards busy submissions, preserves
rationale on conflict, and retries unknown outcomes using the identical request.
Closing after an unknown outcome does not undo a possibly completed decision.
[Verification steps](EVIDENCE_USER_VERIFICATION.md) and
[release evidence](SUPPRESSION_RELEASE_REVIEW.md) describe the delivered scope.

## Historical design proposal

The following proposal preceded implementation. The current contract above
supersedes proposal details such as requiring an absence pair, automatic trusted
matching and preventing dismissal after an unknown outcome. Those details are
not claims about the current product.

## User stories and boundaries

1. An organization auditor reviews an absent finding from two comparable complete
   scans, confirms its reviewed identity and records why it should be hidden.
   The explicit suppression hides that finding from active lists and new risk
   calculations. It does not mark it Resolved or approve verification evidence.
2. The same native finding is uploaded again. Its occurrence is recorded, but
   the standing suppression remains. A visible reappearance event invites review.
   A different port, plugin, tool or canonical asset does not inherit suppression.
3. An organization administrator clears suppression. An existing retained finding
   can become visible only if its lifecycle permits. A purged payload cannot be
   recovered; the administrator sees that distinction before proceeding.
4. Two reviewers act on the same item. One version wins; the other receives a
   conflict, retains the rationale and must reload. No last-write-wins decision.

First implementation is bounded to individually reviewed native Nessus identities
using `nessus-plugin-service-v1` and `finding-identity-v1`. Generic CSV/JSON,
profiles, unbound observations, ambiguous matches and canonical conflicts remain
ineligible. No bulk mutation, automatic absence disposition, canonical record
merge, source-payload refresh or remediation-status change in this increment.

## State and authorization

Keep visibility suppression independent of workflow status, queue review state
and upload/asset archive ownership. Use a dedicated active-list exclusion rather
than setting the existing `archived_at`/`archive_batch_id`: those fields belong to
retention jobs and could otherwise erase or restore the wrong decision.

| Action | Allowed role | Result |
| --- | --- | --- |
| Read suppression/history | Organization member with existing finding read access | No mutation |
| Suppress eligible finding | Organization admin or auditor | Required rationale, explicit confirmation, versioned active suppression |
| Clear suppression / request restore | Organization admin | Required rationale, explicit confirmation, versioned cleared suppression |
| Keep active / reopen absence review | Existing queue permissions | Review note only; never clears suppression |

Platform administration alone confers no organization mutation authority.
Clearing is admin-only under the approved retention policy. Existing workflow
permissions and administrator approval of scoring evidence stay separate.

| Situation after clear | Visible result |
| --- | --- |
| Retained finding and parents active; no identity conflict | Finding visible again, original workflow retained |
| Finding/asset/upload independently archived | Suppression cleared; still archived. Explain the separate restore requirement |
| Original finding purged | Suppression cleared; historical payload unavailable. Do not claim recovery or create a replacement from copied queue text |
| Multiple active records share reviewed identity | Block restore and require canonical review; never merge/delete records silently |

Clearing permits future eligible observations to be visible. It does not
retroactively publish previously hidden scanner payloads or restore parents.

## Persistence and identity validity

Propose a new indexed organization-scoped suppression registry with unique
`(org_id, identity_version, candidate_key)`, current state/version and immutable
identity material (tool namespace, canonical asset, normalized plugin/service,
mapping version). Store append-only decisions with actor label/optional actor
reference, UTC time, rationale, expected/resulting version and copied target
context. Runtime timestamps display in browser time zone. Database constraints
and tenant-scoped joins enforce ownership; uploaded claims never establish it.

Finding/scan/observation references are optional provenance, never cascading
owners of the registry. Their purge must retain the minimal identity, decision
and rationale needed to honor suppression. User deletion retains attribution
labels; organization deletion follows the organization deletion policy. Do not
retain full source documents, secrets or scanner payloads in the tombstone.

Only the server's current reviewed binding can match a registry entry. Revoked
or changed bindings cannot confer suppression to new observations; show the
identity review blocker instead. Existing explicit suppression remains attached
to its retained finding until an authorized clear, independent of binding
revocation. A mapping-version change requires explicit migration/review, not a
text-key fallback. Hostnames, descriptions, filenames and CVEs cannot transfer it.

## Import, scoring and retention contract

Resolve eligible keys in bounded sets during publication, with an indexed lookup
per batch, not per-row queries or an organization-wide identity scan. A new
observation does not inherit an administrator-reviewed binding automatically;
unsupported/unreviewed matches cannot be hidden. If first-increment imports cannot
safely establish an eligible identity, retain the observation as unbound/visible
for review rather than guessing. This eligibility limit must be visible in UI.

A confirmed matching suppressed identity records observation provenance and a
reappearance receipt without restoring visibility or changing user workflow.
Repeated identical requests/occurrences must not generate duplicate decisions.
Later review may attach a new record to the standing suppression only through
an explicit version-fenced action. Matching must not overwrite scanner fields,
notes, dates, assignee or previous evidence decisions.

Active lists, facets, exact-count caches, top issues and new dashboard/assessment
inputs exclude suppressed findings consistently. Recorded/source totals must
label suppressed counts separately; suppression is not a verified scoring
exclusion and is never evidence of control effectiveness. Include disposition
policy/provenance in new snapshots. Invalidate/coalesce existing list and
Dashboard refresh paths; old saved reports remain immutable. Clearing restores
risk contribution only under the existing scoring/evidence policy; a later
observation continues to invalidate stale scoring approval normally.

Upload/asset archive, restore, purge and duplicate handling must preserve active
suppression. Source-row retention must not clear it. Existing retention controls
continue to govern archived payloads, not suppression expiry. Restore must check
both independent lifecycle and suppression before making records active. Do not
reuse the archive service's duplicate-deletion path to implement reconciliation.

## Concurrency and request safety

Preview returns immutable target summary plus a server context token covering
current identity, finding lifecycle/workflow version, suppression version and
queue/declaration context when invoked from the absence queue. Submission
revalidates it; stale context returns 409 with no partial writes. Require request
idempotency scoped to organization/action/target; identical retry returns the
same receipt, conflicting reuse rejects. Rationale length/format use existing
bounded server validation, not client-only checks.

Use one documented lock order for publication and disposition: existing
organization publication lock, then deterministic target/identity row locks,
then decision writes. Check membership and versions inside the transaction.
Acquire absent registry identities safely using the unique constraint and a
transactional key fence. Never acquire the job-admission lock after the
publication lock. If publication is busy, fail promptly with retry guidance;
do not hold a blocking modal for an entire import. Workflow edits to unrelated
findings must retain their current concurrency and performance.

Visibility update, registry/version, append-only decision, durable activity and
invalidation request commit atomically. Worker failure/retry must not expose
half-applied state. Multi-record cases are blocked for this increment rather
than partially hidden. Document actual helper/lock ordering in implementation
and reproduce competing import/archive/restore cases on PostgreSQL.

## UI contract

Add explicit Suppress finding only for eligible imported rows and their review
details; show why unavailable for other sources. Keep manual Archive unchanged.
Inspection includes identity, source/scan context, current status and consequences.
Use application confirmation with frozen target, required rationale, neutral
Cancel and primary action per [UI conventions](UI_CONVENTIONS.md). Do not imply
that suppression is remediation or that clearing restores deleted data.

Provide a paged Suppressed findings view/filter with identity, retained/purged
payload state, last observed/reappearance, reviewer and decision history. Clear
suppression is admin-only and explains any remaining archive blocker. Disable
dismissal while submission outcome is unknown; preserve drafts on errors. No
native browser confirmation. Support keyboard, narrow screens and readable
loading/conflict states. Suppression reads must not start inventory scans.

## Ordered implementation and acceptance

1. Schema/tenant ledger and explicit suppress/clear APIs; migrations up/down,
   constraints, idempotency, independent decision history and source purge tests.
2. Integrate active queries/count caches, scoring and archive/restore lifecycle;
   verify query plans and bounded lookup counts against existing performance
   baselines. No unrelated import serialization or workflow regression.
3. Add reviewed-key matching/reappearance receipts with adversarial missing,
   revoked, ambiguous and different-tenant identities. Prove no new observation
   acquires trusted bindings automatically.
4. Add guarded single-target UI and paged management/history, then real Chrome
   role, conflict, retry, narrow-screen and keyboard walkthroughs.
5. Full backend/frontend/build/security acceptance and exact-SHA Linux CI;
   update user verification and release evidence before activation.

Required examples include same native key reimport; changed port/tool/asset;
Add a duplicate asset strategy; partial/failed scan; two concurrent admins;
workflow edited after preview; import held at publication; upload restore after
suppression; payload purge then admin clear; canonical conflict; evidence approval
expiry/revocation; empty/all-suppressed inventory; unchanged saved reports; list
counts/facets/top issues agreement; no cross-tenant reads or writes.

PB-1.3 remains open until this lifecycle and its tests are delivered. Safe record
consolidation and payload publication remain separately scoped work; neither is
implicitly enabled by this design. Pilot and SaaS-scale gates stay deferred.


## Foundation implementation

Historical checkpoint, superseded by the end-to-end release review above.

Implemented locally after the design, 11 November 2026. Migration 0050 prepares
`finding_suppressions` and `finding_suppression_decisions` with identity/owner,
version/state, request-id uniqueness and bounded rationale constraints. A
composite tenant foreign key prevents a decision referencing another
organization's registry. Source finding IDs are historical; source purge does
not cascade into the ledger. Actor deletion clears only the actor reference.
The registry owns its history, and organization deletion cascades both.

Read-only authenticated routes:

- `GET /api/v1/orgs/{org_id}/finding-suppressions`: state filter, limit 1-100,
  offset, deterministic newest-first page and `has_more`, without exact counts.
- `GET /api/v1/orgs/{org_id}/finding-suppressions/{id}/history`: limit 1-100,
  optional exclusive `before_version`, newest version first. Unknown or foreign
  registry IDs return 404 within the authorized organization.

Both require current organization membership and return `Cache-Control: no-store`.
Registry pages load only the columns returned; history does not load copied
context, actor IDs or request hashes. `mutations_available: false` explicitly
explains the missing lifecycle integration. No HTTP write endpoint or UI action
is registered, and no environment option can bypass that boundary.

The internal repository is transaction infrastructure, not authorization. A
future publisher must validate identity/role/context and take publication
admission before using it. It holds an organization/request-specific advisory
transaction lock (namespace 17), then the registry row lock; request reuse with
changed material conflicts. The unique request constraint is defense in depth.
Independent reviewers compare expected versions; retries return their original
receipt. A savepoint rolls back a failed decision and head update together;
the repository never commits the caller's transaction. Initial row creation and
first decision must share that outer transaction. No scanner query or matching,
archive operation, finding update, scoring calculation or activity claim is
performed by this repository.

Validation completed locally: 174 PostgreSQL regression tests passed in 346.25s,
covering the ledger, migrations and existing scan/identity/canonical/archive
behavior. Final review then reproduced a request-lock namespace collision with
the platform scoring lock using a forced zero key and a held independent session.
That reproducer failed with a lock timeout before correction. The ledger now
uses dedicated namespace 17; all 25 ledger/migration tests passed after correction
in 45.39s, including the collision reproducer and real independent writers.
These runs overlap; do not add their counts. This is targeted acceptance, not a
new full-backend, frontend, Chrome or hosted-CI run.

High-severity Bandit, dependency consistency, changed-file secret patterns,
Python syntax, document links and whitespace checks pass. Tests ran against
private disposable PostgreSQL instances and removed their databases/stopped
their servers. No migration was applied to the normal application, no UI or
setting was enabled, and no commit/push was made for this foundation.
Next implementation work: production identity/context admission and atomic
visibility/invalidation publisher, followed by scoring/archive/restore and
reappearance integration. Only then expose guarded write APIs and UI. This
foundation does not close the suppress/clear API acceptance criterion or PB-1.3.
