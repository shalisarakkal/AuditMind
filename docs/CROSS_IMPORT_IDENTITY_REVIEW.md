# Cross-import identity review (PB-1.3, increment 3)

This increment compares a selected later native Nessus observation with an
earlier, currently reviewed observation. It supports an explicit independent
review of the same finding across uploads; it does not enable automatic import
matching, canonical merging, absence conclusions or suppression.

## Rules

- Both observations belong to this organization and retained, completed imports.
  Their findings and source/canonical assets must be active.
- The reference must come from a different, earlier import, ordered by recorded
  time. This is import order, not proof of the scanner's observation time.
- Only the reviewed native Nessus plugin/port/protocol mapping is supported.
  Generic files, generated profiles, changed/missing service identifiers and
  unsupported contract versions fail closed.
- The earlier decision supplies a proposed scanner namespace and canonical asset.
  It does not prove the later upload came from that scanner or host. The admin
  must independently confirm both and provide a reason.
- If the same native key points to separate finding UUIDs, show a canonical
  conflict. No merge, reassignment or carried mapping is allowed through this
  operation. Conflicting/revoked target reviews require independent review.
- An already current target with the same key is a no-op, not another decision.
- Preview is read-only. It returns a context token covering both observation IDs,
  finding IDs, decision versions and current source/target/tool/asset context.
  Saving recomputes the preview under existing organization write admission;
  changed context, retirement, revocation or another saved review returns 409.
- A successful save appends the target's own decision and Activity event in the
  same transaction, with the reference observation/version retained as provenance.
  Revoking the reference later does not revoke this independently approved target.
  Retiring their shared tool disables both, as before.

The operation loads two observations and a bounded number of related rows. It
does not scan the organization's inventory, search for implicit matches or add
work to the import publisher. Workflow, severity/details, original scan ownership,
archive state, scoring and historical reports are unchanged.

## Chrome verification

1. Upload a small native `.nessus` file. In Findings, open Workflow, then Show
   source observations. Review its identity binding using the scanner namespace
   and verified canonical host. Expand Observation ID and copy that UUID.
2. Upload a second version of that file (same native plugin/port/protocol and
   host; change the bytes or explicitly reimport according to duplicate settings).
3. Open the later observation and choose **Review against an earlier observation**.
   Paste the earlier observation UUID and click **Compare identity**.
4. Verify the scanner, canonical host, captured target host and native identifiers.
   Saving remains unavailable until a reason and independent confirmation exist.
5. **Save reviewed mapping**. Reopen Review identity binding to see the reference
   UUID/version. Confirm workflow/status/notes and finding counts did not change.
6. Change the reference input: the preview and confirmation must clear. Cancel
   comparison and reopen: the draft must be empty and no write must have occurred.
7. In two sessions, preview then revoke the reference or retire its tool before
   saving. The save must conflict and require a new comparison. Do not retry a
   stale/uncertain write blindly.
8. A different plugin/port/protocol must fail comparison. A matching identity on
   separate finding UUIDs must show a conflict and offer no save/merge action.

Organization admins can save. Members can read comparison results through the
API; auditors, viewers and platform read-only access cannot save mappings.

API: POST `.../findings/{finding}/observations/{observation}/identity-binding/compare`
with `source_observation_id`; POST the same prefix `/carry-forward` with the
reference UUID, preview `review_token`, `expected_version`, `confirm_mapping`
and `rationale`.

## Remaining implementation sequence

1. **Canonical conflict resolution:** explicit selection of survivor, review of
   both workflows and verification decisions, version/lifecycle fences, atomic
   retained observation/history links and safe original-upload ownership. Never
   discard a conflicting decision merely because native identity matches.
2. **Canonical payload publication:** choose the latest successful eligible
   observation by an approved source-time policy; refresh severity/details while
   retaining reviewed workflow and historical reports. Test out-of-order imports,
   purged/archived sources and competing imports before activation.
3. **Not-observed review queue:** comparable complete scan declarations and
   reviewed scope exclusions are prerequisites. Absence is a separate review
   flag, never automatic Resolved, archive or score exclusion.
4. **Suppression/reappearance:** independent minimal tombstones, explicit restore
   and admin clearance, retention/purge and import/archive lock ordering.

PB-1.3 remains open until those lifecycle gates are implemented and verified.

## Local verification record

- Expanded PostgreSQL checkpoint: 119 tests passed across identity, bindings,
  scan snapshots and comparison. Final post-review identity/binding suite: 47
  passed in 84.63 seconds, including additional concurrency, changed-payload
  and mid-read review-creation cases. These checkpoints overlap; do not add them.
- Full frontend: 553 tests passed; lint and production builds passed.
- Focused real Chrome: seven checks passed, including actual native uploads,
  carry-forward/provenance, unchanged workflow, independent reference withdrawal,
  retirement, 320px layout and scoped Axe. No external AI usage or page errors.
- Final full real Chrome regression: 95 checks passed. Artifacts:
  `temp/testing/finding-workflow/phase3_browser_f4861e3e839c`.
  Focused artifacts: `temp/testing/finding-workflow/phase3_browser_24fd00b311b0`.
- Chrome initially reproduced overflow in the new comparison fieldset with a
  long scanner name/UUIDs. Minimum-width and intrinsic text wrapping were corrected;
  the focused real-browser reproduction now passes. The first browser attempt
  also had an isolated-build backend-address error; correcting the test build
  configuration required no application change.
- Review guards concurrent reference withdrawal and a target review appearing
  during read-only comparison. Current-context tokens and organization write
  admission prevent replay and competing saves from appending duplicate decisions.
- Bandit high-severity checks and tracked/new-file secret guards passed.
- Activated locally at existing migration 0046 after confirming all five work
  queues idle. Standard demo restart retained data; login returned HTTP 200 and
  both comparison/carry-forward routes are present in the running API.

These are local results, not hosted CI, production-scale acceptance or closure
of canonical merging/absence/suppression. The previous 1,653-test full backend
release is historical and is not claimed as a rerun of this increment.
Initial cross-import delivery: `dd46468`. A subsequent pre-push review reproduced
an asset edit after token validation but before the binding write: it returned
200 and captured the changed host context. A server-only expected-context fence
now rejects that save with 409 before appending a decision. The correction adds
no importer work, inventory scan or new database query. Expanded post-fix local
backend: 124 passed in 126.53 seconds. Focused real Chrome: seven checks passed
at `temp/testing/finding-workflow/phase3_browser_79ff36dd0716`.

Hosted CI is authoritative for each pushed commit in GitHub Actions; the final
push is not considered verified until all four jobs pass on its exact SHA.
