# Stage B publication storage

Reviewed application source `2751c3b`, 14 November 2026. Follows the
read-only preview foundation (`531d8e9`, hosted Linux verified).
This is reserved storage, not an enabled publication service. Existing preview
behavior and scanner fields are unchanged. No normal database activation has
been performed.

Migration 0056 adds four empty tables without modifying Findings columns or
rebuilding existing inventory indexes:

| Table | Purpose and retention |
| --- | --- |
| observation_publication_decisions | Minimal receipt: target/source UUIDs, request and payload hashes, mapping, operation/version, rationale and actor. Survives finding/source purge; organization purge removes it. No full scanner JSON or before/after text. |
| observation_publication_snapshots | Full before/after payloads tied to the exact receipt/target; deleting either the owning finding or that snapshot's supplying scan removes the payload. |
| observation_publication_states | One current generation per organization/finding; composite foreign key prevents pointing at another target or decision version. Retained after finding purge; a row alone never authorizes publication or undo. |
| observation_publication_dependencies | Indexed resource UUIDs per decision for future targeted lifecycle guards; no cascading resource links that would erase audit references. |

Organization-scoped request and finding/version uniqueness are enforced in the
database. The snapshot role is unique per decision. Receipts accept only Publish
or Undo operations and require a nonblank rationale of at most 2,000 characters.
Actor deletion clears the actor UUID while preserving its recorded label.

Downgrade refuses to discard any retained receipt, even after undo. A reviewed
history-export and rollback procedure must precede removal. Empty storage can be
downgraded. The migration imports no application models and does not seed rows.

The schema does not replace authorized transaction admission. The forthcoming
writer must validate tenant ownership of every source/target, freeze the full
dependency set, lock/revalidate the current generation and feature-setting
version, enforce payload limits/hashes and permit only one active publication.
Snapshot deletion must cause Undo to refuse, never reconstruct purged data.

Still required before enabling writes: default-off organization opt-in; fresh
authorization and idempotent atomic Publish/Undo; proof/source hash integration;
list/count/Dashboard/evidence invalidation; lifecycle admission/worker guards and
restore-cleanup protection; provenance in consumers; guarded UI and Chrome
verification. Saved reports remain immutable. Deferred manual acceptance stays
pending.

## Review and verification

The review reproduced three cross-tenant live-owner violations before the fix.
Snapshot inserts and owner changes now require live, same-organization Finding
and Scan owners. This invoker-rights guard performs primary-key probes only on
publication snapshots; it does not add an observation-import query. It is
installed consistently by migration and test metadata creation. No Finding
columns, active indexes or existing source/proof hashes are changed.

Actor deletion has a supporting receipt index and preserves the recorded label.
The unique organization/finding/version index also serves ordered history; a
redundant standalone history index was removed. Source-purge and exact-generation
constraints, organization-cascade retention and downgrade refusal were reviewed.
Authorized transaction admission remains mandatory before any writer is exposed.

Full backend: **1,981 passed in 2,180.81 seconds (36 minutes 20 seconds)**.
Frontend: **585 tests / 61 files passed**; lint and production build passed.
Installed Chrome: **106 checks passed**, including mobile/Axe, source lifecycle,
concurrent edits, selection safety and consolidation proof/recovery paths.
Final focused storage: **18 passed in 38.09 seconds**; this overlapping run also
strengthened the receipt-target test to use a real same-tenant alternative finding.
The migration upgrade/downgrade/drift checks passed. The 100,000-dependency probe
used its targeted resource index; one local warm execution was 0.151 ms, not
end-to-end latency or a SaaS scale claim.

High-severity Bandit, tracked-file secret checks, pip consistency and the backend
development dependency audit passed. Frontend production dependencies had zero
audit findings. The development audit reported seven moderate findings in the
ESLint/minimatch chain, with no high/critical findings; remediation remains a
separate compatibility-tested dependency increment, without a forced downgrade.

Local evidence (ignored artifacts): `temp/stageb-storage-full-backend.log`,
`temp/stageb-storage-final-integrity.log`,
`temp/stageb-storage-final-integrity-performance.log`,
`temp/stageb-storage-full-browser.log`, and Chrome artifacts under
`temp/testing/finding-workflow/phase3_browser_b85170641d33`.
The earlier 48/12-check storage runs are historical overlapping scopes, not
additional full suites. No manual customer acceptance is claimed.

Hosted Linux CI is the post-push delivery gate. The exact pushed-commit result
is linked in the delivery confirmation; the current workflow is available at
[main CI](https://github.com/shalisarakkal/AuditMind/actions/workflows/ci.yml?query=branch%3Amain).
No normal application restart or database activation was performed.
