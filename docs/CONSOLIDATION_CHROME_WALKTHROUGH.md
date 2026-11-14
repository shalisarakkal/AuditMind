# Chrome verification: reviewed finding consolidation

**Acceptance status: TODO - deferred at the user's request.** The complete
manual user/pilot walkthrough has not been signed off. Do not infer completion
from the earlier partial navigation or from passing automated tests. No manual
action is required from the user now; retain this procedure for later acceptance.
Automated local/hosted Chrome and PostgreSQL verification passed separately.
Engineering may continue to the next bounded PB-1.3 increment; this deferral does
not close manual acceptance or authorize broader consolidation enablement.

Use this procedure for the activated Stage A feature. It is a synthetic acceptance
test, not an assertion that a real vulnerability was remediated. No terminal,
database edit or application restart is required.

## 1. Prepare an empty test organization

1. Open http://localhost:3000/login in Chrome. If using an old tab, press Ctrl+Shift+R.
2. Sign in with an account that is an actual administrator of the test organization.
   A platform-admin account with read-only organization access cannot perform these writes.
3. Select an empty/disposable organization. If it is not empty, record existing totals;
   all counts below describe just the two test findings, not unrelated inventory.
4. Use the repository files `docs/examples/consolidation-primary.nessus` and
   `docs/examples/consolidation-alias.nessus`. Do not use the older
   `canonical-baseline.nessus` / `canonical-alias.nessus` examples: their different
   severities are intentional and do not satisfy consolidation admission.
5. Open Settings -> Reviewed finding consolidation. Confirm it starts Off.
6. Check Allow reviewed native pair consolidation -> Save consolidation setting.
   Expect New pair consolidation: On. Do not change evidence-qualified scoring.
7. For the later scoring test, confirm Settings -> Status-aware scoring has an
   effective policy of On. This is a separate setting from consolidation.

## 2. Upload the examples in order

1. Findings -> Upload file -> choose `consolidation-primary.nessus`.
2. Confirm the detected source is Nessus. Click Upload (or Upload all ready files
   when using the queue). Wait until processing is completed.
3. Upload `consolidation-alias.nessus` separately, after the primary completes.
4. Expect two separate active findings, both High severity and the same domain.
   Both carry fictional native plugin 99999178, port 443, protocol tcp.
5. Identify the primary and alias by their source filenames under Workflow ->
   Show source observations. Their synthetic category/description also distinguish them.
6. Open each row's Finding ID and copy its UUID. Record the following references:

| Reference | Meaning | Where to find it |
|---|---|---|
| F1 | Primary finding UUID | Main Findings table -> primary row -> Finding column -> expand Finding ID |
| O1 | Primary observation UUID | Primary Workflow -> Show source observations -> Observation ID |
| A1 | Primary captured asset UUID | Primary observation -> Review identity binding -> Canonical asset UUID (initial default) |
| F2 | Alias finding UUID | Main Findings table -> alias row -> Finding column -> expand Finding ID |
| O2 | Alias observation UUID | Alias Workflow -> Show source observations -> Observation ID |

Finding ID is outside the workflow dialog, beneath the finding title in the
main Findings table. Close the workflow to copy F1/F2, then reopen it for O1/O2.

These UUIDs are different kinds of identifiers. In particular, do not put F1 or
O1 into the Canonical asset UUID field.

## 3. Independently review the primary identity

1. Open the primary row's Workflow -> Show source observations.
2. Confirm the filename is `consolidation-primary.nessus` and copy O1.
3. Click Review identity binding. Record the initial Canonical asset UUID as A1.
4. Enter Identity review reason: `Synthetic test: reviewed the fictional scanner and primary host.`
5. Expand Register a tool instance.
6. Enter Tool instance name: `Synthetic consolidation scanner - test 1` (use a unique name).
7. Click Register tool instance. Registration saves the tool immediately; it does
   not yet save the identity binding. Confirm this tool is selected.
8. Keep Canonical asset UUID equal to A1.
9. Check I verified the scanner instance and canonical asset for this observation.
10. Click Save identity binding. Expect a Current saved binding.
11. Close the workflow dialog without saving a workflow change.

## 4. Independently review the alias identity

1. Open the alias row's Workflow -> Show source observations.
2. Confirm its filename is `consolidation-alias.nessus` and record O2.
3. Click Review identity binding.
4. Choose the SAME registered scanner used in section 3. Do not register another tool.
5. Replace Canonical asset UUID with A1, copied from the primary. The alias initially
   defaults to its own different captured asset; leaving that value is not this test's mapping.
