# Stage B publication consumers and lifecycle guards

14 November 2026 private integration checkpoint after core `fceedd4`.
This work is not activated. There is no public Publish/Undo/settings writer
and no new GUI. Normal schema remains 0055; migrations 0056 through 0058 require
separate coordinated activation. Existing saved reports are immutable.

## Private transaction boundary

`publication_consumers._stage` uses the distinct internal receipt contract
`observation-publication-consumers-v1`. It wraps source materialization, snapshots,
receipt/current generation, Activity, consumer epochs and Dashboard invalidation
in the same outer savepoint. It never commits. The original core contract remains
separate: neither replaying a core receipt nor loading its generation can upgrade
it to this integration contract. Replays and effective no-ops add no effects.
Public service entry points still reject calls regardless of policy/client flags.

The private review token binds the selected contract. An integration failure,
including after epoch/Activity SQL, rolls back fields and receipt together.
The existing lock order, authorization, bounded waits, explicit approval revocation
and workflow/ownership preservation continue to apply.

## Consumers and proof

- Existing Finding statement triggers invalidate cached list counts and seek
  navigation in the same transaction as the source-field update. Reads continue
  to use the materialized fields; no per-finding payload join is added to counts.
- A separate monotonic organization publication revision and the existing evidence
  revision advance for each effective Publish or Undo. This publication epoch is
  included in Dashboard captures and organization inventory fingerprints.
- Saved Dashboard reads reject a mismatched epoch. A worker capturing an earlier
  snapshot cannot publish it across the epoch change; it returns the job to Pending.
- In-flight evidence jobs fail their existing revision fence and are Superseded.
- Finding evidence bindings and risk approval attestations retain the exact
  publication version, receipt ID and state, including after Undo. Returning to
  equal source fields does not revive an earlier submission, approval or inventory
  evaluation. Existing never-published sources keep their earlier binding format.
- Pending evidence whose generation changed must be resubmitted. Existing approved
  evidence must still be explicitly revoked before Publish/Undo; expiry alone does
  not authorize replacing it. A newly reviewed current-generation approval works.
- Missing or unsupported retained generation context fails closed. Policy switches
  do not manufacture evidence, and historical reports are not recalculated.

## Source lifecycle protection

Migration 0058 adds the consumer revision table and indexed source-guard functions.
Service checks extend existing consolidation admission hooks, including archive
admission and worker rechecks, tool retirement, identity binding/canonical review,
suppression and new consolidation admission. Only an actual consumer-contract
active publication has these lifecycle effects; reserved/core-only receipts are
not upgraded into lifecycle authority.

Database guards also cover bulk SQL/import updates of identity-relevant asset
fields, scan identity/availability, finding ownership/availability, tool records,
observation payloads, source bindings and creator relationships. The probe starts
from tenant/resource indexes and joins the exact active receipt. It also checks
current observation owners added after publication, not only the captured manifest.
New creator/binding changes cannot bypass protection through insertion.

Unchanged asset identity, unrelated metadata and worker progress/heartbeat updates
remain allowed. Guard triggers are restricted to relevant update columns; unchanged
identity returns before dependency queries. New unrelated imports and additional
observations are allowed; changing a protected source requires authorized Undo
first. This does not increase worker concurrency or change job scheduling.

After Undo, individual source retirement/purge can proceed. Source-owned full
snapshots are removed by existing foreign-key retention rules; minimal receipt
history remains. Purged data is never reconstructed. Organization purge continues
to own all its retained data. Account purge may clear the reviewer FK while
retaining immutable review material and the historical label; that exception
does not permit changing identity context, review labels or reviewer assignment. Restore duplicate cleanup excludes findings with
publication history and refuses conflicting reviewed restorations instead of
silently deleting them. Downgrade refuses retained integrated receipts/epochs,
including after Undo; a reviewed rollback/export procedure is required.

## Verification and remaining work

Latest focused integration verification: **31 checks passed in 73.90 seconds**.
A separate two-case performance run passed: 10,000 unchanged asset identity
updates took 1.985 seconds with zero dependency probes; 10,000 unrelated assets
were purged in 1.609 seconds while a publication was active. These are local
synthetic probes, not capacity/SaaS benchmarks. Compilation, high-severity Bandit
and tracked/new-file secret/whitespace guards passed. The expanded regression
run passed **283 tests in 648.07 seconds**. Existing browser regression passed
**106 checks**, with no AI calls or page errors; artifacts are under
`temp/testing/finding-workflow/phase3_browser_1667a108f54f`. These browser checks
cover existing screens and do not claim new Publish/Undo GUI acceptance.

The initial full run had 2,067 passing tests and one DDL-consistency failure:
source DDL was edited while that process retained its older imported module.
It is not accepted as a successful full run. The clean frozen-source rerun passed **2,070 tests in 2,320.79 seconds
(38 minutes 40 seconds)** on isolated PostgreSQL with warnings treated as errors.
No backend Python source/test file changed after that accepted run started. A table-specific shared-trigger bug was
reproduced in the disposable test database and fixed before acceptance. Review also separated creator links from unrelated
matched-asset links so unrelated uploads remain removable. One new
count-cache fixture assertion used High instead of its actual Medium severity;
the fixture was corrected. Neither run affected the normal application.

Check-in review reproduced an account-purge guard conflict: clearing only an
identity review's actor FK was incorrectly blocked. The narrow fix allows that
retention cleanup while keeping review material/labels immutable. Three negative
mutation checks passed. The follow-up publication/core/migration/identity/security
run passed **98 tests in 199.88 seconds**, plus **3 negative mutation tests**
in 6.95 seconds. Post-fix compilation, high-severity Bandit and secret/whitespace
checks passed. Exact-commit Linux CI repeats the full suite after push; the result
is recorded in the delivery confirmation. The 2,070-test full-suite and 106-browser results above precede
this narrow review fix and are not presented as reruns of it.

Remaining before public enablement: bounded user-facing provenance/recovery,
default-off setting and guarded actions, unknown-outcome UX, Chrome verification,
final review, commit/push and exact-commit Linux CI, then coordinated activation.
History beyond the existing bounded review limits or missing source context still
requires explicit recovery design; guards do not guess identity or delete history.
Manual Stage A customer acceptance remains deferred at the user's request.
