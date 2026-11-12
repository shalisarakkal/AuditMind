# AuditMind Product Roadmap

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


11 November local integration: the authorized durable absence-review queue
from the second worktree is now included with review corrections. It records
historical keep-active/reopen notes without changing findings or scores;
local acceptance passed (1,723 backend tests, 567 frontend tests, 99 Chrome
checks, builds/security), and the app is active at 0049. Hosted CI is verified
on the exact pushed SHA at delivery. [Current review](ABSENCE_REVIEW_RELEASE_REVIEW.md).
This supersedes earlier statements that this feature is excluded; older dated
test/CI results remain historical.

## Goal

Evolve AuditMind from an evidence-ingestion and reporting platform into an
evidence-backed cyber resilience workflow: teams can trust what a report says,
decide what to do next, assign the work, and verify that risk was reduced.

This is a product direction, not a claim that the capabilities below are
implemented or approved for release. The latest delivered code and exact-SHA hosted results are recorded above. Pilot and production acceptance remain
separate open decisions. See [release readiness](RELEASE_READINESS.md) and
[Phase 4 status](PHASE4_STATUS.md) for the code-backed project state.
The [product backlog](PRODUCT_BACKLOG.md) breaks the phases into ordered
candidate work items with acceptance criteria.

## Prioritization at a glance

PB-1.3 has delivered reviewed native identities, cross-import mapping review,
canonical designation, a durable absence-review queue and explicit native Nessus
suppression/clear with source-lifecycle safeguards. Canonical designation does
not merge records. New uploads do not inherit trusted identity bindings;
possible reappearances remain visible for independent review.

The next proposed engineering increment is reviewed consolidation and source-
payload publication, with workflow/proof ownership and rollback rules designed
before implementation. Additional source mappings and automatic reconciliation
remain separate. PB-1.4 asset ownership/context and PB-1.5 controls/mappings follow.

