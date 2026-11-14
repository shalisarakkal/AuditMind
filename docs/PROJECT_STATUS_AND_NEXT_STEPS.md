# Project status and next steps

Current checkpoint (14 November): Stage B reserved publication storage is committed in `2751c3b`; full local regression verification passed. Normal schema remains `0055`; migration `0056` is not activated. Publish/Undo and its UI remain unavailable. Stage A stays default-off and manual acceptance remains deferred. See [storage review](OBSERVATION_PUBLICATION_STORAGE.md) and [hosted CI](https://github.com/shalisarakkal/AuditMind/actions/workflows/ci.yml?query=branch%3Amain). Earlier dated entries are historical checkpoints.

Updated 14 November 2026; the current checkpoint above supersedes earlier hosted
results. This replaces the pre-implementation assessment; its historical text is
retained in [the e4c7488 version](https://github.com/shalisarakkal/AuditMind/blob/e4c7488/docs/PROJECT_STATUS_AND_NEXT_STEPS.md).

## Current baseline

| Scope | Verified status |
| --- | --- |
| Committed application source | `2751c3b` storage foundation; full local verification below. Preview `531d8e9` passed all four jobs in [run 43538479642](https://github.com/shalisarakkal/AuditMind/actions/runs/43538479642). [Storage delivery CI](https://github.com/shalisarakkal/AuditMind/actions/workflows/ci.yml?query=branch%3Amain). |
| Suppression/retained-source delivery | `f97a4fbf29a728a45087f03d8dabf6ea21950d4b`; all four jobs passed in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797) |
| Recorded local schema | 0055, activated with clean drift; reserved-storage migration 0056 is not activated |
| Suppression availability | Authorized native Nessus preview/suppress/clear APIs and guarded UI are delivered; current independent identity reviews are required |
| Source lifecycle | Purge retains the minimal ledger; clear/restore refuse conflicting retained payloads, including aliases; possible reappearances stay visible until independently reviewed |
| Unchanged drafts | Save draft disabled without persisted changes; identical valid saves preserve version, timestamp, audit and evidence revision; stale/source checks remain |
| Current local validation | Full backend 1,981 passed; frontend 585 passed across 61 files; Chrome 106 checks passed; lint/build, migration/drift, performance and security scopes passed as detailed below |
| Historical overlapping scopes | Suppression: 120 expanded backend, three final indexed, 576 frontend and 103 Chrome checks. Draft-save: 54 backend and 15 component tests, lint/build. These overlap later full runs |

[Release evidence](SUPPRESSION_RELEASE_REVIEW.md),
[verification steps](EVIDENCE_USER_VERIFICATION.md),
[release gates](RELEASE_READINESS.md) and
[Phase 4 validation](PHASE4_VALIDATION.md) contain detailed scopes. The older
foundation-only and CI-pending assessment is superseded; it is not current status.

## Next engineering work

Documentation closeout reconciles CI/source/lifecycle records and checked links.
The baseline above identifies the delivered application code; this closeout
changes documentation only.

1. The reviewed [read-only foundation](CONSOLIDATION_FOUNDATION_REVIEW.md) was pushed
   through `112646f`; all four hosted Linux jobs passed in
   [run 43275574591](https://github.com/shalisarakkal/AuditMind/actions/runs/43275574591).
   Implementation `9380668` delivers schema, pair preview, reserved memberships and
   source manifests without consolidating findings or publishing payloads.
2. The [internal metadata transaction component](CONSOLIDATION_TRANSACTIONS.md) is
   the next local increment. It is not exposed through a route. Complete atomic
   visibility/revision changes, group-aware proof, source lifecycle safeguards and
   guarded UI under the [staged design](REVIEWED_FINDING_PUBLICATION_DESIGN.md)
   before enabling production publication or accepting a production write token.
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
