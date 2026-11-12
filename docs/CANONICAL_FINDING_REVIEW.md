# Reviewed canonical finding selection (PB-1.3)

This increment adds an explicit, reversible canonical designation for two
separate native Nessus findings whose identities have both been independently
reviewed. It preserves the two records and their independent histories. It is a
prerequisite for future consolidation, not an automatic merge or deduplication.
Finding totals, workflow, scoring decisions, source ownership and reports are
unchanged. The UI states this before confirmation.

The next [consolidation/publication proposal](REVIEWED_FINDING_PUBLICATION_DESIGN.md)
uses a fresh designation as one admission input to a separate operation. No new
consolidation or publication authority is added to this existing designation API.

## Review contract

1. Both observations must have current administrator-reviewed bindings to the
   same scanner namespace, canonical asset and native plugin/port/protocol key.
   A proposed or uploaded mapping alone is insufficient. The reference must be
   from an earlier import, following the existing cross-import contract.
2. Both findings, source/canonical assets and retained completed scans must be
   active. An affected pending archive/restore/purge operation blocks review.
3. The bounded preview displays each finding's description, severity, ownership,
   current workflow/version, latest rationale and verification note, recorded
   scoring-review decision/version, and latest retained observation reference.
   Links open the complete retained finding histories in a new tab.
4. No canonical choice is preselected. The organization admin selects one of the
   two findings, enters a reason and explicitly confirms reviewing both histories.
   Changing the choice clears confirmation. Preview alone writes nothing.
5. Save requires the exact preview token and latest pair version. The token pins
   identity reviews, both finding summaries/workflow/verification versions and
   latest-observation references. Context changes reject the save with HTTP 409;
   the editor retains the reason but requires a fresh preview/choice/confirmation.
6. Writes use organization mutation admission and sorted finding locks. A final
   context check rejects edits made during preparation. Two competing admins
   produce one successful decision and one conflict, never two first versions.
7. A finding or native identity key cannot participate in another recorded
   selected pair, including a stale pair. Revoke that selection first. Disjoint
   pairs cannot designate competing canonical findings for the same native key.
   Latest decisions are checked across all historical contexts so a superseded
   scanner decision is not mistaken for an active selection. Unknown legacy
   identities fail closed until explicitly reviewed/revoked. Chains and groups
   of three or more findings are not inferred or transitively reconciled.

## History, invalidation and retention

Migration 0047 adds `finding_canonical_decisions`; migration 0048 indexes its
captured native identity key for cross-pair conflict checks. Neither migration
rewrites the captured decisions or scans inventory. No inventory backfill or
publisher rewrite is performed. Each selection/re-review/revocation appends a
versioned receipt with actor label, reason and captured summaries, and an Activity
event in the same transaction. Neither source finding nor its observation,
workflow or scoring-verification history is moved, overwritten or deleted.

The saved selection is current only if its preview context still matches. New
observations, workflow/verification edits, identity re-review/revocation, tool or
asset changes, and lifecycle changes can make it stale. The history list shows
recorded decisions, not a claim of current eligibility. Reopen the pair preview
to check currency. Exact restoration of unchanged source context may make the
recorded selection current again; explicit revocation requires a new decision.

Historical finding and observation UUIDs are deliberately not cascading live
foreign keys. Source purge can remove original payloads and full histories under
the existing retention rules, but the captured review receipt survives until the
organization is purged. Receipts contain bounded description previews and latest
notes/decisions, not complete copies of uploaded files or every history entry.
An admin can revoke a retained receipt even after its source rows were purged.
Organization deletion removes its receipts. Actor deletion retains the recorded
actor label and clears only its live user reference.

This record grants no scoring exclusion, approval inheritance, absence conclusion,
suppression, canonical payload publication or automatic import-matching authority.
The other finding remains independently counted and actionable.

## Chrome verification

Use a small native Nessus fixture and a synthetic organization first.

Example files: [baseline](examples/canonical-baseline.nessus) followed by
[alias](examples/canonical-alias.nessus). These are synthetic native-format
examples, not real scanner results. They deliberately create separate imported
hosts and findings. In a disposable test organization, register a new synthetic
scanner namespace and use the primary host's captured asset UUID as the explicit
canonical asset for both observations. This mapping is only the fictional test
story; do not infer such equivalence for real hosts from similar names or IPs.

1. Import two files that produce separate finding UUIDs for the same native
   plugin/port/protocol (for example, different imported host aliases).
2. Independently review each observation's identity under the same scanner and
   explicitly verified canonical asset UUID. Do not rely on hostname similarity.
