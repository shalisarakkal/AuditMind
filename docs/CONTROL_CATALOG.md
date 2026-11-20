# PB-1.5 - Versioned control catalog and reviewed finding mappings

Implementation `e7546a7` passed all four [hosted Linux jobs](https://github.com/shalisarakkal/AuditMind/actions/runs/43906412468). Local schema is 0061; production rebuild, service restart and HTTP/readiness checks passed. This work
does not enable AI calls, alter scoring or rewrite saved reports.

## First increment

Use the repository's already verified, pinned NIST CSF 2.0 OSCAL source. Its
source URL, rights notice and content hash travel with an immutable catalog
release. Only the 106 current outcomes are offered; 79 explicitly withdrawn entries are excluded. Stable internal control IDs identify outcomes across releases; each
release retains its own reference, title and description. Do not promote the
legacy mutable RAG documents into reviewed controls. CIS/ISO full text remains
outside this increment unless authorized source material and usage rights are
separately established.

A platform administrator explicitly installs the bundled catalog; organization
membership alone cannot change shared catalogs. Installation performs no
embedding or provider calls. Identical installation is a no-op. Subsequent
catalog editions create new releases rather than editing prior descriptions.

Organization mappings match an exact source, domain and category tuple obtained
from a finding in that organization. Empty values have exact empty semantics;
there are no wildcard or domain-wide automatic mappings. A mapping means a
reviewed relevance relationship, never a control pass or certification.

Admins and auditors can propose mappings with rationale and explicit catalog
release/control selections. Only organization admins approve or withdraw them.
Platform privilege alone grants no organization mapping authority. Proposals do
not replace the effective approved mapping until approved. Approval identifies
the exact proposal and expected rule generation; stale requests fail and retain
the user's draft. Decisions are append-only and record actor, rationale, source,
catalog release and review state. Unchanged proposals do not add generations.

No catalog installed, no approved mapping, or a withdrawn mapping is explicitly
Unmapped. A pending proposal remains distinguishable from an approved mapping.
Imports do not approve mappings. A new source/category/domain tuple does not
inherit an unrelated rule. Catalog and rule lookups use bounded queries rather
than scans or backfills of the findings table.

Mappings describe categories, not finding identity, workflow or suppression.
Archive/restore retains category rules; source purge does not silently remove a
reviewed rule or its provenance. Organization deletion uses the existing tenant
purge boundary. Prior report snapshots remain byte-for-byte unchanged; any
future report consumption must snapshot exact mapping and catalog revisions.

## Verification gates

Verify authorization and tenant separation, immutable releases/decisions,
same-release target references, stale and unchanged requests, concurrent
reviewers, pending-versus-effective behavior, explicit Unmapped states,
archive/import isolation and report preservation. Reproduce suspected defects
before fixing them. Validate migrations and query plans, guarded UI and browser
behavior, regression suites and exact-commit hosted Linux CI before coordinated
normal database activation.

## Implementation safeguards

The storage foundation is five sidecar tables in migration 0061. Catalog rows and
mapping targets are sealed to their creating database transaction; descriptions,
decisions and committed target sets cannot be edited later. Deferred integrity
checks require each current rule generation to have a retained decision, each
proposal/approval to contain 1-20 same-release controls, and approval targets to
match the exact preceding proposal. Readiness checks require the application's
own schema and enabled guards; another search-path schema cannot supply activation.

Findings pages receive small summaries using bounded rule/decision queries for
only the selected page. Detail/history pages batch catalog and target reads.
Mapping changes do not alter count/filter/sort predicates, so existing exact-count
and seek caches remain valid; new page requests load fresh mapping summaries.
No mapping-based list filter or scoring integration is added in this increment.

Initial regressions reproduced post-commit child appends, unnecessary contention
with an import actor reference lock, incomplete generations/empty approvals, and
cross-schema readiness borrowing. Their targeted fixes passed in
isolated databases; logs under `temp/pb15-*` are local evidence, not hosted or SaaS
capacity claims. Normal services have not been restarted for this work.

## Retained rule review

A rule is scoped to the organization and exact category tuple, not to the life of
its original finding. Open **Control mappings**, select **Rule ID**, and paste the
retained ID from mapping details or Activity. Administrators can propose, approve
or withdraw that rule after the originating finding/import is purged. Membership,
role, immutable tuple and expected-generation checks still apply. Read-only
members can inspect the retained decision history. Finding-based editing requires
an active primary finding; it never silently redirects an inactive finding.

## Local verification, 16 November 2026

- Full backend regression: 2,161 tests passed in 2,809.53 seconds. This run preceded
  the final retained-rule UI/API additions; the final focused regression below
  covers those additions. Counts are separate scopes, not additive totals.
- Final backend catalog, migration, performance and navigation regression:
  55 passed in 120.69 seconds. Four historical asset-context/catalog migration
  checks also passed, including upgrade, empty rollback, retained-data refusal,
  quoted schemas and model drift.
- Full final frontend suite: 632 tests passed; lint passed. The isolated Chrome
  production build includes TypeScript checking. Focused Chrome: nine checks
  passed, including actual synthetic archive/purge followed by Rule ID withdrawal,
  viewer access, history, query navigation, 320/1440px layout and accessibility.
- Final full Chrome regression passed 117 checks, including the retained-rule
  scenario. Local artifacts: `temp/testing/finding-workflow/phase3_browser_dc040cb4d3e0`.
- Bounded-query test uses 5,000 category rules and a 100-row selected page: at most
  two mapping metadata reads after readiness, and two batched catalog/target reads
  for 50 history decisions. This is a query-budget regression, not SaaS capacity.
- Suspected defects were reproduced before correction: committed child appends,
  import actor-lock contention, incomplete generations, incorrect projections,
  borrowed/miswired guards, stale navigation, unavailable labels and missing
  retained-rule operations after source purge. Final focused regressions passed.
- High-severity Bandit gate passed. Lower-severity findings remain separately
  triaged; this is not a claim of zero findings at every severity.

At the pre-delivery checkpoint, migration 0061 added five sidecar tables and guards,
without a findings/assets backfill or scoring-policy changes. Activation required that the
exact pushed commit pass all four hosted Linux jobs, services be idle/stopped,
and a verified local backup be recorded. These gates passed as recorded below. Catalog installation is an explicit
platform-admin action after activation; no actual category mapping is approved
automatically.

## Delivery follow-up, 16 November 2026

Exact implementation commit `e7546a71d8fb7efcf211dcbe17ca3e1f3dc11b46`
passed backend, frontend, browser and dependency/security jobs in hosted run
43906412468. Local maintenance completed migration 0060 to 0061 after a
verified custom-format backup (1,744,044,078 bytes; archive listing and SHA256
recorded in the ignored local checkpoint manifest). Migration/model drift,
index validity and catalog readiness checks passed. Inventory remained at six
organizations, 5,608,732 assets, 5,961,209 findings and 64 imports. The five new
tables were empty after migration; no catalog installation or mapping approval
was performed. Local artifacts remain under `temp/pb15-*` and the ignored
`temp/auditmind-demo/checkpoints` directory.

Resume verification completed: the normal production frontend rebuild (including
TypeScript) passed; API, one-slot worker and frontend restarted. `/health`,
`/ready`, `/login` and proxied authentication options returned HTTP 200. Readiness
reported database, uploads and worker healthy. Unauthenticated control-page
requests also responded successfully; these HTTP checks do not replace the
117 pre-delivery authenticated Chrome checks or deferred owner acceptance.
Existing accounts/passwords were retained. The app is available at
http://localhost:3000/login. Catalog installation remains an explicit platform-admin
action; no real category mapping was approved during activation.
