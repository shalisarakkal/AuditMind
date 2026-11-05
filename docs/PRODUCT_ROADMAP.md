# AuditMind Product Roadmap

## Goal

Evolve AuditMind from an evidence-ingestion and reporting platform into an
evidence-backed cyber resilience workflow: teams can trust what a report says,
decide what to do next, assign the work, and verify that risk was reduced.

This is a product direction, not a claim that the capabilities below are
implemented or approved for release. The current release still has pending
acceptance/sign-off; see the [README status](../README.md#status) and
[Phase 4 status](PHASE4_STATUS.md) for the code-backed project state.
The [product backlog](PRODUCT_BACKLOG.md) breaks the phases into ordered
candidate work items with acceptance criteria.

## Prioritization at a glance

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

**Progress, 5 November:** PB-0.1 checklist/ownership reconciliation is complete;
the project owner/user holds release approval and engineering/operations/security
ownership. PB-0.3 passed the isolated synthetic recovery rehearsal. PB-0.2 pilot
preparation remains user-deferred, and production acceptance gates remain open.
See [current release gates](RELEASE_READINESS.md#current-release-gate-checklist---5-november-2026)
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
- A small, explicit lifecycle such as **Open → Triaged → In progress → Pending
  verification → Resolved**, with a reopen path when new evidence shows the
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

**Exit criteria:**

- Users can explain why an item ranks above another and identify the inputs
  behind that ranking.
- Historical comparisons disclose changes in data coverage, scoring rules, and
  framework versions.
- Score or priority changes can be traced to changed evidence, context, or
  policy rather than silently shifting.

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
- **Build the closed loop first:** provenance → prioritization → ownership →
  remediation → verification → trend.

## How to maintain this roadmap

For each milestone, record the owner, user problem, scope, dependencies,
acceptance tests, rollout/rollback plan, and known limitations in the relevant
delivery plan. Reprioritize based on pilot feedback and measured operational
evidence; do not treat this sequence as a commitment to implement every P5
candidate.
