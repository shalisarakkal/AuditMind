# Reviewed native pair consolidation

12 November 2026. Stage A of PB-1.3; local implementation under final verification.
The running application database has not been migrated or restarted for this
increment. The feature defaults **Off** for every organization. Completing this
increment does not close PB-1.3 or enable observation-payload publication.

## What changes

An actual organization administrator can explicitly publish one independently
reviewed native Nessus pair under its already designated canonical finding.
Both physical UUIDs, source ownership, observations and workflow histories remain.
The canonical record contributes once to lists, counts, Dashboard and new report
inputs. Alias sources/history remain readable; alias workflow/proof/suppression
and identity mutations are blocked. No source fields or workflow are copied.

Use organization **Settings ? Reviewed finding consolidation** to opt in. This
setting is separate from status-aware and evidence-qualified scoring. Turning it
Off prevents new applies, keeps existing pairs intact and still permits explicit
undo. A no-op setting save creates no version/event noise. Stale saves require
reload. Platform administration alone gives no organization write authority.

Apply and undo require a fresh actor-bound preview, expected version, request
UUID, rationale and acknowledgment. Admission takes try-only organization locks,
fresh account/membership checks and sorted target locks. Identical authorized
retries return their original receipt, including after undo or a setting change;
changed request reuse conflicts. A receipt describes the original operation,
not necessarily the current live group. Activity, visibility, metadata and
consumer invalidation commit together; injected failures roll back all effects.

The older `consolidation_transactions.publish()` stub stays unavailable and
accepts no flag-based bypass. Authorized operations are explicit routes in the
new publication service; private metadata staging is not a public writer.

## Evidence and scoring

A group approval binds its canonical finding, group version, both retained
member observation sets, current identity bindings, physical scanner fields,
source scans/assets/tool and current canonical designation. The existing
verification ledger's `attestation.group_context` records the contract, group
and member IDs, observation count and digest. No approval is inherited from an
individual finding, an alias note or an older group generation.

Only an actual organization admin approves. Auditors may submit evidence;
viewers cannot write. Existing evidence-review/self-review acknowledgment,
expiry, document and workflow-status rules remain. Open, Accepted risk and
Mitigated retain full risk. Only current approved Resolved/False positive
canonical findings can be excluded, once per visible pair. Retained aliases
are not verified exclusions. New report provenance includes group proof scope;
saved reports remain immutable and internal proof references stay out of prompts.

Either member's changed payload, added/removed observation, lost scan, changed
source/binding/tool/designation or group generation makes the approval ineligible.
Late commits with older recorded timestamps are still detected. Assignment and
note-only canonical edits preserve approval. Import-report dismissal and worker
progress are not source evidence changes. Digests use UTC internally regardless
of connection timezone; user-facing times retain browser-local display rules.

The current approval must be explicitly revoked before replacement submission
or undo, even after it expires. Undo never revives a physical or group approval.
The UI describes the entire pair's evidence scope before review and retains the
captured scope in history. Domain finding-source bindings and inventory digests
also include group source context; an alias source change cannot leave an older
canonical evidence binding current.

Proof checks support at most 1,000 retained observations across a pair. Aggregate
observation JSON text is limited to 16 MiB, and each hashed source/scanner value
is limited to 16 MiB. Larger or unavailable contexts fail closed: current risk
is retained and a separate review path is required. They are not truncated into
an approval. These are technical limits, not claims of complete control coverage.

## Lifecycle and reappearance

Indexed resource probes block source scan/asset archive, restore or purge while
a published group depends on it. Admission includes physical owners, observation
sources, any separate canonical asset and creator-upload dependencies. Workers
recheck before the first write, every chunk and final sweep, catching old queued
jobs. A blocked job fails without first changing inventory. Failed archive
batches do not permanently block recovery undo; actual queued/running jobs do.

