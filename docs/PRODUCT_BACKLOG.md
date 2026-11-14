# AuditMind Product Backlog

Current checkpoint (14 November): Stage B reserved publication storage is committed in `2751c3b`; full local regression verification passed. Normal schema remains `0055`; migration `0056` is not activated. Publish/Undo and its UI remain unavailable. Stage A stays default-off and manual acceptance remains deferred. See [storage review](OBSERVATION_PUBLICATION_STORAGE.md) and [hosted CI](https://github.com/shalisarakkal/AuditMind/actions/workflows/ci.yml?query=branch%3Amain). Earlier dated entries are historical checkpoints.

## Next PB-1.3 design prepared - 11 November 2026

The [reviewed consolidation/publication design](REVIEWED_FINDING_PUBLICATION_DESIGN.md) is prepared for review, not implemented
or enabled. Recommended stage A is reversible native Nessus pair consolidation
with pristine-alias and explicit proof/lifecycle guards. Stage B separately
publishes a reviewed observation onto its own non-consolidated finding; group
publication remains later work. No physical source/history movement, automatic
matching, workflow overwrite or inherited approval is proposed.

First implementation target: stage A schema/admission/preview and receipt
foundation; writes remain unavailable until visibility, proof, lifecycle,
consumer invalidation and guarded UI are complete. No migration, app setting or
running data was changed by preparing this design.


## Current delivery - 11 November 2026

Committed application baseline: `e4c7488c1a0b40a99bc20efe60a6663fac7f62d3`.
All four hosted Linux jobs (backend, frontend, dependency/security and browser)
passed for both the suppression/retained-source delivery `f97a4fb` in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797)
and the draft-save correction `e4c7488` in [run 43144443993](https://github.com/shalisarakkal/AuditMind/actions/runs/43144443993).

- Migration 0050 is locally activated. Reviewed native Nessus suppression/clear,
  atomic list/count/Dashboard/risk invalidation, possible-reappearance receipts,
  source-purge retention and guarded UI are delivered.
- Retained-source conflicts are fixed: clear refuses additional retained payloads;
  restore checks reviewed identity as well as legacy duplicates, including aliases.
- Save draft is disabled without persisted draft/binding changes. Identical valid
  saves preserve version, timestamp, audit history and evidence revision. Stale
  versions and source validation still apply; first saves create version 1.
- Suppression acceptance: 120 expanded backend regressions, three final indexed
  cases, 576 frontend tests and 103 Chrome checks. Draft-save acceptance: 54 backend
  and 15 component tests, lint and production build. Scopes overlap; do not sum
  them or treat targeted results as full-suite totals. Full hosted jobs are green.

PB-1.3 remains partial: consolidation, source-payload publication, additional
reviewed mappings and automatic reconciliation are not delivered. Recommended
next work is a bounded consolidation/payload-publication design, then its reviewed
implementation; PB-1.4 asset ownership/context follows. Pilot/production, broader
evidence-qualified scoring and SaaS load gates retain their prior holds.
[Release evidence](SUPPRESSION_RELEASE_REVIEW.md) and
[verification steps](EVIDENCE_USER_VERIFICATION.md).

## Prior absence-review delivery - 11 November 2026

The durable absence-review queue is delivered on `main` through `60d957b`.
All four hosted Linux jobs passed for exact commit
`60d957b4f9f03383e797a26677e31fb60fce2077` in
[run 43045746714](https://github.com/shalisarakkal/AuditMind/actions/runs/43045746714): backend, frontend, dependency/security
and browser acceptance (including evidence/scoring and worker recovery).
Local acceptance: 1,723 backend tests, 567 frontend tests and 99 Chrome checks.
Migration 0049 was active at that checkpoint; current migration is 0050. CI uses preinstalled stable Chrome on Ubuntu
24.04; the earlier Chromium installer failure did not recur on this path.
This supersedes older pending/unmerged queue statements; dated checkpoints
remain historical. It does not approve a pilot, production deployment or SaaS load.

At that checkpoint, next was [imported-finding suppression and restore design](IMPORTED_FINDING_SUPPRESSION.md).
Suppression, restore, reappearance handling, consolidation and payload publication
are not delivered by the review queue. PB-1.3 remains open.


This backlog turns the [product roadmap](PRODUCT_ROADMAP.md) into candidate,
testable work items. It is grouped by product phase and ordered within each
phase. It is not a delivery commitment; confirm scope and release gates before
starting an item.

## Baseline: capabilities already present

Local follow-up (5 November): concurrent import/workflow saves and independent
workflow list invalidation are implemented and validated (migration 0042).
Activated locally with migration 0043 after the user-approved stalled import
abort on 6 November; uploader/admin Abort import is also available. See
[delivery plan](../PLAN.md) and [validation](PHASE4_VALIDATION.md).

Local cloud reimport performance correction (6 November): bounded bulk asset
updates, unchanged-payload write suppression and Abort foreign-key-lock handling
are active. The exact retained file reimported 500,000 existing assets in
213.084 seconds in an isolated test schema, with unchanged full payload checksum.
This is not a hosted scale result or a production-duration guarantee; see the
same validation record for limits. Delivered through `24a5f66`; all four hosted
Linux jobs passed in [run 42245252464](https://github.com/shalisarakkal/AuditMind/actions/runs/42245252464).
The subsequent PB-4.4 scoring increment has its own release checks below.

Avoid rebuilding these as new features. Extend them only where an item below
identifies a specific gap:

- Multi-organization roles, assets/findings imports, upload reports, and
  asynchronous report jobs.
- Finding workflow status, assignee, due date, accepted-risk review date,
  rationale/verification notes, optimistic version checks, history, and bulk
  workflow updates.
- Evidence-captured report snapshots, citations/provenance, output/reference
  validation, report downloads, and optional AI assessment distinct from
  deterministic scoring.
- Optional reviewed-coverage qualification and stored Dashboard snapshots.

These features and their constraints are documented in
[Phase 3 closure](PHASE3_CLOSURE.md), [evidence coverage profiles](EVIDENCE_COVERAGE_PROFILES.md),
and [finding workflow code](../backend/app/services/finding_workflow.py).
The remaining work below is additive; validate the current implementation
before changing contracts.

## Phase 0 — Acceptance and pilot readiness

### PB-0.1 — Reconcile release gates into one current checklist

**Status, 8 November:** Complete as checklist/ownership reconciliation. The
project owner/user confirmed ownership of release approval and of engineering,
operations and security. Operational release gates remain open; this is not release
approval. [Current gate checklist](RELEASE_READINESS.md#baseline-and-operational-gates).

**Priority:** P0 · **Depends on:** none

Review the current acceptance, operational, security, provider, and deployment
records. For each open gate, record an accountable owner, evidence required,
approval authority, status, and next action. Retire contradictory or historical
handoff text without erasing its audit context.

**Acceptance criteria**

- Every open release gate has an owner, test/evidence requirement, and explicit
  approval boundary.
- The checklist distinguishes local tests, hosted CI, pilot approval,
  production readiness, and live-inference approval.
- Documentation links to the authoritative latest evidence rather than
  implying old results cover later changes.

### PB-0.2 — Define a bounded pilot contract

**Status, 8 November:** User-deferred; not completed. This is the next
pilot-readiness decision, not an engineering defect or a request to enable a
customer deployment. The owner must first decide to resume it, then approve the
bounded contract and scope-dependent release gates in
[release readiness](RELEASE_READINESS.md#pb-02-pilot-readiness-contract-decisions-required-to-close-the-gate).

**Priority:** P0 · **Depends on:** PB-0.1

Before pilot code/configuration work, document the pilot objective and audience;
participant organizations/roles; target environment and access; approved sources
and data classification; retention, deletion and incident handling; included
workflows; exclusions and off-by-default capabilities; support and recovery
ownership; measurable success, stop and exit criteria; and required approvals.
Use explicit owner-approved values, not assumptions from synthetic/local tests.
Keep current worker limits and defaults unless separately approved and measured.

**Acceptance criteria**

- The versioned pilot contract names its audience, purpose, target, allowed data,
  included workflows, exclusions, support contact, success/stop criteria and
  approvers; undecided items block closure.
- Each included workflow maps to an implemented path, exact-SHA verification
  evidence, and known limitations; any missing feature is excluded rather than
  implied.
- Operators can identify required consent, settings and approvals; live AI,
  broader evidence-qualified scoring, SaaS/parallel scale and not-yet-built
  reconciliation behaviors stay excluded unless separately approved.
- Applicable deployment, security, privacy/data-handling, monitoring,
  backup/recovery and workload gates have evidence and explicit acceptance
  before a real deployment or customer data is used.
- No concurrency, SaaS capacity, certification or production-readiness claim is
  made without corresponding evidence and approval.

**To close this gate:** obtain owner decisions for every contract field and
record approval; prepare the scope-to-evidence matrix; complete applicable
release gates for the chosen target; then record a dated go/no-go. This closes
pilot readiness only for that documented scope, not production readiness.

### PB-0.3 — Verify recovery and operational procedures for the pilot

**Status, 5 November:** Completed for the authorized local synthetic rehearsal:
ten operational checks and five focused unit checks pass. Intended-deployment
recovery acceptance remains open. [Evidence and limits](RECOVERY_REHEARSAL.md).

**Priority:** P0 · **Depends on:** PB-0.1

Exercise the documented backup/restore and worker recovery procedures in an
approved non-production environment. Record data-loss and recovery-time
observations; do not infer targets that have not been approved.

**Acceptance criteria**

- A restore rehearsal completes from documented backup artifacts.
- Recovery steps, failures, measured duration, and unresolved gaps are recorded.
- The rehearsal does not modify ordinary/demo data or enable production actions.

## Phase 1 — Evidence provenance and control context

### PB-1.1 — Add per-finding source observation history

**Status, 5 November:** Complete locally and activated at migration 0040;
validation/activation closeout is
recorded in [Phase 4 validation](PHASE4_VALIDATION.md). Append-only import
occurrences and a read-only, paged source-history view preserve current matching
and workflow behavior. No historical backfill or reconciliation eligibility is
inferred. Chrome passed 87 checks and the final full frontend suite passed 522 tests.
Final pre-commit review included 1,528 passing backend tests with PostgreSQL
required and warnings as errors. Delivered in `ec5f7b2`, `56bce49`, `376342c`;
all four hosted Linux jobs passed for `376342c` in
[run 42113315252](https://github.com/shalisarakkal/AuditMind/actions/runs/42113315252).
[Contract and verification](FINDING_OBSERVATIONS.md).

**Priority:** P1 · **Depends on:** PB-0.1

Add an append-only observation record for supported imports, separate from the
canonical finding and its workflow. Record organization, source/tool instance,
scan/import, source-specific stable identifier where available, observed time,
and relevant asset identity. Preserve existing finding identity and workflow
decisions on repeated imports.

**Acceptance criteria**

- Repeated observations can be inspected without overwriting finding workflow
  history or duplicating the canonical finding.
- Ambiguous/missing source identifiers are explicitly marked ineligible for
  reconciliation, not guessed from description text.
- Tests cover asset-bearing and finding-only import paths, repeated/changed
  findings, null identifiers, and archive interactions.

### PB-1.2 — Declare comparable scan snapshots

**Status, 5 November:** Complete locally and activated at migration 0041. Chrome
passed 90 checks, the final snapshot backend suite passed 40 checks and the full
frontend suite passed 529 tests. Captured configuration, versioned source-scan declarations and
metadata-only comparison expose scope/completeness/configuration blockers.
Absence eligibility remains false; no findings are marked Not observed.
Delivered through `dcf387a`, `b3e5095` and `24a5f66`; all four exact-commit hosted
Linux jobs passed for `24a5f66` in
[run 42245252464](https://github.com/shalisarakkal/AuditMind/actions/runs/42245252464).
[Contract and verification](SCAN_SNAPSHOTS.md).

**Priority:** P1 · **Depends on:** PB-1.1

Represent successful complete scans with source/tool, scope, configuration
identity, and completion state. Provide a review operation that compares only
compatible snapshots and reports scope differences before any absence result is
accepted.

**Acceptance criteria**

- Partial, failed, cancelled, incompatible, or scope-changed scans cannot
  generate absence conclusions.
- A comparison displays its baseline/current snapshots and scope exclusions.
- "Not observed" is a review state only; it does not change severity, archive
  the finding, or mark remediation resolved.

### PB-1.3 — Implement reviewed finding reconciliation

**Current, 11 November:** native reviewed suppression/clear and its retained-source
conflict correction are delivered at migration 0050. All four hosted jobs passed
for `f97a4fb` in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797); the subsequent draft-save correction
`e4c7488` passed all four in [run 43144443993](https://github.com/shalisarakkal/AuditMind/actions/runs/43144443993). Durable review, atomic
visibility/count/risk invalidation, source-retention safeguards, possible-
reappearance receipts and guarded UI are implemented. Consolidation, source-
payload publication, additional mappings and automatic reconciliation remain open.
Earlier dated checkpoints below describe their original scope.

**Delivered increments (8 November):** [Cross-import identity review](CROSS_IMPORT_IDENTITY_REVIEW.md)
adds bounded native Nessus comparison and independent admin-confirmed mapping
carry-forward for the same finding. Canonical conflicts block. The subsequent
[canonical designation](CANONICAL_FINDING_REVIEW.md) adds reversible admin
designation with both histories preserved, context/version fences, independent
receipts and explicit revocation. It does not consolidate counts or transfer
workflow/scoring decisions. All four hosted CI jobs passed on the canonical
feature SHA `f31bb25` in
[run 60](https://github.com/shalisarakkal/AuditMind/actions/runs/42492464513);
the follow-up documentation SHA passed all four in
[run 61](https://github.com/shalisarakkal/AuditMind/actions/runs/42493878994).
The final canonical local run passed 1,710 backend and 560 frontend tests.
The new bounded absence-candidate preview is implemented locally and its
focused backend regression set passes 110 tests. Its focused frontend suite
passed 8 tests, and changed-file lint plus TypeScript checks passed. All four
hosted Linux jobs passed on `d06d31e` in
[run 42529240560](https://github.com/shalisarakkal/AuditMind/actions/runs/42529240560);
the new isolated real-Chrome walkthrough passed two scenarios
(candidate shown when eligible; candidates withheld when current identity
review is revoked). Durable absence
dispositions that change finding visibility, consolidation, source publication and suppression remain open;
PB-1.3 is not closed by these review increments.

**Identity foundation:** Versioned candidate-key logic, reviewed native Nessus
mapping, read-only observation diagnostics, and explicit admin-reviewed tool
and canonical-asset bindings (migration 0046) are implemented. New observations
do not inherit bindings. Cross-import review (increment 3) and reversible
canonical designation (increment 4, migrations 0047/0048) preserve explicit
review and do not enable automatic reconciliation. See
[identity contract](FINDING_IDENTITY.md). These delivered increments close
their scoped features, not PB-1.3 as a whole.

**Integration update, 11 November:** both worktrees are integrated with stale
preview/workflow guards, blocking submission controls and bounded queue
summaries. Full local backend 1,723 and frontend 567 tests, 99 Chrome checks,
builds and security checks pass. Activated at 0049 after idle checks; hosted CI
is verified on the exact pushed SHA at delivery. [Current review](ABSENCE_REVIEW_RELEASE_REVIEW.md).

**Historical checkpoint, 8 November (superseded by verified delivery above):** The durable absence-review queue is implemented locally
on the PB-1.3 feature branch. Migration 0049 stores candidate/context snapshots
without source-row foreign keys; organization members can page/read, and admins
or auditors can explicitly save candidates and append version-fenced keep-active
or reopen decisions. Neither action changes finding state. The focused
PostgreSQL scan-snapshot suite passes 47 tests, including queue idempotency,
tenant/role boundaries, pagination, decision history, unchanged finding state
and source-row purge retention. The focused queue UI suite passes 11 tests;
changed-file lint and TypeScript validation pass. Chrome and hosted CI remain
pending; this is not yet a merged or deployed migration. Suppression,
archive/restore disposition and reappearance reconciliation remain out of
scope.

**Priority:** P1 · **Depends on:** PB-1.1, PB-1.2

Provide an authorized user with a durable review queue for findings not
observed in comparable scans, then allow an explicit retain, suppress/archive
or restore decision with a reason and durable history. The integrated local
increment supplies the read-only preview and a durable, explicit review queue
with keep-active/reopen notes, plus reviewed native suppression/clear and safe
source archive/restore/purge handling. Consolidation, source-payload publication,
additional mappings and automatic reconciliation remain open; PB-1.3 is partial.

**Acceptance criteria**

- Absence never auto-resolves or archives a finding.
- Saving a candidate batch is explicit, idempotent and preserves the compared
  evidence after source-row retention; candidate saves and review decisions do
  not mutate the finding.
- Keep-active and reopen decisions are attributed, version-fenced and
  append-only.
- Only an explicit reviewed suppression or archive/restore operation may change
  disposition, with stable identity and durable rationale.
- Reappearance updates observation history and surfaces the prior review or
  suppression.
- Suppression uses stable identity and survives ordinary source-row retention;
  ambiguous identity never inherits suppression.
- Cover retention, restore, purge, duplicate imports, and tenant boundaries.

Detailed functional constraints are in the documented
[finding reconciliation design](FINDING_RECONCILIATION_DESIGN.md).

### PB-1.4 — Add the minimum asset context and ownership model

**Priority:** P1 · **Depends on:** PB-0.1

Add organization-managed asset owner, environment, and business-criticality
fields with clear unknown/unassigned states. Keep them separate from imported
scanner attributes unless a source mapping is explicitly configured.

**Acceptance criteria**

- Authorized users can set, view, filter, and audit changes to these fields.
- Imports do not silently overwrite organization-maintained values.
- Existing assets migrate with safe unknown defaults and unchanged finding
  references.

### PB-1.5 — Introduce a versioned control catalog and finding mappings

**Priority:** P1 · **Depends on:** PB-1.1

Create stable internal control IDs, versioned control descriptions, and
traceable mappings from supported finding categories to controls. Display
framework references only where the source and usage rights are established.

**Acceptance criteria**

- A mapping identifies its catalog version, source, and review status.
- Unmapped findings remain visible as unmapped; no implied compliance pass or
  certification is produced.
- Changing catalog versions does not rewrite saved report snapshots.

## Phase 2 — Evidence-backed remediation operations

### PB-2.1 — Attach remediation proof as a first-class record

**Status, 6 November:** PB-4.4 implements the protected reference/document-version
submission and administrator decision ledger for scoring eligibility. This is a
bounded delivery: workflow closure remains a user assertion and rejected proof
restores/retains full risk without automatically rewriting workflow status.
Full transition enforcement and broader artifact workflows below remain open.

**Priority:** P2 · **Depends on:** PB-1.1

Extend the existing finding workflow so post-fix evidence is a protected,
tenant-scoped artifact/reference with uploader, timestamp, source, and review
state—not only free-text verification.

**Acceptance criteria**

- A user can submit evidence for a finding in a verification-pending state.
- An authorized verifier can accept or reject it with a reason; the decision is
  recorded in workflow history.
- Rejected proof leaves the finding unresolved and explains the next action.
- Access, retention, archive, and download behavior follow existing evidence
  security rules.

### PB-2.2 — Enforce and explain workflow transitions

**Status, 6 November:** Existing role/version/deadline/note validation remains.
PB-4.4 additionally binds scoring exclusions to approved evidence and invalidates
them after later status changes. Requiring that decision before a workflow
transition itself, and source-triggered reopening, remain separate future work.

**Priority:** P2 · **Depends on:** PB-2.1

Define allowed transitions for the existing workflow statuses and show why a
transition is unavailable. Keep scanner observation state independent from
remediation status.

**Acceptance criteria**

- Invalid transitions are rejected consistently by API and UI.
- Resolved/mitigated transitions require the configured verification decision
  and evidence reference; false-positive and accepted-risk transitions retain
  their own rationale and permissions.
- Reopen records the triggering observation and does not erase prior history.

### PB-2.3 — Add remediation work queues

**Priority:** P2 · **Depends on:** PB-2.2

Provide saved views for "assigned to me", overdue, pending verification,
accepted risk nearing review, and unassigned findings. Reuse existing workflow
fields and pagination rather than creating duplicate state.

**Acceptance criteria**

- Each queue has exact totals and tenant-scoped filters.
- Deadline comparisons use stored expiry instants; display and date filters
  follow existing browser-timezone and inclusive full-day semantics.
- A workflow update or organization switch cannot leave stale rows or filters
  visible.

### PB-2.4 — Add risk-acceptance review notifications

**Priority:** P2 · **Depends on:** PB-2.3

Notify the designated owner/admin before a risk-review deadline and surface
expired acceptances in the work queue. Start with in-app visibility; add email
only after notification preferences and delivery operations are designed.

**Acceptance criteria**

- Notification candidates are idempotent and do not extend or renew acceptance.
- Expired risk acceptance is visibly overdue and requires an authorized review.
- Delivery failure is observable; no notification is silently reported as sent.

## Phase 3 — Decision-support reporting

### PB-3.1 — Add evidence coverage and freshness to report summaries

**Priority:** P3 · **Depends on:** PB-1.1, PB-1.5

Include captured source date ranges, stale/missing evidence, import/scan
references, applicable control mappings, and explicit coverage limitations in
report summaries and exports.

**Acceptance criteria**

- Summary values derive from the report's captured snapshot, not mutable live
  data.
- Missing coverage is stated as unknown/insufficient rather than a passing
  result.
- HTML/PDF and API representations agree on source/citation references.

### PB-3.2 — Publish a report-linked remediation action plan

**Priority:** P3 · **Depends on:** PB-2.1, PB-2.3, PB-3.1

Show report recommendations with their underlying finding/control/evidence,
current workflow state, owner, and due date. Let authorized users create or
open remediation work from an action without duplicating it on report refresh.

**Acceptance criteria**

- Every action links to captured report inputs and, when created, one
  organization-scoped workflow record.
- Repeated action creation is idempotent for the same report/action identity.
- Report snapshots preserve the state at generation time; current remediation
  state is clearly labeled separately.

### PB-3.3 — Add report review and release state

**Priority:** P3 · **Depends on:** PB-3.1

Support draft, reviewed, and distributed states with reviewer identity and
timestamps for report audiences that require approval. Retain the immutable
generated report version.

**Acceptance criteria**

- Only authorized roles can approve or distribute.
- A revised report creates a new version and never silently edits a distributed
  report.
- Report status and audit history are available in the UI and API.

### PB-3.4 — Strengthen recommendation validation

**Priority:** P3 · **Depends on:** PB-3.1

Validate recommendation references, required rationale, uncertainty labels,
and safe output rendering. Keep deterministic scoring separate from AI prose
and reject fabricated or unknown IDs.

**Acceptance criteria**

- A recommendation referencing an ID outside captured input cannot be
  published as evidence-backed.
- Insufficient evidence is represented explicitly.
- Tests cover malformed output, missing evidence, duplicate references,
  output encoding, and unchanged legacy report snapshots.

## Phase 4 — Contextual prioritization and measurable progress

### PB-4.1 — Define an explainable priority policy

**Priority:** P4 · **Depends on:** PB-1.4, PB-1.5, PB-2.1

Specify a deterministic, versioned priority policy that combines finding
severity with available exploitability, exposure, asset criticality, evidence
quality, and remediation urgency. Treat unknown inputs explicitly.

**Acceptance criteria**

- Each ranking exposes input values, weights/rules, policy version, and
  missing-data effects.
- Identical inputs and policy versions yield identical priorities.
- Priority is advisory and does not silently alter existing dashboard scores
  or finding severity.

### PB-4.2 — Explain priority changes

**Priority:** P4 · **Depends on:** PB-4.1

Record which input or policy change caused an item to move up or down and
provide a concise user-facing explanation.

**Acceptance criteria**

- A user can compare the current priority with the preceding evaluated version.
- Changes caused by new evidence, asset context, or policy updates are
  distinguishable.
- Missing historical inputs are labeled rather than inferred.

### PB-4.3 — Add remediation and risk trend views

**Priority:** P4 · **Depends on:** PB-2.3, PB-3.1

Provide time-series views for open/overdue/verified work, accepted risk,
finding age, evidence freshness, and deterministic score changes.

**Acceptance criteria**

- Trend points use immutable snapshots or event history with documented
  timestamp semantics.
- The view identifies changes in coverage, scoring policy, and control catalog
  version that affect comparability.
- Filters and totals remain organization-scoped and return a clear empty state.

### PB-4.4 — Introduce verified status-aware current-risk scoring

**Priority:** P4 · **Depends on:** PB-2.1, PB-2.2

**Status:** Approved policy implemented and validated locally on 6 November 2026;
reviewed and pushed through `8043cca`. All four hosted Linux jobs passed in
[run 42319257996](https://github.com/shalisarakkal/AuditMind/actions/runs/42319257996). Broader coverage rollout, residual-risk reductions and
production acceptance remain separate open items.
See [the approved contract](STATUS_AWARE_SCORING.md).
This belongs to Product Phase 4, not the older delivery-phase documents named
`PHASE4_*.md`.

Introduce a default-On Platform policy with an organization Inherit/On/Off
override for versioned current-risk scoring. Preserve legacy scoring when
disabled. This setting is separate from
the evidence-qualified scoring setting: remediation status must not bypass
coverage, freshness or insufficient-evidence checks.

**Approved treatment**

| Workflow status | Current-risk contribution |
| --- | --- |
| Open | Full risk contribution. |
| Accepted risk | Full contribution; accepting risk does not remove it. |
| Mitigated | Full contribution until an approved residual-risk assessment supports a defined reduction. |
| Resolved | Exclude only after an authorized verification decision with supporting evidence. |
| False positive | Exclude only after an authorized decision validates that the finding is incorrect or inapplicable. |

Free-text rationale or verification notes alone do not authorize score
exclusion. Organization admins review evidence; self-review requires explicit
acknowledgment. Proof expires within 90 days and later observations invalidate
exclusions. Mitigated retains full risk until a residual-risk method is approved.
Scanner observation state remains separate
from workflow status; absence alone must not imply resolution.

**Acceptance criteria**

- Existing organizations inherit the approved Platform default On. Organization
  admins can explicitly choose On/Off or resume inheritance; changes are versioned
  and audited. Existing notes never become verification approvals automatically.
- Show visible finding totals separately from findings contributing to current
  risk, using the same tenant/filter scope and explaining exclusions.
- Exclusions/reductions identify their verification decision, evidence reference,
  policy version and reason. Expired/revoked or invalidated verification cannot
  silently continue suppressing risk. Reopening restores risk contribution.
- Preserve finding severity, source observations, workflow history and saved
  report snapshots. Do not delete or archive a finding to change its score.
- New dashboard/report snapshots capture the scoring mode, policy version and
  contribution/exclusion basis. Older snapshots are never recalculated in place;
  comparisons disclose changes in policy and evidence coverage.
- Insufficient evidence remains Not assessed. Excluding every finding must not
  automatically establish adequate coverage or a healthy score of 100.
- Invalidate/rebuild affected dashboard and count caches after setting changes,
  verification decisions, proof expiry/revocation and workflow changes, without
  allowing stale background results to overwrite newer policy/evidence state.
- Tests cover disabled-mode parity, all statuses, unverified closure, accepted
  risk, residual-risk rules, reopening, stale/revoked proof, missing evidence,
  tenant/role isolation, concurrent edits, cache invalidation and immutable reports.
- Platform default On and optional organization override are approved. Retain
  the setting until confidence supports a separate decision to remove it.

## Phase 5 — Integrations and advanced intelligence

### PB-5.1 — Choose one ticketing integration from pilot evidence

**Priority:** P5 · **Depends on:** PB-2.3, PB-0.2

Select one ticketing system based on pilot usage. Define whether AuditMind or
the ticketing system owns assignment, status, due dates, and closure before
building synchronization.

**Acceptance criteria**

- Credentials are tenant-scoped and stored using the approved secret mechanism.
- Sync is idempotent, retryable, observable, and supports disconnect/revocation.
- Conflicts and external deletion are surfaced for user resolution; no silent
  destructive sync is performed.

### PB-5.2 — Add configurable notifications

**Priority:** P5 · **Depends on:** PB-2.4

After in-app reminders prove useful, add an approved delivery channel with
organization settings, templates, unsubscribe/preferences, and delivery status.

**Acceptance criteria**

- Preferences and recipients are permission-checked and audited.
- Retries do not create duplicate notices and delivery errors are visible.
- Notification content does not disclose findings to unauthorized recipients.

### PB-5.3 — Evaluate threat-intelligence enrichment

**Priority:** P5 · **Depends on:** PB-4.1

Run a bounded design and data-quality evaluation for known-exploited and
exploit-availability enrichment. Do not fetch or expose external intelligence
until licensing, provenance, freshness, privacy, and egress are approved.

**Acceptance criteria**

- Enrichment source, retrieval time, confidence, and expiry are visible.
- Missing/stale intelligence does not lower priority or imply safety.
- The feature can be disabled without changing source findings or deterministic
  baseline scores.

### PB-5.4 — Assess attack-path analysis feasibility

**Priority:** P5 · **Depends on:** PB-1.4, PB-1.5, PB-4.1

First validate whether asset relationships, identity paths, and exposure
evidence are sufficiently complete. Implement only a bounded graph view if
inputs support explainable paths.

**Acceptance criteria**

- Every path edge has a source and observation time.
- Incomplete graph coverage is explicit; absence of a path is not described as
  proof of safety.
- Users can inspect the evidence behind each path and report false/ambiguous
  relationships.

## Cross-cutting definition of done

Every implementation item must include, as applicable:

- Tenant and role authorization tests, including cross-organization denial.
- Migration upgrade/rollback or compatibility coverage for persisted changes.
- API schema and UI behavior tests, including empty, stale, and error states.
- Audit/history behavior for state changes and administrative decisions.
- Evidence retention, archive/restore, and export implications.
- Performance measurement for large organization lists and background jobs.
- Documentation of feature flags/defaults, rollout, rollback, and limitations.
- Verification against the exact requested behavior; mocks are not evidence of
  real-provider quality or production capacity.

## 12 November 2026: PB-1.3 read-only foundation

Migration `0051` adds retained consolidation/decision ledgers and bounded read APIs.
An administrator-only preview validates current pair prerequisites in a read-only
snapshot. No consolidation writes, visibility changes or new UI actions are enabled.
Current membership/dependencies, proof, lifecycle and consumer integration remain
pending before publication. Validation and API details: [foundation review](CONSOLIDATION_FOUNDATION_REVIEW.md).

Membership/dependency follow-up: `0052` reserves tenant/generation-scoped member
and retained source-reference tables. Read-only previews include bounded dependency
counts and a diagnostic fingerprint. No writer, visibility integration or lifecycle
guard is enabled. All 90 PostgreSQL regression tests passed; migration parity and
the high-severity security gate passed. Local activation is tracked in the foundation review.

Strong pre-commit review (12 November): full backend 1,820 passed; final affected
suite 49 passed; frontend 578 passed; Chrome workflow 103 checks passed; isolated
build/TypeScript/lint and security gates passed. Review fixed preview pool
exhaustion, malformed manifest admission and excessive-offset validation. See
the consolidation foundation review for overlapping scopes and performance limits.
The foundation remains read-only; hosted CI must pass for the pushed checkpoint.

## 12 November: Stage A internal metadata transaction component

The next increment adds caller-owned atomic metadata staging, fresh authorization,
try-only admission locks, idempotent receipts and source/conflict checks. It is
not called by a route; production publication stays unconditionally disabled.
Visibility/count/scoring/proof/lifecycle/UI integration remains pending.
Validation and exact scope: [transaction component](CONSOLIDATION_TRANSACTIONS.md).

Local transaction verification: 82 broader regression/performance checks and
31 final unit/transaction checks passed (overlapping scopes); high-severity
static gate passed. No normal data publication, migration or restart occurred.
Hosted CI must be verified for the pushed transaction-component checkpoint.


## 12 November: Stage A visibility integration (local, unpublished)

The private transaction now integrates canonical/alias visibility with lists,
counts, Dashboard snapshots, scoring/report inputs and atomic revision
invalidation. Both source/history rows remain retained. Publication is still
unconditionally disabled: group-aware proof, lifecycle/reappearance, final
policy/Activity and guarded UI gates remain. PB-1.3 is not closed. Migration
`0053` requires coordinated activation and rebuilds 28 partial indexes; it has
not been applied to the normal application database. Scope, validation and
rollout limits: [visibility integration](CONSOLIDATION_VISIBILITY.md).

Local visibility verification completed: all 1,865 backend tests passed with
PostgreSQL required and warnings treated as errors; isolated production build
and all 103 existing Chromium workflow checks passed. The 100,000-finding count
plan retained its covering index; high-severity static and whitespace gates
passed. No normal-data migration, restart or publication occurred. This local
result does not replace hosted CI for a subsequent committed checkpoint.


## 12 November: reviewed native pair publication (Stage A, locally verified)

Group-scoped scoring proof, source lifecycle/reappearance guards, default-off
organization opt-in, authorized apply/undo and guarded UI are implemented locally.
Both source records/workflows remain; no payload is copied. Existing notes are
not approvals, and undo requires explicit approval revocation. PB-1.3 remains
partial: Stage B payload publication and additional/automatic mappings are open.
No normal-data migration or restart occurred. Contract, activation and Chrome
steps: [Stage A release review](CONSOLIDATION_RELEASE_REVIEW.md).


## 13 November: Stage A local review closeout

Local validation passed: 1,903 full backend tests, 585 frontend tests, 106 full
Chrome checks and the final focused Chrome walkthrough. The final 58-test
PostgreSQL run covers the subsequent failed-archive revocation recovery fix;
these scopes overlap. Lint, high-severity static security, secret and whitespace
checks passed. Retained history paging and reapply after undo are covered.
Changes remain uncommitted; normal-data migration/restart and hosted Linux CI
for this increment remain pending. Consolidation stays default-off. See
[scope, measurements, activation and verification](CONSOLIDATION_RELEASE_REVIEW.md).


## 13 November: hosted verification and local activation complete

Application commit `427596b781d278a9b65d4a8d46511662b50834ed` passed all four
[hosted Linux jobs](https://github.com/shalisarakkal/AuditMind/actions/runs/43436101209):
backend, frontend, dependency/security and browser acceptance. The hosted mobile
Settings overflow was corrected and the 374px/390px checks remain enforced.

The owner selected maintenance after CI success. Services were stopped, an
approximately 1.74 GB custom-format `auditmind_demo` backup was created in 126.9
seconds, and its archive listing and SHA256 were verified. Backup and manifest
remain in the ignored local `temp/auditmind-demo/checkpoints` directory; no
backup data or credentials are committed.

Migrations `0053` through `0055` completed, including all 28 findings index
replacements and both observation indexes. No invalid indexes or metadata drift
remain. The maintenance script's initial Alembic version-table reflection check
was corrected to match `demo.prepare`; this required no application/schema fix.
The frontend was rebuilt and API/frontend/one-slot worker restarted. `/health`,
`/ready` (database/uploads/worker) and `/login` passed. Existing accounts and
passwords were retained. No organization is opted in and no alias was published.

The application is available at http://localhost:3000/login. Enabling the
separate organization setting and applying a reviewed pair remain explicit
admin actions. Remaining PB-1.3 scope is unchanged: Stage B payload publication,
additional identity mappings, larger groups and automatic reconciliation.


## 13 November: manual acceptance deferred; next engineering scope

- [ ] Complete the [manual consolidation acceptance walkthrough](CONSOLIDATION_CHROME_WALKTHROUGH.md)
  in a test organization. **TODO, deferred at the user's request**; the complete
  manual flow has not been signed off. No user testing is required now.
- [x] Automated verification remains complete: local/hosted Chrome, backend,
  frontend and security checks passed; local schema activation is at `0055`.
  This is separate from manual user/pilot acceptance.
- [x] Delivered in `531d8e9` (hosted Linux verified): Stage B's versioned native observation
  payload contract, ownership/identity/context admission and bounded read-only
  publication preview, following the [publication design](REVIEWED_FINDING_PUBLICATION_DESIGN.md).
  Preserve finding ownership/workflow and retained history. Publication writes,
  scoring/evidence invalidation and guarded UI must be reviewed/tested before
  exposing Apply. The preview is complete; Stage B publication remains incomplete.

Deferring manual acceptance does not close PB-1.3 or approve broader feature
rollout. Existing settings, partial test records and running services are unchanged.


## 13 November: Stage B read-only payload preview (locally verified)

New native snapshots have a strict server mapping stamp inside existing JSON;
legacy snapshots are not rewritten. A tenant/actual-admin guarded API previews
only the latest independently reviewed ordinary native observation, with full
hashes and bounded field differences. It cannot publish or undo. No migration
or running-application restart occurred. Manual Stage A acceptance stays TODO.
See [contract, verification and remaining publication gates](OBSERVATION_PAYLOAD_PREVIEW.md).

Local Stage B verification: full backend 1,960 passed; Chrome 106 checks passed;
final focused preview/metadata regressions passed (52 plus three overlapping
metadata cases). High-severity security, source secret-pattern and whitespace
checks passed. No publication/undo writer, new UI, migration or normal-application
restart is included. This increment requires exact-commit hosted verification
before activation; Stage A manual acceptance
remains TODO/deferred. Next is reviewed snapshot/decision storage and atomic
publish/undo with consumer/lifecycle/proof guards before exposing Apply.

## Stage B storage follow-up — 13 November

The preview foundation `531d8e9` is pushed and all four Linux CI jobs passed.
Current work reserves source-owned before/after snapshots, minimal retained
decision receipts, exact current-generation references and indexed dependencies
in migration 0056. See [storage scope](OBSERVATION_PUBLICATION_STORAGE.md).
No publication route or normal database activation is included. Transaction,
consumer/proof/lifecycle integration and guarded UI remain required before writes.

Storage verification passed: 48 isolated PostgreSQL storage/preview/migration
checks, then all 12 final storage checks including retained-receipt downgrade
protection (overlapping scopes). Compilation, high-severity Bandit and whitespace
checks passed. Storage is committed in `2751c3b`; normal database activation remains deferred.


## 14 November: reviewed Stage B storage delivery

Application source: `2751c3b`. [Storage contract and review](OBSERVATION_PUBLICATION_STORAGE.md).
Migration 0056 reserves source-owned before/after snapshots, minimal retained
receipts, exact current-generation references and indexed dependencies. A
reproduced cross-tenant snapshot-owner gap is fixed by a snapshot-only database
guard. Actor lookups have an index; a redundant history index was removed.

Verification: full backend **1,981 passed in 2,180.81 seconds**; frontend **585
passed across 61 files**; lint/production build passed; installed Chrome **106
checks passed**. The final storage suite passed **18 checks in 38.09 seconds**
(overlaps the full suite). Migration up/down/drift, retention, tenant boundaries,
actor deletion and the indexed 100,000-dependency probe passed. One local warm
probe measured 0.151 ms; this is not API latency or SaaS capacity evidence.
High-severity Bandit, tracked-secret checks, pip consistency and the backend
dependency audit passed. Frontend production audit found zero vulnerabilities;
seven moderate ESLint-chain development findings are a separate dependency follow-up.

No normal migration, restart, source-field publication or feature enablement was
performed. Still required: default-off publication settings, authorized atomic
Publish/Undo, proof and consumer invalidation, lifecycle guards and guarded UI.
PB-1.3 remains partial; manual acceptance remains TODO/deferred. Hosted Linux CI
is the post-push acceptance gate; see the main workflow and delivery confirmation
for the exact pushed-commit result.


- [ ] Separate dependency follow-up (14 November audit): remediate the seven
  moderate ESLint/minimatch development-chain findings with compatibility tests.
  Production frontend audit: zero findings; no high/critical development findings.
  Do not apply the audit tool's forced downgrade without compatibility review.