6. Enter Identity review reason: `Synthetic test: this fictional alias represents the same canonical host.`
7. Check scanner/asset verification -> Save identity binding.
8. Expect Current, the same tool and the same canonical asset A1 on both observations.
9. Keep the alias pristine: do not change its status, assignee, dates or workflow
   notes, and do not submit scoring evidence for it. Identity and canonical reviews are allowed.

For real customer data, only make such a mapping after independently verifying
that both observations represent the same scanner/host/service. Similar names/IPs
alone do not establish this.

## 5. Select the primary as canonical

1. While viewing the later alias's source observation, click Review against an earlier observation.
2. Paste O1 into Earlier observation UUID. This is the observation UUID, not F1 or A1.
3. Click Compare identity.
4. Expect matching native identity pointing to separate findings. This is the
   expected conflict for an explicit pair review, not a failed import.
5. Click Review canonical selection.
6. Verify both finding UUIDs, source ownership, workflows and recorded reviews.
   No radio choice should be preselected.
7. Select F1 as the canonical finding.
8. Enter Canonical selection reason: `Synthetic test: retain the primary record as canonical.`
9. Check the confirmation that both independent histories were reviewed.
10. Click Save canonical selection, then close the workflow dialog.
11. Expect BOTH findings to remain visible. Canonical designation alone does not
    consolidate, merge payloads or reduce counts.

## 6. Verify draft protection and Cancel

1. Open F1 -> Workflow -> Show consolidation review.
2. Expect Preview consolidation for <F1 UUID>.
3. In the main workflow's Add rationale or note field, type `Unsaved workflow test`.
   Expect the consolidation preview action to be disabled and a draft warning shown.
4. Clear that main workflow field completely. Do not save it. Preview should become available.
5. Click Preview consolidation for <F1 UUID>.
6. In Consolidate reviewed pair, verify F1 is canonical, F2 is the retained alias,
   and original source ownership names the expected imports/assets.
7. Cancel should initially have keyboard focus. Consolidate pair must remain
   disabled until both review rationale and acknowledgment are supplied.
8. Click Cancel. Close the workflow and confirm both findings remain visible.
   There must be no new Finding consolidated Activity receipt.

## 7. Apply and check retained history

1. Reopen F1 -> Workflow -> Show consolidation review -> Preview consolidation.
2. Enter Review rationale: `Synthetic test: reviewed both retained native records and source ownership.`
3. Read and check the acknowledgment, then click Consolidate pair once.
4. If submission lasts long enough to observe, dismissal/inputs must be locked.
5. Expect the dialogs to close and the Findings list to refresh.
6. In an otherwise empty test organization, expect ONE visible finding: F1. The
   hidden alias F2 is retained, not deleted. The two assets are not merged.
7. Open F1 -> Workflow -> Show consolidation review. Expect a Published pair,
   canonical link and F2 under Retained member source and workflow history.
8. Expand F2's retained history and source observations. The alias remains read-only.
9. Expand group decision history. Expect one apply decision with your actor/rationale.
10. Open Activity. Expect one Finding consolidated receipt for this apply, not
    one Activity entry overall (earlier identity reviews generated their own events).
11. Open Dashboard -> Refresh dashboard. Wait for completion and a newer Last updated
    timestamp. Expect the pair to contribute once to visible finding/risk inputs.
    Asset count remains two. Internal retained-record totals may still count both
    physical records; they are different from active/visible counts.
12. Evidence-based scores can still say Insufficient evidence / Not assessed.
    Consolidation does not approve domain evidence or establish control coverage.

## 8. Verify source protection and the Off switch

1. Close the workflow. Open Uploads -> the alias source -> Archive.
2. If confirmation is offered, confirm. Expect a clear active-consolidation blocker
   instructing you to undo first. The source and findings must not be archived.
3. Return to Settings, uncheck Allow reviewed native pair consolidation and save.
4. Expect the existing pair to remain published and its alias to remain hidden.
   Off prevents new consolidations; it is not Undo.
5. Return to F1 -> Workflow -> Show consolidation review. Preview undo consolidation
   must still be available. Leave the setting Off if no further apply is needed.

## 9. Verify group-scoped scoring approval

Use only the synthetic organization for the following fictional evidence entries.

1. Open F1's Workflow. Set New status to Resolved.
2. Enter Add rationale or note: `Synthetic retest of both retained members.`
3. Enter Add verification note: `Synthetic verification only; not real remediation evidence.`
4. Click Save workflow and reopen F1 -> Scoring evidence review.
5. Expect the scope to identify the entire pair: two findings and, for these fresh
   files, two observations. A verification note alone must not authorize exclusion.
