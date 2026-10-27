# Dashboard evidence-qualified scoring — proposed contract

27 October 2026. **Draft for approval; not implemented.**

## Existing behavior and reuse

The dashboard now suppresses scores only when active assets AND findings are zero.
Nonempty organizations still use the findings-based deterministic baseline; an
unobserved domain can therefore score 100. Do not describe that as qualified coverage.

Reports already implement opt-in schema 3 qualification in
`backend/app/services/evidence_policy.py` and
`backend/app/schemas/evidence_assessment.py`. Reuse the seven profiles and invariants
in [coverage profiles](EVIDENCE_COVERAGE_PROFILES.md), not a second set of objectives.
That report pilot uses a trusted operator JSON pack, binds captured source hashes,
and supports only one organization per configured pack. It is not a scalable live
dashboard evidence registry. Do not turn on report inference or reuse an AI score
as a live deterministic dashboard score.

## Proposed domain contract

Return the following independently: evidence status/reason, qualification scope,
reviewed/observed/expiry instants, supporting source references, policy version,
nullable score/tier, and baseline method/version. Browser labels:

| Evidence status | Display | Numeric score/tier |
| --- | --- | --- |
| insufficient, no operational evidence | Not assessed | null/null |
| limited, or expired qualification | Insufficient evidence | null/null |
| conflicting | Review required | null/null |
| sufficient, current qualification | Existing deterministic domain score | score/matching tier |

Keep report evidence-status enums unchanged. A separate reason code distinguishes
missing, incomplete and stale evidence; do not conflate them with low resilience.
Coverage proves observations were made, not that the controls passed.

All three existing objectives must qualify for a domain, over the same declared
scope. Use actual observation dates, not file-upload dates. Follow the existing
90-day maximum review/observation rules and explicit timezone checks initially;
this is application policy, not a universal compliance interval. Invalid, changed,
archived, deleted, foreign-tenant or out-of-scope sources cannot qualify coverage.
Inventory alone, a generic standard, workflow verification notes or an absence of
findings cannot grant sufficiency. The model cannot grant qualification.

## Scope and baseline compatibility — required before implementation

A qualification must explicitly identify the inventory population/control scope
it covers. The current dashboard baseline counts all active organization findings.
Therefore only organization-wide qualification covering that population may gate
that baseline. Smaller-scope evidence remains partial; do not apply a scoped
attestation to an organization-wide score. Inventory growth or material source
changes require re-evaluation. A future scoped score requires a separately defined
scoped finding set and denominator, not silent filtering of the current baseline.

Maintain the existing deductions and thresholds for eligible domains. Adequate
operational evidence with no findings may yield 100; no evidence may not. A score
of zero remains a valid numeric score, never a missing-value sentinel.

## Overall aggregation

- All seven domains sufficient/current under one compatible scope: compute the
  existing weighted overall score and tier, with explicit aggregation version.
- Some qualified: return partial assessment, null overall score/tier, qualified
  domain scores and coverage count (for example 3 of 7 domains assessed).
- None qualified: return Not assessed, null overall score/tier and 0 of 7.
- Never replace missing domains with 0/100 or redistribute their weights.

Retain existing dashboard baseline rounding/weights unless a separately reviewed
version migration explicitly adopts report integer half-up aggregation. Historical
reports and risk snapshots remain immutable and retain their recorded method.

## Delivery and approval boundaries

1. Approve this contract, organization-wide scope rules and reviewer authority.
2. Design tenant-scoped persisted qualification records with source bindings,
   reviewer identity, audit history, optimistic concurrency and invalidation.
   Organization administrators may manage evidence; the exact role permitted to
   approve it must be agreed, not assumed from upload permission.
3. Implement a shared non-inference qualification evaluator; keep report captured
   snapshot evaluation distinct from live dashboard evaluation. Existing operator
   report packs remain compatible until explicit migration.
4. Add versioned API fields/rollout controls and reviewer UI using existing layouts.
   Keep raw baseline diagnostics distinguishable from qualified resilience scores.
5. Add PostgreSQL unit/integration/regression tests, API contract tests and Chrome
   acceptance before activation. No real model calls are needed or authorized.

Acceptance must cover all seven objectives/profiles; empty and asset-only orgs;
valid zero/100; missing/expired/future/hash-mismatched/truncated/archived evidence;
scope/inventory changes; contradictory observations; cross-tenant access; concurrent
approval/revocation; all/partial/no-domain aggregation; and legacy report retention.
Semantic adequacy and material contradictions require reviewer judgment: source
counts or two IDs alone are not proof. Invalid qualification must fail closed with
an actionable reason, not a generic server error or a fabricated score.

No production rollout, schema migration, live inference or scoring change is
authorized by this design draft.