Identity-binding changes, designation replacement/revocation and tool retirement
require undo first. A third native copy never automatically joins or disappears.
An alias reimport can create an independent visible finding; reviewing that same
identity requires undo before another binding is accepted. A canonical legacy-key
match can append an observation while retaining its workflow; the old group
approval immediately loses eligibility.

After undo, ordinary source lifecycle resumes. Cleanup protects history-marked
findings even at workflow version 0. Restore refuses an unrelated active legacy
payload conflict instead of deleting or merging reviewed history. Known members
of the same explicitly undone pair can return independently. Purge removes its
source-owned payloads/observations under normal retention; minimal group receipts
survive. Undo cannot recreate a purged member. Organization purge removes its
organization-owned ledger and settings.

## UI behavior

For one finding, open **Workflow ? Show consolidation review**. The panel shows
current/undone groups, retained member sources/workflow history and paged group
decisions. A current selected canonical designation can open **Preview
consolidation** when the organization opt-in is On. Unsupported, edited,
incomplete or conflicting pairs return a blocker instead of an apply option.

The modal names the exact pair and source counts. Neutral Cancel and filled cyan
primary actions follow the shared footer convention. Targets and dismissal are
locked during submission. A stale preview requires reload while preserving the
rationale. A network/server failure preserves the exact request UUID/body for
**Retry same request**. Closing an unknown outcome does not undo a committed
operation; the list reloads. After success the underlying workflow closes and
lists refresh, preventing further edits to a newly hidden alias.

## Chrome verification after activation

Use an isolated organization and actual organization admin. The existing
[consolidation primary](examples/consolidation-primary.nessus) and
[alias](examples/consolidation-alias.nessus) examples support the native review flow.
Generic CSV/JSON examples do not establish trusted native identities. The older
canonical-designation examples intentionally use different severities and are
not eligible for consolidation; use the matching-severity examples linked above.

1. Confirm the consolidation setting starts Off. Verify an auditor/viewer or
   platform-only account cannot enable it. Enable it as the organization admin.
2. Upload the two native examples. Independently bind both observations to the
   same real scanner instance/canonical asset, then explicitly designate a
   canonical finding through Source observations' cross-import review.
3. Keep the alias pristine. Open Workflow ? Show consolidation review ? Preview
   consolidation. Inspect both exact UUIDs, source ownership and consequences;
   Cancel should have initial focus. Rationale and acknowledgment are required.
4. Apply. Confirm one visible pair, both retained sources/history and a single
   Activity receipt. Alias workflow and source archive/identity mutations are
   refused until undo. Check mobile width, keyboard and screen-reader labels.
5. Resolve the canonical finding with a workflow note. It retains risk until a
   current group-scoped evidence submission is explicitly approved by an admin.
   Evidence scope/history must show two members and the observation count.
6. Add a later source occurrence: canonical append invalidates its exclusion;
   alias reappearance remains an independent visible finding. Nothing inherits
   membership or trusted identity automatically.
7. Preview undo while approval is still recorded, including expired approval:
   it must require explicit revocation. Revoke, preview again, and undo. Both
   retained members regain independent visibility where their sources are active;
   canonical workflow edits remain and old approvals stay inactive. A failed
   archive job must not prevent explicit revocation before recovery; queued or
   running jobs still block conflicting review operations.
8. Exercise two-admin stale previews and a lost committed response. Reload must
   preserve rationale; unknown retries must use the same request nonce. A second
   operation/Activity record must not appear for an identical retry.
9. After undo, archive/restore/purge a test source. History must not be silently
   deduplicated; receipts survive source purge without recreating source data.

## Storage and activation

`0053` remains the heavy visibility prerequisite (28 partial-index rebuilds).
`0054` adds the bounded SQL proof/hash functions and tenant/source-asset and organization/scan/finding
observation indexes. It does not add a fingerprint column to every finding or
per-row import counter triggers. `0055` adds versioned default-off organization
settings. Migrations and matching application code require coordinated
activation, backup, idle writers and a measured disk/time plan; the two source index
builds also use database resources. Do not hot-restart old code against a partly
migrated visibility schema. No normal-data activation occurred during tests.