6. Action -> Submit evidence. For this synthetic exercise enter:
   - Evidence reference: `https://example.com/synthetic-consolidation-retest`
   - Observed at: approximately one hour ago in your browser's local time.
   - Review rationale: `Synthetic evidence covering both retained members.`
7. Click Submit evidence. Expect Pending and full risk contribution retained.
8. Action -> Review evidence -> Decision: Approve.
9. Set Approval expires at to tomorrow (within 90 days of observation/review).
10. Check I reviewed the referenced evidence. If reviewing your own submission,
    also check the displayed self-review acknowledgment.
11. Enter a new Review rationale and click Save evidence decision.
12. Expect Approved and Current evidence qualifies for exclusion when status-aware
    scoring is On. The history must show the consolidated evidence scope.
13. Refresh Dashboard again. With effective status-aware scoring On, expect one
    verified exclusion and zero current-risk findings in this otherwise empty
    organization. The finding remains listed as Resolved. An all-excluded score
    may be Not assessed; it must not manufacture evidence coverage or a perfect score.
14. Open Show consolidation review -> Preview undo consolidation. Expect a blocker
    requiring explicit revocation of approved scoring evidence. Cancel the preview.

## 10. Revoke approval, Undo and check workflow preservation

1. In F1 -> Scoring evidence review choose Action -> Review evidence.
2. Expect Revoke the current approval. Enter Review rationale:
   `Synthetic test: revoke group approval before undo.`
3. Click Save evidence decision. Expect Revoked and full risk contribution retained.
4. Show consolidation review -> Preview undo consolidation.
5. Verify both exact member UUIDs and the consequences. Enter Review rationale:
   `Synthetic test: restore independent finding visibility.`
6. Check acknowledgment -> Undo consolidation.
7. Expect TWO visible findings again. F1 remains Resolved with its workflow notes;
   F2 remains Open with its original independent workflow.
8. Expect the group to show Undone, with both apply/undo receipts retained.
9. Refresh Dashboard. With approval revoked, both findings again contribute risk
   under the current full-risk policy. Old approval must not reactivate.
10. Archive the alias upload now; it should succeed. Restore it from Archived;
    expect both findings and their retained histories to return. Do not purge the
    examples if you want to continue using this pair for review.

## Optional: concurrency and reappearance

- Two admins: open an undo/apply preview, change the canonical finding from a second
  admin session, then submit the old preview. Expect a conflict, retained rationale,
  disabled stale submission and Reload and review current targets before retrying.
  Use two Chrome profiles or regular/incognito sessions for different accounts.
- Reappearance: in a separate fresh test run, while a group is active, explicitly
  reimport the alias file. If exact-duplicate policy is Skip, choose Ask/Reimport
  for the test organization first. Expect an independent new visible finding,
  not automatic membership or inherited approval. Changing only the filename
  does not change a file's hash.
- Canonical reimport: while a group has approved evidence, reimport the primary
  file and ensure an observation was actually added. The old approval must lose
  eligibility, while the canonical workflow stays unchanged. Explicit revocation
  is still required before Undo; later observations need their own identity review.
- Permission check: a viewer/auditor/platform-only account cannot enable the
  consolidation setting or apply/undo. Read-only retained history is allowed.
- UI: check 390px width with Chrome device toolbar, keyboard focus and Escape.
  Cancel before submission must not apply; Escape/Close during saving cannot
  imply cancellation of a submitted operation.

Lost committed-response retries and injected transactional rollback are covered
by automated real-Chrome/PostgreSQL regressions. Switching DevTools to Offline
before clicking Apply does not reproduce a committed response being lost.

## Expected results summary

For a fresh organization containing only these two examples:

| Checkpoint | Visible findings | Current-risk findings with status policy On | Group |
|---|---:|---:|---|
| After both imports | 2 | 2 | None |
| After identity/canonical review | 2 | 2 | Not published |
| After Cancel | 2 | 2 | Not published |
| After Apply, both Open | 1 | 1 | Published |
| After Resolved, before approval | 1 | 1 | Published |
| After approved group evidence | 1 | 0 | Published |
| After approval revocation | 1 | 1 | Published |
| After Undo | 2 | 2 | Undone |

Compare Dashboard numbers only after Refresh dashboard finishes. Do not include
optional reimports or archived sources in the core two-file counts.

If a step fails, record its section/step number, screenshot, test organization,
F1/F2/O1/O2 and the displayed error. Never include passwords or session tokens.