3. Give the findings different workflow notes/statuses, then open the later
   finding's Workflow -> Show source observations -> Review against an earlier
   observation. Paste the earlier observation UUID and Compare identity.
4. Choose **Review canonical selection**. Verify both workflow versions, latest
   notes and recorded scoring reviews. **Cancel**/Escape closes only this dialog
   and makes no write. No radio choice should be preselected.
5. Choose a canonical finding, enter the reason and confirm. **Save canonical
   selection** records the designation. Counts, statuses, notes and scoring
   approvals must remain unchanged. Submission blocks dismissal until it finishes.
6. Open **Show canonical selection history** in either finding's Workflow. The
   receipt must name the chosen finding and reviewer and retain the captured
   review. Only the latest selected version offers **Revoke canonical selection**.
   Revocation requires a reason and appends a new version without changing either
   finding. Earlier receipts remain visible on the paged history.
7. In two admin sessions, preview the same pair and save in both. The second save
   must conflict. Reload must clear choice/confirmation while retaining the reason.
   Repeat with a workflow/verification edit or new import between preview/save.
8. Archive an affected source upload: its pair preview must be unavailable.
   Restore unchanged sources: recheck the preview. Purge an archived source:
   its original history follows normal retention; the review receipt remains.
9. Check narrow/mobile width, keyboard focus, Escape and independent dialog
   dismissal. Viewer/auditor/platform read-only users cannot save or revoke;
   another organization cannot read or mutate the receipts.

## API and performance

- POST `.../identity-binding/canonical/preview` with the reference observation UUID.
- POST `.../identity-binding/canonical` with canonical finding UUID, preview token,
  expected pair version, reason and `confirm_histories`.
- GET `/orgs/{org}/findings/{finding}/canonical-decisions?offset=0`: 20 receipts
  per page, including latest-version metadata. Historical UUIDs work after purge.
- POST `/orgs/{org}/canonical-decisions/{decision}/revoke`: expected version/reason.

Previews query only the selected two findings and bounded related records. Latest
observation reads use existing ordered indexes; raw/details payloads are deferred.
The pair-version uniqueness index supports latest decisions; the captured-key
expression index bounds cross-pair identity lookups. Both historical
finding IDs and actor deletion paths are indexed. No per-import/per-row overhead,
inventory-wide candidate search or Dashboard recomputation is introduced.

## Verification status

The full post-fix backend suite passed **1,710 tests in 1,578.76 seconds** with
`--require-postgres -W error`; this includes migration tests and the import
publication concurrency regression. The earlier backend suite passed 1,709 tests
before this final fix. Full frontend checkpoint: **560 passed**, with lint/build passing. The full isolated installed
Chrome workflow passed **98 checks**, including real synthetic Nessus imports,
canonical selection/revocation, competing-pair rejection, 320px layout and Axe.
There were no browser page errors or AI usage. Artifacts:
`temp/testing/finding-workflow/phase3_browser_5eec4455ec7f`.

The initial backend run was interrupted at 38% to fix a confirmed disjoint-pair
conflict. That run is superseded; the 1,709-test run is the corrected final
result. The browser regression reproduced and verified fixes for a former
assignee label and the competing canonical-pair guard. The conflicting prior
receipt can be reviewed/revoked even after source purge.

Final code review also reproduced a race where an import could publish a newer
observation after the canonical save's final context check. The new regression
fails without the fix and passes with the organization lock held through the
receipt commit. The final backend run includes the regression and passes. The
Chrome checkpoint predates this backend-only concurrency fix; hosted exact-SHA
CI passed all four jobs on `f31bb25`
([run 60](https://github.com/shalisarakkal/AuditMind/actions/runs/42492464513)).

Local activation is verified: the demo schema was already at migration 0048.
Idempotent preparation found no new upgrade operations or schema drift; the
existing demo was retained. The API health check and canonical OpenAPI routes
are available, the one-slot worker is running, and all six tracked queues were
idle. No restart or data change was needed. Exact-SHA hosted CI passed all four
jobs after this local activation check. No production deployment or complete
canonical consolidation is claimed.

Next implementation gates remain physical/logical consolidation semantics,
latest-source payload publication, not-observed review and independent suppression
lifecycle. See [reconciliation design](FINDING_RECONCILIATION_DESIGN.md).

## 12 November 2026: PB-1.3 read-only foundation

Migration `0051` adds retained consolidation/decision ledgers and bounded read APIs.
An administrator-only preview validates current pair prerequisites in a read-only
snapshot. No consolidation writes, visibility changes or new UI actions are enabled.
Current membership/dependencies, proof, lifecycle and consumer integration remain
pending before publication. Validation and API details: [foundation review](CONSOLIDATION_FOUNDATION_REVIEW.md).