Downgrade refuses removal of group settings while published pairs exist, removal
of proof support while current group approvals exist, and removal of visibility
history once revisions/history are retained. Revoke/undo and preserve audit
history; prefer a reviewed roll-forward recovery after publication.

## Validation status

Initial focused PostgreSQL runs passed: 22 publication/proof checks, 129 broader
archive/admission/foundation regressions and 35 source lifecycle/reappearance/
migration checks. Scopes overlap and are not additive. The initial existing
frontend suite passed 578 tests; dedicated new UI checks cover stale drafts,
submission freezing and identical unknown-response retries. Final runs follow.

A local warm-query check with 100,000 unrelated unapproved findings used the
approved-only finding index. Eligibility measured about 14.5 ms for two retained
observations and 203.4 ms for 1,000 observations with roughly 8 MiB retained text.
This is a bounded local query check, not a cold-cache or SaaS capacity claim.
The group digest is evaluated for approved candidates, not every ordinary finding.

Chrome uncovered and reproduced a network-status-0 retry bug; the dialog now
preserves its exact request for that outcome. The focused real Chrome walkthrough passed default-off settings, apply, mobile/Axe,
lost committed-response replay, source/alias guards, group proof scope, explicit
revocation, stale undo reload, retained rationale and workflow preservation.
The complete backend regression passed 1,903 tests. The final frontend suite
passed all 585 tests across 61 files. The complete Chrome walkthrough passed
106 checks; the final focused Chrome run also passed all seven checks after
workflow-draft protection and group-history paging refinements. Lint, the
high-severity Bandit gate, the expanded changed/new-source secret guard and
frozen migration SQL comparison passed. Additional PostgreSQL checks passed
for reapply after undo and paging while an active group is on a later history
page. The final 58-test PostgreSQL recovery/scoring/publication run passed
after reproducing and fixing failed-archive revocation: failed jobs permit
explicit revocation, while queued/running jobs remain guarded. This targeted
run covers the final recovery change made after the 1,903-test full-suite run.
Test scopes overlap and must not be added together. The preceding `bb07019` checkpoint passed all four
hosted Linux jobs in [run 43323043722](https://github.com/shalisarakkal/AuditMind/actions/runs/43323043722).
That result does not validate this new uncommitted increment.

Remaining PB-1.3 work includes Stage B observation-payload publication, additional
identity mappings, groups larger than two and any automatic reconciliation.


## Review closeout - 13 November 2026

Implementation and local verification are complete for this bounded Stage A
increment. Changes remain uncommitted and unpublished. The normal application
has not been migrated or restarted. Next release steps are scoped diff/check-in,
push and hosted Linux CI, followed by coordinated migration/activation and an
explicit organization opt-in. This does not close the remaining PB-1.3 scope.


## Hosted Linux follow-up - 13 November 2026

Commit `fd3cf10` is pushed. In run 43432914113, frontend and dependency/security
checks passed, but browser acceptance caught a 3-pixel Settings overflow at
390px with the large organization logo. The consolidation opt-in card now wraps
long text and gives its checkbox label a shrinkable text span. Browser regression
checks both 374px and 390px and reports overflowing elements on failure. The
full local Chrome rerun passed all 106 checks; lint and the isolated production
build passed. The follow-up commit requires its own green hosted run before database activation.
Normal data remains on 0052. The owner selected maintenance immediately after
CI passes; backup and migrations 0053 through 0055 must precede application
restart, with consolidation still off by default.


The narrower 374px hosted check also exposed existing Settings text overflow;
the page now permits word wrapping across all sections. Diagnostic bounds exclude
content intentionally clipped by a horizontal table scroller, so a future
failure identifies page overflow rather than normal wide-table contents.

The page-level wrapping follow-up passed the full 106-check local Chrome run,
isolated build and lint. The initial Linux backend job passed all 1,910 tests.
