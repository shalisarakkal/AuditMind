# Dashboard evidence-qualified scoring — approved staged contract

Updated 28 October 2026. **Registry/review UI, durable background evaluation, safe
revision invalidation and opt-in Dashboard integration implemented locally. The
setting remains off by default; production/default-on rollout is not approved.**
User approved the recommended approach with a temporary setting controlling adoption.
Organization administrators approve/revoke qualifications within their organization;
auditors/viewers cannot approve or change scoring mode. Retain the existing maximum
90-day qualification policy, same-scope requirements and all-seven aggregation gate.

### Current implementation boundary

Migration 0031 adds one active durable evaluation per organization and transactional
statement-trigger evidence revisions. A worker evaluates a complete snapshot;
changed inputs supersede its result, and all later reads independently check
revision/policy/expiry and result integrity. The admin setting is now available
with expected-version confirmation/audit, but remains false by default. Dashboard
reads never fingerprint inventory or enqueue evaluations automatically.

When enabled, only current eligible domains receive baseline deterministic scores;
unqualified domains are null. The overall score is null unless all seven domains
qualify with compatible scope. Existing deductions, weights, saved reports and
risk snapshots are unchanged. Turning off restores baseline interpretation.
The browser checks cheap state every ten seconds/on focus and hides mismatched
or unverifiable scores. See [job/invalidation contract and limits](BACKGROUND_EVIDENCE_EVALUATION.md).

### Stage-two implementation history (before 0031)

Performance follow-up: inventory binding now uses explicit v2 PostgreSQL JSONB
row hashing and a compact materialized/sorted projection; old v1 bindings require
re-review. Reviewer reads stream actual batch progress from one repeatable-read
snapshot. [Measurements and remaining rollout gates](EVIDENCE_EVALUATION_PERFORMANCE.md).

Migration 0030 adds immutable inventory binding, reviewer identity, review/expiry
timestamps and explicit attestations. Admin-only review/revocation endpoints use
expected-version checks and before/after audit records. Reviews require all three
domain objectives, current organization operational sources, entire-inventory and
conflict-review attestations, and a future expiry within both review and observation
90-day elapsed-time windows. Material conflicts require two references plus a
reviewer explanation, and remain unscored. Approved records must be revoked before
editing; revoked/conflicting records may be returned to draft with cleared review
metadata and a new version.

Active findings and current, retained organization-policy KnowledgeVersion records
are supported. Shared standards, reference content kinds, unpublished/retired/purged
versions and content/hash mismatches cannot qualify. Source hashes are rechecked,
not automatically repaired. Operational adequacy and independence of contradictory
observations remain explicit human-review responsibilities, not machine-certified.

`GET /scoring/inventory-scope` binds the complete active asset/finding population
and material attributes, plus material lifecycle event history. This conservatively
invalidates approval after restore/reactivation even if final IDs/content match;
retention removing bound history also requires re-review. The fingerprint is scoped
to the organization, versioned, and computed with bounded-memory streaming.
Review provenance retains the binding version, fingerprint and population counts.
This is a cryptographic binding and scope summary, not a historical copy of every
inventory row; reconstructing deleted historical inventory needs a separately
retained export/versioned manifest before any forensic-retention claim.

`GET /scoring/evaluation` reads one repeatable-read snapshot, returning per-domain
eligibility/reasons, qualified count and complete/partial/not_assessed coverage.
Missing/stale/mutated/expired/revoked qualifications fail closed. Complete coverage
also requires compatible declared scope across all seven domains. It does not yet
calculate a new dashboard score or change saved reports. Review locks material
inventory publication and locks document parent before version, matching workers.

**Performance boundary:** fingerprinting is currently O(active inventory plus
material lifecycle history), with bounded memory but no constant-time cache. It
is not wired into normal dashboard requests. Local authenticated HTTP/concurrent
read benchmarks and two-user reviewer acceptance are complete. A safely invalidated
background/revision strategy and broader load acceptance remain required for a pilot;
do not turn every member's dashboard refresh into a full inventory scan.

Settings exposes the reviewer preview and a disabled not-yet-available scoring
control; the API still reports unavailable and rejects enabling. The local demo
is on migration 0030 with reviewer/progress checks completed. Qualified scoring
and mode-aware Dashboard integration are not activated. Migration downgrades discard new
review columns; audit events retain prior review snapshots. Existing records cannot
regain qualification without complete, current review metadata after re-upgrade.

### Stage-one implementation history

Migration 0029 adds tenant-owned settings and one versioned qualification record
per domain. GET/PATCH `/orgs/{id}/scoring/settings` returns `available=false`;
enabling returns 409 until the live evaluator/reviewer workflow is complete.
Default is off, including organizations without a stored row. This API is not yet
exposed in Settings UI and is not consulted by the existing dashboard calculation.
PUT `/orgs/{id}/scoring/qualifications/{domain}` is admin-only and saves drafts,
with expected-version conflicts, transactional role/lifecycle checks and audit
before/after records. Members can read their organization's drafts. No approve
endpoint exists; an empty or stale draft never grants qualification.

