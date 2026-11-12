# Project status and next steps

Updated 11 November 2026 against the delivered application and exact-SHA hosted
results. This replaces the pre-implementation assessment; its historical text is
retained in [the e4c7488 version](https://github.com/shalisarakkal/AuditMind/blob/e4c7488/docs/PROJECT_STATUS_AND_NEXT_STEPS.md).

## Current baseline

| Scope | Verified status |
| --- | --- |
| Committed application | `e4c7488c1a0b40a99bc20efe60a6663fac7f62d3`; all four hosted Linux jobs passed in [run 43144443993](https://github.com/shalisarakkal/AuditMind/actions/runs/43144443993) |
| Suppression/retained-source delivery | `f97a4fbf29a728a45087f03d8dabf6ea21950d4b`; all four jobs passed in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797) |
| Recorded local schema | 0050, activated with clean drift; the draft-save fix required no migration |
| Suppression availability | Authorized native Nessus preview/suppress/clear APIs and guarded UI are delivered; current independent identity reviews are required |
| Source lifecycle | Purge retains the minimal ledger; clear/restore refuse conflicting retained payloads, including aliases; possible reappearances stay visible until independently reviewed |
| Unchanged drafts | Save draft disabled without persisted changes; identical valid saves preserve version, timestamp, audit and evidence revision; stale/source checks remain |
| Local validation scopes | Suppression: 120 expanded backend, three final indexed, 576 frontend and 103 Chrome checks. Draft-save: 54 backend and 15 component tests, lint/build. Counts overlap, not full-suite totals |

[Release evidence](SUPPRESSION_RELEASE_REVIEW.md),
[verification steps](EVIDENCE_USER_VERIFICATION.md),
[release gates](RELEASE_READINESS.md) and
[Phase 4 validation](PHASE4_VALIDATION.md) contain detailed scopes. The older
foundation-only and CI-pending assessment is superseded; it is not current status.

## Next engineering work

Documentation closeout reconciles CI/source/lifecycle records and checked links.
The baseline above identifies the delivered application code; this closeout
changes documentation only.

1. Check in the reviewed [read-only foundation](CONSOLIDATION_FOUNDATION_REVIEW.md)
   and verify hosted Linux CI for the pushed checkpoint. Implementation `9380668`
   delivers schema, pair preview, reserved membership/dependencies and source manifests;
   it does not consolidate findings or publish payloads.
2. Next implement atomic membership/dependency publication, visibility and revision
   invalidation across consumers, group-aware proof, source lifecycle safeguards
   and guarded UI under the [staged design](REVIEWED_FINDING_PUBLICATION_DESIGN.md).
   Writes remain unavailable until those paths and authorization/conflict guards
   are coherent and regression/Chrome/exact-tip CI checks pass.
3. Continue PB-1.4 organization-managed asset ownership/environment/criticality,
   followed by PB-1.5 versioned controls and finding mappings.

PB-1.3 remains partial. Additional source mappings and automatic reconciliation
are separate work; no generic or unreviewed upload silently inherits suppression.
No new implementation is authorized by this documentation update.

## Held and later work

- PB-0.2 pilot scope remains user-deferred. Production hosting, operations,
  security configuration, recovery and workload acceptance need their existing
  target-specific decisions and evidence.
- Broader evidence-qualified scoring rollout remains held/default-off. This is
  separate from the delivered default-On status-aware scoring policy.
- SaaS scale/load acceptance remains held; current local operation and bounded
  worker tests do not establish the requested 32/1,000-organization capacity.
- Retain the user's current search behavior; short-character indexing remains
  deferred. Delivered count reuse/seek navigation do not remove every cold broad
  search cost.
- Live AI/provider acceptance, generative integration/evaluation, Docker/model-
  cache staging and scheduled location-based imports retain their prior holds
  or Future scope.

Use [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md) for acceptance criteria and
[PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for ordering. This status update does not
close every Product Phase 4 item or confer pilot/production approval.

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
