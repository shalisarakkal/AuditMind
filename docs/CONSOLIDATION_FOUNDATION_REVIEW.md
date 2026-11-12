# Consolidation foundation review

Review date: 12 November 2026. Local schema: `0052`.

The read-only foundation and membership/dependency schema are implemented and
reviewed. Consolidation and payload publication remain unavailable. No production
writer, visibility exclusion or new UI control is enabled. Implementation commit:
`9380668`. Hosted Linux CI must be verified for the pushed checkpoint.

## Delivered scope

- Migration `0051`: retained consolidation and decision ledgers.
- Migration `0052`: reserved current members and retained typed dependencies,
  scoped to organization/group/decision generation by composite foreign keys.
- Unique current finding membership and canonical/alias roles; unique generation
  resource references; constrained kinds and positive explicit versions.
- Bounded ledger/history reads and an actual organization-admin-only preview.
- Batched source manifests covering both original retention owners and later
  observation sources, with bounded counts and diagnostic fingerprints.

The schemas do not independently prove that referenced resources belong to an
organization, both roles exist or a generation is active. The future transactional
publisher must validate exact pair/role agreement, source ownership, authorization
and current state under locks. Metadata rows alone confer no visibility or proof
authority. No Finding columns, source ownership or existing large-table indexes
are changed by these migrations.

## Read API contract

Under `/api/v1/orgs/{org}/finding-consolidations`:

| Method/path | Contract |
| --- | --- |
| `GET` | Member-accessible retained ledger page; limit 1-100; offset 0-2,147,483,647; deterministic ordering; no exact count |
| `GET /{group_id}/history` | Member-accessible version history, bounded limit and exclusive before-version cursor; private contexts excluded |
| `POST /preview` | Accepts only `canonical_decision_id`; active actual organization administrator required; platform access alone is insufficient |

Preview opens a read-only repeatable-read snapshot. Before borrowing that
connection, the HTTP route captures the actor ID and releases its completed read
transaction. Pending ORM changes produce a conflict without rollback. The service
itself does not end its caller's transaction. Authorization is rechecked inside
the snapshot. Successful responses are no-store.

Preview validates current canonical selection, independent reviewed native Nessus
identity bindings, classification agreement, pristine alias workflow, proof and
standing-suppression conflicts, recorded group overlap and active retained source
owners. It reads at most 1,001 observation metadata records; more than 1,000 blocks
admission. Classification extraction touches only the two latest observations.
Descriptions are excerpted; full hashes are calculated in PostgreSQL. Manifest
lookups are batched and do not select raw payloads or full binding contexts.

`prerequisites_scope` is `bounded_pair_only`. Every response keeps
`apply_available` false and names pending components. A fingerprint is diagnostic,
not permission or a future write token. Other independently reviewed identity
conflicts, pending source jobs and transactional publication admission still need
validation before any writer can be enabled.

## Issues reproduced and fixed during review

1. A preview held its request connection while borrowing another. A one-slot
   pool reproduced exhaustion. Releasing only the route's completed read
   transaction resolves it; pending ORM changes are preserved. One-slot HTTP and
   four-concurrent-request/two-slot regression cases pass, with no connections
   left checked out.
2. The manifest builder relied on its caller for exact pair and identity shape.
   It now rejects wrong-pair, cross-tenant, malformed or excessive context before
   database access. Unit tests prohibit database reads on those rejected paths.
3. An out-of-range OFFSET reproduced PostgreSQL numeric overflow (SQLSTATE 22003).
   API validation now bounds the value and returns 422 for excessive offsets.

## Completed validation

| Check | Result |
| --- | --- |
| Full PostgreSQL backend unit/functional/regression suite | 1,820 passed in 1,619.89 seconds, warning-strict and PostgreSQL-required |
| Final affected backend suite | 49 passed, including the late offset guard, pool concurrency and bounded performance case |
| Frontend unit/regression | 578 passed across 60 files |
| ESLint, isolated production build and TypeScript | Passed |
| Installed Chrome workflow acceptance | 103 checks passed, including mobile/Axe and nested Dashboard presentation checks |
| Real migration up/down and metadata parity | Passed |
| Dependency consistency and warning-strict TestClient import | Passed |
| Tracked-file secret guard and final high-severity Bandit gate | Passed |

The full run began before the last offset-bound change. The final 49-case rerun
covers that change and its normal paths. These suites overlap; their counts are
not a distinct-test sum. The backend scan retains 23 medium and 12 low Bandit
findings; a passing high-severity gate is not a claim that all findings are fixed.

The initial default-concurrency frontend run had 11 worker-start timeouts and is
not counted as a pass. The clean rerun used two workers with file parallelism off.
The first full backend attempt on the HDD-backed workspace was stopped after
progress without reported failures. A subsequent attempt was restarted to pin
both application and test URLs. Neither partial run counts as a completed pass.
The successful full run used the final code apart from the late offset bound,
a fresh SSD-backed disposable PostgreSQL cluster, and both `DATABASE_URL` and
`TEST_DATABASE_URL` pinned to that cluster. No durability settings were relaxed.
Normal organization data was not used as a test fixture. Browser tests used
synthetic isolated data, separate frontend chunks and no external inference.

## Performance exercise

Three local HTTP requests per case, with about 1.2 million characters in each
finding description, produced these diagnostic measurements after the pool fix:

| Retained reviewed observations | Queries | Median seconds | Maximum seconds | Response bytes |
| --- | --- | --- | --- | --- |
| 2 | 49 | 0.0685 | 0.0787 | 7,586 |
| 1,000 | 49 | 0.3257 | 0.3431 | 7,597 |

The final rerun also passed constant-query, bounded-response and hang-guard
assertions. This is not a production SLA, cold-cache inventory benchmark or SaaS
load qualification. Lists, counts, Dashboard, scoring, import matching and
archive/restore behavior are unchanged by this foundation.

## Local activation and remaining gates

Fresh backups were made before additive schema activation and their archive
listings verified; this is not a restore rehearsal. Queues were checked idle before
restarts. Existing data and passwords were retained. Application health checks and
final source activation are recorded at the end of this document.

Before enabling writes, implement atomic membership/dependency publication,
visibility and revision invalidation for all consumers, group-aware proof, source
lifecycle guards, authorized reversible operations and guarded UI. Resource UUIDs
in dependencies are retained references, so source purge does not erase audit
metadata; active-source protection must be implemented before publication.
Organization or owning decision deletion cascades the metadata.

See [the staged design](REVIEWED_FINDING_PUBLICATION_DESIGN.md). No Apply/Undo
control exists to verify in Chrome at this foundation checkpoint.

Final local activation completed at schema `0052`. All six job queues were idle
before the restart. Health, login and authentication options returned HTTP 200;
OpenAPI confirms the live offset maximum and absence of publication routes.
The full test process exited successfully, removed its disposable database and
stopped its private PostgreSQL server. Diff whitespace checks passed. Unrelated
user deletions and untracked documents/branding files remain untouched and outside
this reviewed increment. The completed local review precedes check-in of the
implementation and documentation in scoped commits. Hosted Linux CI verification
is required for the pushed checkpoint; local results are not a hosted-CI claim.