**Deferred decision:** resume PB-0.2 and approve a bounded pilot contract when
the project owner resumes that gate. The native suppression/clear increment is complete; the
next proposed PB-1.3 work is consolidation/payload-publication design.
The gate remains deferred until the project owner selects audience, environment,
data, workflows, operating/support boundaries and acceptance criteria. The
[release checklist](RELEASE_READINESS.md#pb-02-pilot-readiness-contract-decisions-required-to-close-the-gate)
lists the exact decisions. Do not treat green CI as pilot/customer approval.

Local baseline maintenance on 6 November addressed stalled existing-asset cloud
reimports with bounded bulk updates and safe Abort handling. Exact-file local
verification and rollout limits are recorded in [Phase 4 validation](PHASE4_VALIDATION.md).
This does not close the separate SaaS scaling or release-acceptance gates.

| Priority | Milestone | Why it comes here |
|---|---|---|
| P0 | Close current acceptance and operational gates | Establish a dependable baseline before expanding scope. |
| P1 | Make evidence and control context explicit | Reports and prioritization need trustworthy, traceable inputs. |
| P2 | Deliver remediation workflow MVP | Turns findings into accountable work and verifiable closure. |
| P3 | Upgrade reports into evidence-linked action plans | Makes reports more useful without overstating what the data supports. |
| P4 | Add contextual prioritization and progress trends | Depends on reliable evidence, ownership, and lifecycle history. |
| P5 | Add integrations and advanced security intelligence selectively | Higher cost and risk; pursue only after the core loop proves useful. |

Priorities describe dependency and product value, not calendar estimates. Each
milestone should be scoped and accepted before the next one expands the data
model or operational surface.

## P0 — Close current acceptance and operational gates

**Progress, 8 November:** PB-0.1 checklist/ownership reconciliation is complete;
the project owner/user holds release approval and engineering/operations/security
ownership. PB-0.3 passed the isolated synthetic recovery rehearsal. PB-0.2 remains
user-deferred; its decision checklist is explicit, but the contract has not been
approved. Production acceptance gates remain open.
See [current release gates](RELEASE_READINESS.md#baseline-and-operational-gates)
and [recovery evidence](RECOVERY_REHEARSAL.md). P0 is not wholly closed.

**Outcome:** The existing product is a reliable baseline for a limited, clearly
defined pilot.

Focus:

- Complete the outstanding release acceptance and sign-off documented in the
  project status.
- Keep documented rollout holds, default-off behavior, and single-worker
  assumptions explicit; do not imply SaaS scale or production readiness without
  measured evidence.
- Keep migration, backup/recovery, authorization, tenant-isolation, and
  operational procedures aligned with the running implementation.
- Ensure pilot users can distinguish implemented behavior from proposals and
  local-only validation.

**Exit criteria:**

- Release gates have named owners and recorded pass/fail evidence.
- A pilot scope, supported workflows, and known limitations are documented.
- No feature is described as production-ready solely because unit or local tests
  pass.

## P1 — Establish evidence and control context

**Progress, 5 November:** PB-1.1's additive source observations are complete
locally and activated at migration 0040, with verification tracked in
[Phase 4 validation](PHASE4_VALIDATION.md). Pre-commit review and local verification
are complete (1,528 backend / 522 frontend tests and 87 Chrome checks).
PB-1.1 was pushed through `376342c` and passed all four hosted Linux jobs in
[run 42113315252](https://github.com/shalisarakkal/AuditMind/actions/runs/42113315252).
PB-1.2 scan declarations and metadata comparison are complete locally and active
at migration 0041 (90 Chrome checks, 40 final snapshot backend checks and 529
frontend tests pass). Delivered through `24a5f66`, with all four hosted Linux jobs
passing in [run 42245252464](https://github.com/shalisarakkal/AuditMind/actions/runs/42245252464);
[contract](SCAN_SNAPSHOTS.md).
Existing matching and archive ownership remain unchanged. PB-1.3's explicit
identity review increments are delivered; automated reconciliation, source
payload publication, durable absence dispositions and suppression remain
pending. The read-only candidate preview shipped through `d06d31e`, with all
four hosted Linux jobs passing in
[run 42529240560](https://github.com/shalisarakkal/AuditMind/actions/runs/42529240560).
A preview candidate is not a recorded absence conclusion.

**Outcome:** Users can tell where evidence came from, whether it is current, and
what security obligation a finding relates to.

Deliver in a narrow, additive increment:

- Preserve source, import/run identifier, observation time, upload time, and
  relevant parser or profile information for ingested evidence.
- Represent evidence review and freshness explicitly, including stale,
  superseded, incomplete, and unreviewed states where applicable.
- Show evidence references and coverage gaps on findings and reports.
- Add useful asset context, beginning with accountable owner, environment, and
  business criticality.
- Define a versioned control catalog and map supported findings to controls.
  Keep framework mappings traceable to authorized source material; selecting a
  framework must not imply that licensed standards text is included.

**Exit criteria:**

- A user can trace a displayed finding back to its source evidence and import.
- Stale or missing evidence is visible and cannot be presented as current proof.
- Control mappings have stable identifiers, versioning, and an auditable source.
- Tenant boundaries and existing import/report behavior remain covered by
  regression tests.

## P2 — Deliver the remediation workflow MVP

**Outcome:** Teams can assign work, document decisions, and close findings only
with appropriate verification.

Deliver:

- A remediation record linked to the finding, affected asset, evidence, and
  control; keep remediation state distinct from the scanner's finding state.
- A small, explicit lifecycle such as **Open â†’ Triaged â†’ In progress â†’ Pending
  verification â†’ Resolved**, with a reopen path when new evidence shows the
  issue persists or returns.
- Owner, due date, notes, timestamps, and a complete change history.
- Time-bounded risk acceptance with a justification, approver, review/expiry
  date, and any compensating controls.
- Post-fix evidence and a verification decision before resolution.
- Basic lists and filters for assigned, overdue, pending verification, and
  accepted-risk work.

**Exit criteria:**

- Every state change is authorized, tenant-scoped, and auditable.
- A finding cannot be marked resolved without the defined verification evidence
  or an explicitly approved exception.
- Expired risk acceptances are surfaced and do not silently remain valid.
- Users can follow one issue from discovery through verified closure.

## P3 — Make reports evidence-linked action plans

**Outcome:** Reports help readers make decisions and act, while clearly
separating measured facts, derived scores, and AI-generated interpretation.

Deliver:

- A versioned report snapshot identifying its reporting period, source data,
  evidence freshness, and coverage limitations.
- An executive summary and technical detail that link claims to finding,
  asset, control, and evidence identifiers.
- A prioritized action plan with rationale, suggested owner, target date or
  timeframe, and links to the underlying remediation records.
- Explicit uncertainty and insufficient-evidence states; do not generate
  unsupported facts to fill gaps.
- Validation that cited IDs exist in the captured report inputs and that
  generated output conforms to the report schema.
- Human review before distribution where required by the report's intended use.
- Clear separation between deterministic baseline scores and optional AI
  assessments; preserve existing report versions rather than rewriting history.

**Exit criteria:**

- Every material finding or recommendation in a report is traceable to captured
  input evidence, or labeled as a qualified suggestion.
- Reports disclose coverage and freshness limits.
- Invalid references, malformed output, or insufficient evidence produce an
  explicit failure or qualification, not a success-shaped report.
- Regression tests confirm legacy reports and deterministic scoring remain
  unchanged.

## P4 — Add contextual prioritization and progress trends

**Outcome:** Teams can focus on the most consequential work and measure change
over time.

Deliver:

- A transparent, versioned prioritization model using documented factors such
  as severity, exploitability, exposure, asset criticality, evidence quality,
  and remediation urgency.
- An explanation of each factor's contribution; do not hide policy choices
  inside an opaque AI score.
- Portfolio views for aging, overdue work, accepted risk, and risk by business
  area or control.
- Comparable historical snapshots for scores, findings, and remediation
  outcomes, with clear handling of changed scoring or control versions.
- Internal trend baselines before considering peer benchmarking.
- Verified status-aware current-risk scoring, enabled by default at Platform level with an
  organization override: retain full Open/Accepted risk/Mitigated contributions, and exclude Resolved/False positive only with
  authorized supporting verification. Preserve historical reports and insufficient-
  evidence states. Implemented and delivered through `8043cca`, with all four hosted Linux
  jobs passing in [run 42319257996](https://github.com/shalisarakkal/AuditMind/actions/runs/42319257996). See
  [PB-4.4](PRODUCT_BACKLOG.md#pb-44--introduce-verified-status-aware-current-risk-scoring),
  dependent on Phase 2 evidence and transition controls (PB-2.1/PB-2.2).

**Exit criteria:**

- Users can explain why an item ranks above another and identify the inputs
  behind that ranking.
- Historical comparisons disclose changes in data coverage, scoring rules, and
  framework versions.
- Score or priority changes can be traced to changed evidence, context, or
  policy rather than silently shifting.
- Status-aware scoring has approved verification/residual-risk rules, legacy
  parity while disabled, distinct total/current-risk counts and pilot acceptance
  before broader rollout. A note or missing scan result alone cannot remove risk.

## P5 — Integrate and automate selectively

**Outcome:** AuditMind fits existing security operations without compromising
tenant isolation, operational reliability, or user control.

Candidate capabilities, subject to user demand and separate design review:

- Ticketing integrations such as Jira, Azure DevOps, or ServiceNow.
- Import or synchronization connectors for selected security tools.
- Notifications and configurable remediation reminders.
- Threat-intelligence enrichment for exploitability and known exploitation.
- Attack-path or dependency analysis when sufficient relationship data exists.
- Carefully scoped, human-approved automation for low-risk workflow actions.

**Gate before each integration or automation:**

- Confirm a concrete customer workflow and supported source of truth.
- Define permissions, secret handling, data retention, retry/idempotency behavior,
  tenant boundaries, and failure visibility.
- Measure operational capacity and concurrency before enabling increased
  background work.
- Require human approval for changes that could disrupt production systems.

## Recommended first release slice

The highest-value first product increment after P0 is a **single finding
remediation loop**:

1. Select an existing finding and inspect its source, freshness, and affected
   asset.
2. Assign an owner and due date; record a triage decision.
3. Optionally document a time-bounded risk acceptance.
4. Attach post-fix evidence and request verification.
5. Resolve or reopen the finding with an auditable reason.
6. Show the resulting status in the finding list and in a report.

Keep the first slice small: no ticketing integration, automatic remediation,
cross-organization benchmarking, or new opaque AI scoring. Validate the workflow
with users before broadening it.

## Product principles and non-goals

- **Evidence before inference:** reports must make source quality and coverage
  visible.
- **Deterministic core:** keep core dashboard scoring explainable and separate
  from optional AI interpretation.
- **Human accountability:** AI can draft and summarize; authorized users own
  risk acceptance and closure decisions.
- **No implied certification:** framework mapping is not certification or proof
  of compliance.
- **No unvalidated scale claims:** load, concurrency, and production readiness
  require their own measured acceptance.
- **Build the closed loop first:** provenance â†’ prioritization â†’ ownership â†’
  remediation â†’ verification â†’ trend.

## How to maintain this roadmap

For each milestone, record the owner, user problem, scope, dependencies,
acceptance tests, rollout/rollback plan, and known limitations in the relevant
delivery plan. Reprioritize based on pilot feedback and measured operational
evidence; do not treat this sequence as a commitment to implement every P5
candidate.

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
