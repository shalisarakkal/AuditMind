# AuditMind Product Backlog

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
same validation record for limits and outstanding commit/CI review.

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

**Status, 5 November:** Complete as checklist/ownership reconciliation. The
project owner/user confirmed release approval and engineering, operations and
security ownership. Operational release gates remain open; this is not release
approval. [Current gate checklist](RELEASE_READINESS.md#current-release-gate-checklist---5-november-2026).

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

**Status, 5 November:** User-deferred; not completed. Customer pilot preparation
and broader scoring rollout remain held.

**Priority:** P0 · **Depends on:** PB-0.1

Document pilot users, supported import/report workflows, data handling,
known limitations, support path, and prohibited or disabled behavior. Preserve
default-off controls and current serial-worker assumptions unless separately
approved and measured.

**Acceptance criteria**

- Pilot scope names included and excluded workflows and data sources.
- Operators can tell which settings are off by default and what approval is
  needed to enable them.
- No concurrency, SaaS capacity, certification, or production-readiness claim
  is made without corresponding acceptance evidence.

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
Review/check-in/push and exact-commit hosted CI for this increment remain pending.
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

**Priority:** P1 · **Depends on:** PB-1.1, PB-1.2

Create a review queue for findings not observed in comparable scans. Let an
authorized user inspect the evidence and explicitly retain, suppress/archive,
or restore a finding with a reason and durable history.

**Acceptance criteria**

- Absence never auto-resolves or archives a finding.
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