Initial draft source bindings support active findings only, using an explicit
`dashboard-finding-v1` hash projection and the existing canonical hash algorithm.
The projection includes source content, domain/severity and import/asset identity,
not workflow assertions/assignment. This is distinct from captured report hashes.
Source lookup rejects foreign/archived findings; saves verify objective/domain/hash
and actual timezone-qualified observation dates. Operational documents, immutable
inventory scope fingerprints, live invalidation/expiry, approval/revocation and
dashboard aggregation are subsequent increments, not implied by draft validation.
No existing report/provider flag or live scoring behavior was changed in stage one.

## Existing behavior and reuse

With the new setting off, the dashboard suppresses scores when active assets AND
findings are zero. Nonempty organizations use the findings-based deterministic baseline; an
unobserved domain can therefore score 100. Do not describe that as qualified coverage.

Reports already implement opt-in schema 3 qualification in
`backend/app/services/evidence_policy.py` and
`backend/app/schemas/evidence_assessment.py`. Reuse the seven profiles and invariants
in [coverage profiles](EVIDENCE_COVERAGE_PROFILES.md), not a second set of objectives.
That report pilot uses a trusted operator JSON pack, binds captured source hashes,
and supports only one organization per configured pack. It is not a scalable live
dashboard evidence registry. Do not turn on report inference or reuse an AI score
as a live deterministic dashboard score.

## Approved domain contract

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

## Temporary setting and controlled adoption

Proposed setting: **Settings → Scoring → Evidence-qualified scoring**.
It is organization-scoped, admin-only, **off by default** for existing and new
organizations. Keep it separate from ingestion options and the existing report
schema-3 flag. Do not change report-provider consent or enable inference.

| Setting | Dashboard behavior |
| --- | --- |
| Off | Existing findings-based baseline; empty-org Not assessed safeguard remains |
| On | Approved evidence qualification contract; unqualified domains and partial overall remain unscored |

The API, not the browser, selects the mode. Return effective mode, policy and
aggregation versions with every dashboard response so clients cannot confuse the
two meanings. Label off-mode scores as findings-based baseline, not qualified
coverage. An enabled mode with no qualifications shows Not assessed; missing or
invalid evidence must never silently fall back to the baseline.

Mode changes require optimistic concurrency, audit events (actor, time, old/new
mode) and refreshed dashboard data. Scope/inventory qualification checks remain
authoritative at read time. Do not permit a new-mode response to be replaced by a
late request from the previous mode/organization. A failed setting save preserves
the previous mode; stale clients must reload rather than overwrite it.

Turning the setting off is a supported pilot rollback. It preserves qualification
records, source bindings and audit history; it does not rewrite saved reports or
risk snapshots. Enabling again re-evaluates expiry, scope and source validity.
Explain the semantic change before an administrator confirms a toggle.

Expose the setting only once the qualification API, reviewer workflow and new
dashboard response are complete and tested. Shipping a switch without the actual
qualification behavior would misrepresent readiness.

### Retirement of the setting

After representative pilot organizations pass all qualification/expiry/conflict,
cross-tenant, concurrency and browser acceptance gates, review adoption and obtain
explicit approval to make qualified scoring the default. Do not automatically
enable it for every organization on deployment. First communicate/migrate the
default with retained mode/version provenance and an agreed rollback window.
Remove the switch and baseline-display branch in a later reviewed release, while
preserving legacy snapshot readers and assessment-method attribution. This design
approval does not itself authorize global activation or switch removal.

## Delivery and approval boundaries

1. Contract, organization-wide scope, admin reviewer authority and setting-gated
   pilot approved on 27 October 2026. Implementation remains staged.
2. Design tenant-scoped persisted qualification records with source bindings,
   reviewer identity, audit history, optimistic concurrency and invalidation.
   Organization administrators explicitly approve/revoke evidence. Upload permission
   alone grants no approval authority; preserve organization-membership checks.
3. Implement a shared non-inference qualification evaluator; keep report captured
   snapshot evaluation distinct from live dashboard evaluation. Existing operator
   report packs remain compatible until explicit migration.
4. Add versioned API fields, the temporary organization setting and reviewer UI using existing layouts.
   Keep raw baseline diagnostics distinguishable from qualified resilience scores.
5. Add PostgreSQL unit/integration/regression tests, API contract tests and Chrome
   acceptance before activation. No real model calls are needed or authorized.

Acceptance must cover all seven objectives/profiles; empty and asset-only orgs;
valid zero/100; missing/expired/future/hash-mismatched/truncated/archived evidence;
scope/inventory changes; contradictory observations; cross-tenant access; concurrent
approval/revocation; all/partial/no-domain aggregation; default-off and per-tenant
mode isolation; admin-only audited/concurrent toggles; rollback/re-enable expiry;
no silent fallback; out-of-order frontend responses; and legacy report retention.
Semantic adequacy and material contradictions require reviewer judgment: source
counts or two IDs alone are not proof. Invalid qualification must fail closed with
an actionable reason, not a generic server error or a fabricated score.

This contract authorizes staged local implementation and testing, not production
rollout, live inference or global default changes. Database migrations must be
reviewed and validated against isolated PostgreSQL before any local demo activation.
