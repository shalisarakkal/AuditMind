# PB-2.1: Open-finding remediation proof review

This increment adds a separate proof-review ledger and workflow panel for an
independent, active finding whose remediation workflow is Open. Implementation,
full local/hosted validation and local-demo activation are complete. The local
application is now at schema 0062 after a verified pre-migration backup; other
deployment targets require their own coordinated rollout.

## User flow and authority

Open a finding's Workflow, then **Remediation proof**. An organization admin or
auditor can submit an HTTPS evidence reference or a current, available
`document:<knowledge-version UUID>` owned by that organization. Supply the
observation time and submission note. Observation times must be within the last
90 days and cannot be in the future. Browser inputs use local time and are sent
as absolute instants. URLs are retained as text and never fetched by the server.
Existing knowledge-document upload, access and removal controls still apply;
this increment does not introduce a new file store or public download route.

Submission displays **Verification pending** while the workflow remains Open.
An organization administrator can approve or reject pending proof, confirming
that they reviewed the evidence and recording a reason and next action.
Self-review requires a separate acknowledgment. Rejection leaves the finding
Open and retains the reason; submit replacement proof after addressing it.
Approval also leaves workflow closure explicit. Neither action grants a scoring
exclusion. Existing scoring-evidence review remains a separate contract.

Viewers can read retained proof history. Platform read-only access does not
grant submission or reviewer authority. Unsaved workflow drafts disable proof
actions. While a proof request is in flight, the parent workflow dialog prevents
dismissal and other writes. A stale-write conflict preserves the draft and
requires an explicit reload; the client does not automatically retry a write.

## Retention and context

Migration 0062 adds one sidecar table, with no findings backfill or status-enum
change. Submissions and decisions are append-only. Each records its finding and
tenant, proof/workflow versions, reference, observation time, document hash where
applicable, submitter and reviewer identities/labels, reason, time and context.
Historical actor UUIDs and labels are snapshots; deleting an account does not
erase or reassign a proof decision. A bounded, version-cursor API exposes history.

The API serializes writes against workflow and inventory changes, rechecks the
actor's membership and account state under locks, and verifies expected proof
and workflow versions. Review revalidates the document and captured workflow,
observation count, scanner-payload publication generation and consolidation
generation. Changed context, unavailable documents or evidence older than 90
days are displayed as Stale and require a fresh submission. This is a freshness
check on a reference and retained source context, not automatic verification of
an external URL's contents.

Consolidated pairs do not accept new proof through this individual-finding flow.
An alias with remediation-proof history fails Stage A's existing independent-work
admission check, including Apply after an earlier preview. A canonical finding's
proof does not become current again after consolidation followed by Undo.

Archive/restore/purge admission blocks proof writes while an affected lifecycle
operation is underway. Finding history survives archive/restore; an archived or
hidden finding cannot accept proof through this endpoint. Purging the owning
finding/organization removes its proof through existing cascades. Database guards
reject direct history edits/deletes and mismatched tenant ownership. Downgrade
refuses retained proof data until it is exported and explicitly reviewed.

## Scope remaining after this increment

PB-2.1 is bounded to references and existing knowledge versions. New binary
artifact workflows and group-scoped remediation proof remain future work.
PB-2.2 will define/configure transition enforcement before this ledger can
authorize workflow closure. Existing legacy transitions remain user assertions;
proof approval must not be treated as automatic closure, remediation success,
compliance certification or risk exclusion.

Hosted CI passed for exact implementation commit `702ef03`, and the local demo's
backup, migration and service activation are complete. Other deployments need
their own coordinated migration. The Stage A manual acceptance, pilot/customer
approval and production/SaaS rollout holds remain deferred.


## Dependency follow-up, 20 November 2026

