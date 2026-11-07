# Status-aware current-risk scoring

Product Phase 4, PB-4.4. Policy approval: 6 November 2026.

The approved policy is enabled by default at Platform level. Each organization
can inherit that default or explicitly choose On or Off. This is separate from
the existing evidence-qualified scoring setting, whose coverage gate remains
unchanged. Removing the override controls is a later rollout decision.

| Workflow status | Risk contribution |
| --- | --- |
| Open | Full |
| Accepted risk | Full |
| Mitigated | Full until a residual-risk method is separately approved |
| Resolved | Excluded only with current administrator-approved evidence |
| False positive | Excluded only with current administrator-approved evidence |

Workflow rationale and verification notes remain user assertions. Existing
notes are never migrated into approvals. Source severity, recorded inventory
totals and previously saved reports are preserved.

## Evidence review

Open an individual finding's Workflow action and expand **Scoring evidence
review**. Organization admins and auditors can submit an HTTPS evidence/ticket
reference or `document:<current organization document version UUID>`, observation
time and rationale. The server never fetches external references. An organization
admin must review the actual evidence before approving it. Review of one's own
submission requires an explicit acknowledgment, recorded in the decision history.
Platform administration alone grants no organization review permission.

Observations must be within the last 90 days. Approval requires a future expiry
within 90 days of both observation and review. Pending submissions may be approved
or rejected; approved decisions may be revoked. Review decisions are retained as
an append-only application ledger with reviewer, reference, time, rationale and
source binding. This ledger follows finding retention and is not a legal WORM
archive. Concurrent edits require reload rather than silent overwrite.

Approval loses scoring eligibility on expiry, revocation, a later workflow
status change, an additional imported observation, or retirement/replacement/purge
of a bound document version. A late-committing observation invalidates approval
even when its recorded timestamp is earlier. Non-status assignment/date/note edits
do not by themselves invalidate approval. New scanner observations do not silently
change the user's workflow status; the finding instead contributes risk again.

## Dashboard and saved assessments

Dashboard defaults to the **Findings-based** tab, showing the resilience baseline,
per-domain baselines and severity totals. Top issues and recent uploads are shared
between views. The **Inventory and finding risk** summary appears alongside each
tab's assessment, including when evidence-based scoring is disabled. It presents
the same recorded totals, severities, current-risk counts and verified exclusions;
these counts never establish qualified evidence coverage. Top issues appear
below both tabs as known finding risks rather than evidence-only
results. The **Evidence-based** tab
shows the separately gated assessment, domain scores, evidence coverage and
unavailable/stale evidence reasons. If evidence-qualified scoring is disabled,
that tab explains the setting and links to Settings; it does not enable it.
Known findings still produce their risk baseline when evidence qualification is
enabled but unavailable. Switching tabs changes only the view, makes no scoring
mutation and starts no evaluation. Keyboard arrows/Home/End select tabs. Refresh
keeps the selected view; switching organizations starts on Findings-based.
Organization identity, Dashboard refresh and snapshot time remain shared.
A numeric baseline is not proof of control effectiveness or sufficient
coverage; a baseline of 100 means no deductions in the recorded finding data,
not that all controls were assessed. Empty inventory and all-excluded findings
retain an unavailable baseline. Neither setting is changed by this presentation.

Recorded finding totals remain visible alongside current-risk and exclusion
counts. Dashboard snapshots retain raw counts and recheck approval eligibility
and policy on read. When source inventory changed since capture, exclusions are
withheld until refresh. Stale filtered top issues require refresh rather than
being labeled as an empty inventory. Approved decisions and organization policy
changes request a coalesced background Dashboard refresh when snapshots are on.

Excluding every known finding does not establish control coverage or a healthy
score of 100. The findings-based Dashboard shows **Not assessed**. The separate
evidence-qualified mode continues to require its own coverage qualification.
Numeric risk-assessment and report generation refuse an all-excluded snapshot
with an explicit explanation instead of inventing a score. New saved assessments
capture policy version, effective settings and raw/risk/exclusion counts; existing
reports are not recalculated. Up to 100 exclusion decision IDs, finding IDs,
references and validity times are captured; provenance explicitly flags truncation
for larger sets. Full decisions follow the finding's evidence-ledger retention.
Report period filters still apply before scoring.

## Chrome verification

1. In Platform **Scoring settings**, confirm the default is On. In organization
   Settings, verify Inherit, Off and On save and reload correctly.
2. Resolve a synthetic finding with a verification note. Confirm the note alone
   does not reduce its risk contribution.
3. Expand **Scoring evidence review**, submit a reference and observation time,
   then approve as an organization admin with review acknowledgment and expiry.
4. Refresh Dashboard: recorded totals are unchanged; current-risk totals exclude
   the approved Resolved/False positive finding. Approved Mitigated stays counted.
5. Revoke approval or reopen the finding: its risk contribution returns. Another
   imported observation also invalidates the old exclusion.
6. Turn the organization policy Off: legacy full contributions return. Saved
   report snapshots retain their captured values and policy provenance.

Local activation uses migration 0045. Validation: 732 backend unit tests, 535
frontend tests, targeted PostgreSQL policy/migration/report/concurrency suites,
and 92 Chrome checks. Lint, production builds and high-severity Bandit pass.
PLAN.md tracks closeout; commit review and hosted Linux CI remain release gates.