The pre-patch build flagged Next.js advisory
[GHSA-mfr8-8qww-v76h](https://github.com/vercel/next.js/security/advisories/GHSA-mfr8-8qww-v76h).
The installed 16.4.2 version was in the affected range. `next` and
`eslint-config-next` are now pinned to 16.4.6 with the matching lockfile; npm
installation reported zero vulnerabilities. Final post-patch audits, build and
browser checks are recorded separately from earlier feature validation below.


## Isolated verification, 20 November 2026

- Final selected PostgreSQL regression: **102 passed in 282.44 seconds**, with
  PostgreSQL required and warnings treated as errors. Covers proof submission,
  approval/rejection, replacement history, roles/tenant boundaries, acknowledgment,
  time/reference validation, stale workflow/observations/document versions,
  archive admission, immutable storage/purge, migration upgrade/rollback/drift,
  retained-data downgrade refusal and the existing workflow/scoring/consolidation
  publication regressions. This is a selected regression, not a full backend run.
- Final proof/workflow frontend regression: **22 passed** after the accessible
  dropdown-name fix. The final full frontend run passed **641 tests across 71 files in 181.44
  seconds**, with two workers and a directly confirmed process exit code of zero.
  The existing JSDOM navigation diagnostic remains stderr output, not a failed
  test; the direct runner avoids PowerShell treating it as a command failure.
- Final production acceptance build, including TypeScript, passed with Next.js
  16.4.6. ESLint, the dependency-security compatibility/amplification check and the
  high-severity Bandit gate passed. npm audit reports **zero vulnerabilities**.
- Installed Chrome passed **eight focused checks**: four common authentication
  checks and four remediation-proof scenarios. Verified real submission,
  rejection, replacement approval, unchanged workflow/scoring authority, viewer
  access, draft protection, 320px/1440px layout and Axe. Browser artifacts:
  `temp/testing/finding-workflow/phase3_browser_cb5f7a8d8112`.
- Early Chrome failures exposed a timezone mistake in the test fixture and an
  unstable dropdown accessible name. Both were corrected before the final run.
  A parallel frontend run hit worker-start timeouts; the successful bounded reruns
  are separate from that failed attempt. Earlier 17/72-test backend and 639-test
  frontend results are overlapping historical checks, not additive totals.

Local logs are under ignored `temp/pb21-*`. The pre-activation check of the
normal application returned HTTP 200 from `/health`, `/ready` and `/login` at
schema 0061. The later local activation is recorded below. PB-1.5 activation
evidence remains a separate earlier checkpoint.


## Pre-commit review, 20 November 2026

The review covers transaction admission and role/account revalidation, evidence
references and stale context, retained storage and downgrade behavior, source
lifecycle/consolidation interaction, UI drafts/in-flight writes, error recovery,
accessibility and migration/model parity.

The review corrected uncertain write recovery: network errors, malformed replies
and server errors now preserve the proof draft, explain that the outcome is
unknown and require an explicit reload before another proof write. Expected
versions already prevent duplicate records; the UI now also guides recovery.
Unit tests cover network and HTTP 503 loss. Chrome deliberately commits the real
request before replacing the response with 503, then checks that reload discovers
one retained proof. Additional backend checks exercise failed Activity receipt
rollback and a locked reviewer account. The full build also caught and corrected
two unsupported Testing Library assertion options before final validation.

Storage/security review confirmed same-tenant ownership, append-only history,
owner-lifecycle purge, indexed finding cascades, strict expected versions and
fresh account/membership checks. A separate PostgreSQL regression uses a schema
containing an apostrophe, rejects an existing foreign tenant's finding reference,
and verifies owner purge. That check is additional to the already-collected full
backend run; its result is recorded separately. Bandit's B608 heuristic on guard
DDL interpolation was reviewed: the schema is derived from the database connection
and quoted as an identifier, with no request-controlled SQL fragments. No scanner
suppression was added. The full high-severity gate passes; lower-severity findings
are not represented as zero findings across all severities.

Full backend verification exposed a pre-existing test portability issue: its
performance diagnostic requires PostgreSQL's restricted `track_functions`
setting. On roles without that permission, it now verifies that the unchanged-
identity trigger fast path precedes dependency probes, while still exercising
the 10,000-row update; privileged roles retain the runtime function-call count.
The adjusted PostgreSQL test passes without a skip. The strict full backend
suite passed **2,193 tests in 4,963.20 seconds** with `--require-postgres -W error`
and zero skips. Frontend verification passed 641 tests
across 71 files. ESLint, dependency guard, production build and npm audit all
passed. Installed Chrome passed the complete finding-workflow suite (**122
checks**) plus evidence/pilot and worker-pool acceptance. The committed-response
loss scenario was exercised against the real API; artifacts are under
`temp/testing/finding-workflow/phase3_browser_454a4724bd25`.

Python dependency checks, `pip check`, optional-embeddings audit, tracked-secret
guard and the high-severity Bandit gate passed. The new SQL identifier quoting
finding was reviewed as described above. All backend, frontend, build, browser,
dependency and high-severity security gates passed locally. The pilot script uses
isolated synthetic data and does not close deferred owner/customer acceptance or
authorize production rollout.


## Hosted verification and local activation closeout, 20 November 2026

Implementation `702ef03` passed all four [hosted CI jobs](https://github.com/shalisarakkal/AuditMind/actions/runs/44825416468): backend, frontend, browser and backend dependency audit.

Before maintenance, the local app was confirmed to use the loopback PostgreSQL
database `auditmind`, isolated schema `auditmind_demo`, revision `0061`, with no
pending/running work in the import, archive, report, document-index, evidence or
dashboard queues. Existing counts were 6 organizations, 5,608,732 assets,
5,961,209 findings and 64 scans. The guarded demo launcher stopped the API,
worker and frontend.

A fresh custom-format archive was written to the ignored local checkpoint
directory. Its archive listing and backed-up Alembic revision were verified;
the revision is `0061`. SHA-256 is
`1cabfc7c61a27b9243711a907fc43e0181666b18e99ebbb7d94cbe0e2461b785`; size is
1,523,227,334 bytes. Manifest:
`temp/auditmind-demo/checkpoints/before-remediation-proof-0062-20261121T012744Z.json`.

The guarded `python scripts/demo.py prepare` applied migration `0062` and passed
Alembic metadata drift checking. Counts remained unchanged; the new
`remediation_proofs` table is empty, its append-only guard is enabled, and its
finding index is valid. `start-demo.ps1` rebuilt the production frontend with
Next.js 16.4.6 and restarted the API, worker and frontend. API health, readiness,
login and authentication options returned HTTP 200; readiness reported database,
uploads and worker healthy. OpenAPI exposes proof read/submit/review routes.

No proof was submitted and no organization policy was changed. This activation is
for the local application only; other installations and production remain
separate deployment decisions.
