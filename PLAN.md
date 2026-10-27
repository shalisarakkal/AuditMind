# AuditMind AI — Delivery Plan

Tracks progress against the roadmap in `Blueprint.md` / `Architecture.md` (section 9).

## How this works

27 October drag/drop regression: restored page-wide Assets/Findings file intake
and guarded signed-in pages against Chrome local-file navigation. Native file
inputs/text drags remain intact; busy/unrelated-modal drops do not enqueue files.
Fresh frontend/browser evidence and local activation: docs/PHASE4_VALIDATION.md.

27 October exact-file policy: organization Ingestion setting Ask/Skip/Reimport
implemented for shared Assets/Findings uploads, default Ask. Skip is audited
without a new job; in-flight identical hashes always skip. Hash admission is
serialized in PostgreSQL. Uses existing settings JSON; no migration. Activated
locally on 27 October after approved idle-queue restart; readiness passed and data/
accounts/settings were preserved. Test evidence: docs/PHASE4_VALIDATION.md.

27 October: grouped duplicate decisions implemented for all Assets/Findings
import formats/sources. Submit later ready files, collect duplicates for explicit
selected skip/reimport, separate failures/source issues and avoid resubmitting
accepted jobs. Documents/logo single-item lifecycle semantics remain unchanged.
Latest evidence is in docs/PHASE4_VALIDATION.md; activation remains separate.

Upload presentation follow-up: queues moved into a native dialog, fixed-height
header actions, compact Detected badges and grouped expandable progress/reports.
Source changes prepared/tested separately while large demo imports run; no demo
restart/activation is included. See latest validation before activating the build.

Follow-up: shared Assets/Findings multi-file upload now offers one-click sequential
submission, fixed sources during the batch, stop/retry and explicit duplicate
confirmation. Separate file reports and existing server import behavior remain.
See the latest batch-upload validation in docs/PHASE4_VALIDATION.md; the combined
backend/branding counts below are the previous baseline, not a fresh backend run.

Previously accepted check-in scope (26 October): organization logos/header preferences
(migrations 0025–0028), approved fixed SVG assets, platform product-logo sizing,
single-brand auth presentation and shared password visibility are implemented.
Final combined-tree review/testing passed; four scoped commits were pushed
through **b91ade6**. The handoff follow-up is docs-only. Hosted CI conclusions
must be checked for the actual tip. See
[current acceptance and per-SHA CI evidence](docs/PHASE4_VALIDATION.md); the
chronological checkpoints below retain their original validation counts and are
not the current release gate. Phase 4 remains partial; production/live AI,
reconciliation/scoring policy and user-approved Future work remain separate.

### Historical delivery checkpoints

26 October follow-up: shared calendar contrast fixed; today's deadlines allowed
until browser-local end of day, newly set dates bounded by finding creation, and
invalid bulk workflow updates reject atomically. Archived/Assets/Uploads now use
Findings-style row-versus-bulk selection and fixed-target native confirmations.
Latest combined validation: 1,218 full PostgreSQL tests (deadline increment),
372 frontend tests and 37 Chrome checks (subsequent selection increment), lint
and builds passed. Relevant manuals/contracts synchronized. Commit/push now
authorized; [scope and exclusions](docs/CHECKIN_PREPARATION.md). The older
checkpoint results and "No push" statements below are historical. Broader Phase 4
and production/live-AI acceptance remain out of scope.

Step 3 (25 October): selective Findings search indexed in migration 0024; local
SA01 warm HTTP search `ssss` fell from 12.472s to 0.031s, with the first post-restart
request 2.299s; live Chrome including debounce/render 1.127s. Literal semantics,
counts and tenant isolation unchanged. Short/broad terms remain costly. Worker
metrics read-transaction leak fixed. See search performance/Phase 4 validation;
earlier "search pending" entries below are historical. Full PostgreSQL regression:
1,203 passed in 607.28s; frontend 367/lint/build and Chrome 35 passed. Demo/test
targets are at 0024 with clean checks; normal application schema not migrated.
Step 4 prepared on 26 October: [explicit check-in groups](docs/CHECKIN_PREPARATION.md),
with backend **86a1c2e** and frontend **c995e5e** committed after explicit user
approval; the third commit contains acceptance/docs and the
[Chrome walkthrough](docs/PHASE4_USER_VERIFICATION.md). Full backend
validation remains 25 October. On 26 October, approved targeted transitive
updates changed only the frontend lockfile (undici 8.12.3, zod 4.6.7). Fresh
367 frontend tests/lint/TypeScript/build, 35 workflow Chrome checks and 6 grouped
Documents checks passed; full/production npm audits zero. The dependency blocker
is fixed, not risk-accepted. No push. [Audit](docs/DEPENDENCY_AUDIT_2026-10-26.md).

Lifecycle/authorization follow-up (25 October): privileged organization writes
use transactional admission fencing with fresh role/account/lifecycle checks;
manual findings reject archiving/archived references, and bulk archives reauthorize
every committed job admission. Ten targeted real-wait PostgreSQL cases pass.
Full PostgreSQL regression: 1,201 passed in 604.85s, warnings as errors, including
all 10 new race tests. Frontend 367/lint/build and Chrome 35 passed. Search remains step 3;
documentation/check-in readiness remains step 4. No migration or real inference.

25 October multi-user increment: selected Findings disable individual row actions;
settings/profile/consent concurrency hardening added. Review/tests and remaining
cross-operation requirements: [multi-user audit](docs/MULTIUSER_CONCURRENCY.md).
This is not blanket acceptance of every multi-user operation; see Phase 4
validation for actual test counts and remaining lifecycle/authorization coverage.

25 October Findings follow-up: modal archive confirmation locks background
interaction and distinguishes one-row versus frozen bulk targets. Verified with
367 frontend tests, 84 focused PostgreSQL tests plus 17 overlapping paging rerun
tests, and 35 Chrome checks; lint/build passed. Common search query improved, but
SA01 count-phase profiling still takes about 8 seconds: indexed-search performance
work remains pending. No schema migration or paid inference was performed.

- Each phase below must have **all its tests green** before work starts on the next phase.
- "Green" means: unit tests pass, and integration tests pass (or are correctly
  skipped with a documented, agreed-upon reason — never silently broken).
- At the end of a phase, I report status here + a test run, **you verify, and
  give explicit go-ahead** before the next phase starts. No self-approval.
- Environment constraints discovered along the way (e.g. no Docker, no pgvector
  build toolchain) are recorded here with the workaround chosen, so decisions
  aren't relitigated.

## Environment notes

- **No Docker** on this machine — all local dev runs directly (venv + native
  PostgreSQL 18, installed at `S:\Program Files\PostgreSQL\18`).
- **pgvector 0.8.6** installed on PostgreSQL 18 (2026-09-27, ahead of Phase 3)
  and enabled in both databases (`backend/scripts/create_databases.sql`).
  Migration `0002_documents_pgvector.py` is applied.
- Backend tools (alembic, pytest, uvicorn) live in `backend\.venv` — activate
  it first (`.\.venv\Scripts\Activate.ps1`). `psql` is not on PATH
  (`S:\Program Files\PostgreSQL\18\bin`).
- Two local databases: `auditmind` (dev), `auditmind_test` (integration tests
  only, created/dropped tables per test run — never shares state with dev).

- **Dev database performance (found 2026-09-28):** Postgres's data is on
  `S:\Program Files\PostgreSQL\18\data`, a 5400-rpm hard disk (Hitachi
  HDS5C4040), with the default 128 MB `shared_buffers`. At ~2 GB of data
  (1.5M assets, 2.15M findings) most queries read from disk, and scattered
  reads cost ~5-10 ms each: slow counts, slow large imports. Moving the data
  directory to the SSD (C:, 299 GB free) and raising `shared_buffers` to
  ~2 GB would fix it; left as is for now (your call, 2026-09-28).
  2026-09-29: archiving and re-imports at ~5M rows ran at ~100-200 rows/s
  (one disk seek per row). What to change at each data size, the
  measurements, and step-by-step instructions for this machine:
  [docs/DATABASE_PERFORMANCE.md](docs/DATABASE_PERFORMANCE.md).

## Phase 1 — Foundations (Week 1 of the roadmap)

**Scope:** repo structure, data model, auth, basic Claude wiring.

- [x] Backend scaffold: FastAPI app, SQLAlchemy models for all 8 core entities
      (organizations, users, assets, scans, findings, risk_scores, reports,
      documents), Alembic migrations
- [x] Frontend scaffold: Next.js (App Router) + TypeScript + Tailwind, brand
      palette wired in, placeholder pages for Dashboard/Assets/Findings/Reports/Settings
- [x] Auth: register/login (JWT + bcrypt), role-based access dependency
- [x] Org selection (backend): `org_memberships` table (migration `0003`) —
      users can belong to several orgs with a role per org. `GET /orgs` lists
      the caller's orgs + role (the picker), `POST /orgs` creates one (caller
      becomes admin), `POST /orgs/{org_id}/members` lets an admin add an
      existing user. Every `/orgs/{org_id}/...` route checks membership.
- [ ] Org picker + login UI: moved to Phase 2 — the frontend has no API
      client or auth wiring yet, and that lands with the dashboard wiring
- [x] Rule-based v1 risk scoring engine (`RISL_SCORING.md` formula)
- [x] Claude smoke-test endpoint (`POST /ai/claude/test`)
- [x] CI workflow (GitHub Actions: backend pytest, frontend build+lint)
- [x] Unit tests: scoring engine (tier boundaries, deductions, weighted
      average), security (password hashing, JWT roundtrip/expiry) — **12
      passing**
- [x] Integration tests written and passing against real Postgres (auth
      register/login/duplicate-rejection, risk-score-from-seeded-findings)
- [x] Databases created (`auditmind`, `auditmind_test`), migrations
      `0001`–`0003` applied (all 9 tables, incl. `documents` with pgvector)
- [x] Integration tests for org selection (picker listing, org creation,
      cross-org denial, adding members, admin-only rules)
- [x] Full suite green: **21 passed, 0 failed, 0 skipped**
- [x] CI fixed before first run: backend job now installs `requirements-dev.txt`
      (pytest wasn't in `requirements.txt`) and runs a `pgvector/pgvector:pg18`
      service, so integration tests run in CI instead of skipping
- [x] Frontend `npm run lint` + `npm run build` pass locally
- [x] First commit, on `main` (2026-09-27)
- [x] Pushed to GitHub (private repo `shalisarakkal/AuditMind`); first CI run
      green — backend **21 passed, 0 skipped**, frontend lint + build pass
- [x] Your review + explicit approval to close out Phase 1 (2026-09-27)

**Status:** Closed 2026-09-27. All tests green locally and in CI (CI #1 on
`95440e1`: 21 backend tests passed, 0 skipped; frontend lint + build pass).

**Bugs the test suite caught and fixed during this phase** (kept here as a
record, not because they need more action):
- `passlib` + `bcrypt>=4.1` incompatibility broke all password hashing
  (pinned `bcrypt==4.0.1`)
- Enum columns (`severity`, `domain`, `role`, `tier`, `status`) were declared
  as plain `String` at the SQLAlchemy Core level, so values read back from
  the DB were raw strings, not enum members — `.value` access crashed the
  risk-scoring endpoint. Fixed with a proper `Enum(..., native_enum=False)`
  column type (`app/db/types.py:str_enum`) so DB round-trips give back real
  enum instances, matching what the `Mapped[...]` type hints already claimed.
- Alembic's default `env.py` runs all pending revisions in one transaction —
  when migration `0002` (pgvector) failed, it silently rolled back `0001`
  too. Fixed with `transaction_per_migration=True`.

## Phase 2 — Ingestion & basic risk (Week 2 of the roadmap)

**Scope:** CSV/JSON asset import, manual findings upload, dashboard wired to
real data instead of placeholder scores, login page + org picker in the
frontend (carried over from Phase 1).

Split into **2a (backend)** and **2b (frontend)**, plus **2c (import
profiles)**, added after 2a/2b were built. There is a single check-in: Phase 2
is marked complete only after 2a, 2b and 2c are done and tested.
Built with the feature-dev workflow (explore → clarify → design → implement →
review).

### Phase 2a — Backend

Design: approach C ("pragmatic balance"): one ingestion service shared by the
sync and background paths, a defusedxml Nessus parser, and per-org settings.

- [x] Asset import `POST /orgs/{id}/assets/import` (CSV/JSON): per-row report
      with line numbers; existing assets matched by hostname (case-insensitive),
      else IP (only against unnamed assets); update/skip/duplicate strategy
- [x] Findings upload `POST /orgs/{id}/findings/import`: generic CSV/JSON +
      native `.nessus`; hosts matched/created as assets; duplicates (same asset
      + source + category) skipped; Nessus Info skipped or recorded as low;
      plugin family -> domain map; each upload recorded as a scan
- [x] Files <= 10 MB processed in the request (201 + report); larger ones
      (up to 100 MB, else 413) in the background (202; poll
      `GET /orgs/{id}/scans/{scan_id}`); migration `0004`
- [x] Per-org ingestion settings `GET/PATCH /orgs/{id}/settings` overriding
      the `.env` defaults (only overrides stored; null resets)
- [x] Dashboard `GET /orgs/{id}/dashboard`, computed live
- [x] Role enforcement: viewers read-only; discover + settings + members
      admin-only
- [x] Login accepts JSON and the OAuth2 form, so Swagger "Authorize" works
- [x] Tests: 192 backend tests passing (unit: parsing, Nessus incl. XXE and
      billion-laughs files, settings resolution; integration: imports, dedup,
      background path incl. a real 11 MB file, size limits, dashboard,
      settings API, full role matrix, form login). Live smoke test against
      uvicorn passed (incl. real background import)
- Follow-up resolved 2026-10-20: ORM enum widths, email uniqueness/indexes,
  and report/document indexes match the migrated schema; `alembic check` passes.
- Known follow-up (pre-existing): `alembic downgrade` below 0002 fails, as the
  app's DB user doesn't own the `vector` extension it tries to drop
- Follow-up: a 10,000-row file takes 12–29 s to import (row-by-row matching),
  all while the page waits for files under 10 MB; batch the lookups

### Phase 2b — Frontend

- [x] API client (`src/lib/apiClient.ts`): bearer token from localStorage;
      an expired session (401 with a token) logs out and goes to /login
- [x] Login/register pages + logout; route groups `(auth)` / `(app)`, with
      a client-side guard (the JWT lives in localStorage, so no `proxy.ts`)
- [x] Sidebar org picker: remembered choice, validated against the fresh org
      list, "+ New organization"; pages remount on switch
- [x] Dashboard (live scores, top issues, recent imports), Assets table +
      Import, Findings grouped by domain + Upload (CSV/JSON/.nessus); large
      uploads poll the scan; per-row report panel; Import/Upload hidden for
      viewers
- [x] Settings → Ingestion: per-org overrides (admins edit/reset; others
      read-only), incl. the org's own Nessus family → domain mappings
- [x] Tests: Vitest + Testing Library, 45 tests (API client, auth/org
      context, guard, org picker, import button incl. background polling,
      report panel, settings panel, login/register, pages incl. viewer role);
      `npm test` added to CI
- [x] Browser E2E run against the real backend (register, import, Nessus
      upload, settings override/reset, dashboard, viewer view). Found and
      fixed: pre-hydration form submit could put credentials in the URL;
      sidebar logout off-screen on long pages; misaligned findings tables
- Out of scope, later phases: radar chart, per-asset risk score, AI
  explanation, remediation status, connector status

### Phase 2 code review (feature-dev: 3 reviewers — simplicity, bugs/security, conventions)

- [x] High: import uploads were fully received before auth ran (FastAPI parses
      the body before dependencies) — `UploadSizeLimitMiddleware` now rejects
      oversized uploads (declared or streamed) before auth; tests prove a 401
      used to come only after the whole body was read
- [x] Medium: two concurrent imports into one org could create the same host
      twice — imports into an org are serialised with a Postgres advisory
      lock (not a unique index, since the "duplicate" strategy allows repeats);
      a threaded test reproduced the race before the fix
- [x] Low: DATA_MODEL.md documents the new columns and import semantics;
      form-login test uses the shared fixture; new Nessus mapping rows start
      on the org's default domain

### Phase 2c — Import profiles (tool exports, asset type names)

Why: real exports (endpoint agents, network scans, cloud inventories) have
their own columns, and each row describes a device *and* its problems. Design:
approach C ("pragmatic") — built-in families in code, settings as data; an org
copies a profile and adjusts it. All 22 clarifying answers: the recommendations.

- [x] Import profiles: built-ins for generic assets, generic findings, endpoint
      agent, network scan and cloud inventory exports; each row -> an asset +
      its findings in one scan (`POST /orgs/{id}/imports`, form field
      `profile`); findings' source is the family, so copies dedup together
- [x] Org copies: `GET/POST/PATCH/DELETE /orgs/{id}/import-profiles` (admins
      write; members read): column names, default values, the family's rule
      settings, the profile's own type names; validated, no formula language
- [x] Rules: endpoint threats (>=1 high, >=5 critical), compliance status map,
      stale heartbeat (>7 days; ISO/US dates, day-first option); network scan
      risk-score bands, vulnerability -> domain map, risky ports, OS -> type;
      cloud resource type names
- [x] Asset type = fixed category + `subtype` (the source's own name); type
      names layered built-in -> `.env` `ASSET_TYPE_ALIASES` -> org setting;
      used by all imports and manual `POST /assets` (which now validates type)
- [x] `assets.details` (merged on re-import), `scans.profile`; migration `0005`
- [x] Import report `warnings` (never failures): loopback/reserved/multicast/
      link-local/unspecified IPs and unreadable values; `findings_created`
- [x] Frontend: "Import data" on Assets and Findings with a Source picker
      (detected from the file's columns); warnings in the report; subtype +
      expandable details on Assets; Settings: asset type names, import
      profiles (copy/edit/delete)
- [x] Tests: 404 backend (was 192), 77 frontend (was 45); sample exports in
      `temp/` and `backend/tests/fixtures/`
- [x] Real-file fixes (your 10K test files, 2026-09-28): a cloud ID alone
      identifies an asset (matching: cloud ID, then hostname, then IP; index
      on `(org_id, cloud_id)`); tags given as an object become `env:prod`;
      profile columns take alternative names (`ResourceType|Type`), and
      detection needs half a profile's fields, not all; tool profiles keep
      the file's other columns as details; "None"/"N/A" vulnerabilities raise
      no finding; the report counts warnings beyond its 1,000-row list
- [x] New built-in profile: Directory (Active Directory) export: disabled
      accounts and logins older than 90 days raise Identity & Access findings;
      type from the Type column, else the OS
- [x] All four 10K files imported through the live API with no failed rows
      (10,000 cloud resources; AD, endpoint and network exports)
- [x] Code review (3 reviewers), all fixed: the Import confirm button could
      upload twice on a fast double-click (now guarded); a blank number in the
      profile editor now names the field instead of sending a bad save; the
      profile API's response building is shared; DATA_MODEL.md and PLAN.md
      updated
- [x] Browser E2E run (separate test account, deleted afterwards) with the
      three sample exports: detection, imports, warnings, details, type names,
      copy/edit/validate a profile, re-import. Found and fixed: generic asset
      and cloud inventory profiles were labelled "Assets + findings"; a finding
      quoted an unreadable risk score; "Endpoint id" -> "Endpoint ID"; report
      tables' columns didn't line up
- [x] Asset matching by hostname + category (decided 2026-09-28): a row
      with a known category merges only into an asset of that category, so a
      server and a router sharing a name stay two assets (the report warns).
      Subtype isn't part of the match, so the same host from AD ("Server"), a
      network scan ("Windows Server 2022") and Nessus still merges. New
      `assets.type_known` (migration `0006`): false for a guessed type (a
      profile default such as endpoint agents' workstation, an unrecognised
      OS, a findings upload's placeholder); a guess matches any category and
      a known type replaces it, never the reverse. A row with no known
      category and several candidates goes to the oldest, with a warning.
      Tests: 413 backend (5 new, 4 updated to same-category repeats)

### Phase 2 sign-off

- [x] Full suite green locally and in CI (514 backend, 153 frontend; CI green)
- [x] Your review + explicit approval to close out Phase 2 (2026-09-28)
- [x] Security fixes verified (Option 2, 2026-10-08): SECRET_KEY, archived-scan 404, discovery 501, report generation 501

**Status:** Phase 2d complete (2026-10-08). All tests green; security posture improved.

## Phase 2d — Imports at scale, then data lifecycle (complete; Phase 2 signed off)

Its own phase, built with the feature-dev workflow once Phase 2 is signed off
and before Phase 3, so Phase 3's reports and documents get the same lifecycle
from the start. All parts tested and checked in with you before the next:
Phase 1 first (import progress), then Phase 3 can start.
Decisions so far (2026-09-28); the full clarifying round comes at the start of
the phase.

### Part 1 — Import progress and performance

Found 2026-09-28 with the 500K-row test files: leaving the page during a
background import loses its progress message and report, and pages load
slowly while it runs.

Decisions (2026-09-28): approach 3 (balanced); findings as one list, most
severe first, with a domain filter showing counts; search on both lists;
sidebar indicator on every page plus progress and report on the page;
"Writing rows: 120,000 / 500,000 (24%)"; everyone's running imports show,
the report only to its uploader, until they dismiss it (for good).

- [x] Progress survives navigation and refresh: `ImportsProvider` in the
      signed-in layout follows `GET /scans?tracked=true` (the org's running
      imports and the user's undismissed reports), polling while any runs;
      the Import button hands each upload to it. Sidebar indicator on every
      page; progress and report (`ImportStatus`) on the Assets/Findings page
      the import affects; `POST /scans/{id}/dismiss`. Migration `0007`:
      `scans.started_by`, `dismissed_at`, `progress` (written every 2,000
      rows through its own short session), earlier finished scans marked
      dismissed
- [x] Faster imports: `import_matching.py` indexes the org's assets and
      finding keys once per import (after the org lock); new rows go in with
      COPY, updates are gathered per asset. 500K-row AD export: 34 min ->
      37 s (12K repeated hosts, live through the API), 64 s worst case (500K
      new assets), peak memory 1.1 GB. Same matching rules and warning texts;
      the concurrency test now slows the index load instead of a per-row
      lookup. Findings got their first indexes
- [x] Assets and Findings lists paged: `{items, total}` (+ `domain_counts`
      for findings), `limit` (default 100, max 500) / `offset`, `q` search;
      findings carry their asset's hostname/IP, so the page no longer loads
      every asset
- [x] Tests: 430 backend (17 new), 84 frontend (7 new). Browser E2E
      (throwaway account): 500K import started on Assets, left for the
      Dashboard, reloaded on Assets mid-import (progress recovered at 70%),
      report shown on Assets and Findings, dismissed
- [x] Code review (3 reviewers, 2026-09-28), every finding reproduced first,
      then fixed and re-checked against its reproduction:
  - High: a manually added finding could point at another org's asset, and
    the findings list then showed that org's hostname/IP. Now 422 for a
    foreign asset_id/scan_id, and the list only joins the org's own assets
  - Medium: overlapping polls let an older response undo a newer one (a
    finished import flipped back to "running", lists reloaded twice, a
    dismissed report could return). Now one poll at a time, older responses
    dropped, dismissed reports never re-shown; polls use the light
    `?active=true` list and fetch reports only when an import starts or ends
  - Medium: a failure to save progress failed the whole import; now logged
    and the import carries on
  - Low: a failed status fetch after an accepted upload showed as an upload
    error (now followed by polling); an old upload error stayed after a new
    file or Cancel; the COPY cursor wasn't closed; the sidebar linked tool
    exports to Assets even when started from Findings
  - Behaviour change, verified: the committed code could create a duplicate
    asset when an earlier row in the same file gave a host its IP (updates
    weren't visible to later rows); the rewrite fixes it. Old vs new
    compared on 1,230 random files: identical once that is accounted for
  - Incident: the review's scratch tests ran outside backend/, `.env` wasn't
    found, and the test fixture fell back to DATABASE_URL, dropping the dev
    database's tables (data not recoverable; schema recreated with
    migrations). Tests now only run against a database named *_test, and
    the skip message no longer prints the database password
  - Tests: 433 backend, 91 frontend
- [x] Dashboard speed (reported 2026-09-28 after re-importing: 24,300
      findings): it loaded every finding (7 MB of raw_data) to count them,
      and sent the recent imports' full reports. Now the database counts per
      domain and severity (`count_org_findings`, also used by POST
      /risk/score), the top 5 come from one ordered query, and recent imports
      carry their counts without the error/warning lists. 1.1 s -> 0.04-0.13 s,
      521 KB -> 6 KB, same scores, tiers, counts and top findings on that data
      (justifications now list the most severe first)
- [x] Findings search also matches the asset's hostname or IP, partially and
      in any case (reported 2026-09-28: "DEV-122" found nothing); it
      searched only description and category before
- [x] Column sorting and filtering on Assets and Findings (requested
      2026-09-28), all on the server so they cover every page. One column
      sorted at a time (header click: ascending, descending, default; blanks
      last either way). A filter row under the headers: pick-lists (several
      values; "(blank)" for none) for type, subtype, environment,
      criticality, severity, domain and source, their values from
      `GET /assets/facets` and `/findings/facets`; "contains" boxes for
      hostname, IP, tags, finding and asset. Filters combine with the
      search box; "Clear filters". Sort, filters and page live in the page
      address (refresh, Back, shareable). Findings gained an "Added" column
- [x] The search box searches every shown column but the date (requested
      2026-09-28): assets by hostname, IP, type, subtype, environment,
      criticality, tags; findings by finding text, category, asset, source,
      severity, domain. Type and domain match the labels on screen
      ("network dev", "mgmt"); the server keeps a copy of those labels
      (frontend/src/lib/domain.ts), which must change together
- [x] Cloud resources visible in the lists (2026-09-28): Assets has a Cloud
      ID column (sort, "contains" filter, search; long ARNs shortened with
      the full value on hover); a finding's asset falls back to its cloud ID
      when it has no hostname or IP, and the Findings asset search, filter
      and sort include it. Before, a resource known only by its cloud ID
      showed as "—" everywhere
- [x] Large JSON files get their source detected (reported 2026-09-28:
      cloud_assets50K.json, 8.4 MB, failed every row as a generic asset
      list): detection skipped JSON over 5 MB, so the picker stayed on the
      page's generic source. It now reads the first record from the file's
      first 256 KB, at any size. And a generic import where no row had a
      hostname, ip or cloud_id column now says so, pointing to the tool's
      own source. 50K cloud records import in ~5 s
- [x] Follow-up with the real file (S:\AuditMind-Scratch\TestData\
      synthetic_assets_50K\cloud_assets50K.json, 26 MB): the retry still ran
      with the page's old code (a hard refresh was needed), and 7,091
      "LoadBalancer" rows would have failed under any source, as type names
      matched "load balancer" only with a space. Type names now match
      ignoring case, spaces, '-' and '_'; the wrong-source note also shows
      when other errors are mixed in. The real file: 50,000 created, 0
      failed, 6.8 s
- [x] Progress for every stage of an import (2026-09-28; reported: 500K-row AD
      and network scan imports sat at "100%" for a long time): the count
      covered file rows only, then a tool export's ~430-500K findings were
      written unshown. Now: "Reading file: n / N rows", "Waiting for another
      import into this organization to finish…" (a second import queued
      behind the org lock), "Writing rows", "Writing findings: n / N",
      "Saving…". Real AD 500K file (500K assets, 427K findings): reading
      23 s, assets 35 s, findings 54 s, saving 1 s. The repeated-row check
      now skips assets listed once (5 s -> under 1 s at 500K rows)
- [x] Imports load only what the file can touch (2026-09-28; reported: even a
      10K-row file was slow): every import loaded the org's whole inventory
      first, ~27 s and ~1.8 GB at 1.5M assets / 2.15M findings. Now a file
      naming up to TARGETED_LOAD_MAX (2,000) identifiers loads just the
      matching assets and their findings (1,000-row file: 0.1 s); larger
      files load the whole org in one sequential pass, which the dev
      database's hard disk handles far better than thousands of lookups
      (10K-row file: ~37 s). Same results either way: old-vs-new comparison
      identical on 823 random files for each path
- [x] Findings list at 2.15M findings (2026-09-28; reported slow: 27-76 s a
      page): it sorted every finding, whole rows with their raw data, to
      show 100. Now it finds the page's ids first, then fetches just those
      rows: the default order walks ix_findings_org_severity_created one
      severity at a time (skipping whole severities by their counts), date
      order walks ix_findings_org_created, other orders sort ids only; the
      asset join is skipped unless a search, asset filter or asset sort
      needs it. First page 0.5 s, date order 0.4 s, severity/domain filters
      0.3-0.5 s; page 50 2.3 s, row 300,000 ~7 s
- [x] Second code review (3 reviewers, 2026-09-28) of everything above since
      the first; every finding reproduced first, then fixed and re-checked:
  - Medium: large-file detection took the first "[" in the file, so a JSON
    object with another list before its records ({"errors": [...],
    "records": [...]}) was read from the wrong record, which could now
    disable Import for a valid file. It now finds the records list as the
    server does: the file's own list, else "records"/"assets"/"findings",
    else the first top-level list (nested or quoted brackets ignored)
  - Medium: switching org kept the previous org's sort, filters and page.
    The address now names the org (org=); another org's view starts clean,
    and an older link without one is stamped on opening
  - Low: "Clear filters" was undone ~300 ms later by a filter still being
    typed; it now also drops typing not applied yet
  - Low: a link to a page past the end showed "Showing 201-50 of 50"; the
    pager now moves to the last page
  - Low: the reading stage's progress stopped short of 100%; it now reports
    after each batch and the final count
  - Wording: .env.example said every left-out setting has a default;
    TEST_DATABASE_URL has none (tests are skipped)
  - Tests: 448 backend, 110 frontend
- Later: "contains" search over millions of rows reads everything (17 s for
  "DEV-12" at 2.15M findings). Fix: pg_trgm text-search indexes on the
  searched columns, weighed against their cost to imports and disk
- [x] Dashboard at 1M assets / 925K findings (2026-09-28): 0.72 s -> ~0.5 s.
      The top 5 findings come from one small query per severity on a new
      index (migration 0008, ix_findings_org_severity_created) instead of
      sorting every finding. Trade-off: that index makes writing findings
      ~25% slower (+11 s for 427K findings). The rest is counting the org's
      findings and assets (~0.4 s at this size); keeping running totals
      would be the next step if it matters
- [x] Unrecognised files are flagged (2026-09-28, after the Azure activity
      log failed silently as a generic asset list): picking a file whose
      columns match no source shows a note listing them, before Import; and
      a generic import that brings in nothing, from a file with none of the
      hostname/ip/cloud_id columns, says the file doesn't match the source
      (whatever error the rows hit), naming its columns. A correctly shaped
      file with bad values gets no such note
- [x] Import is disabled when the selected source can't read the file
      (2026-09-28): the file has none of the columns that source identifies
      hosts by (generic: hostname/ip/cloud_id; tool sources: their own names,
      e.g. ResourceID, DeviceName), and the source supplies no default.
      Switching to a source that can read it re-enables Import; if none can
      (a file no source knows; event logs have sources since Phase 2f), the
      note says so and Cancel is the way out. Judged per
      selected source, not by auto-detection, so a minimal generic file
      (type,hostname: too few columns to be detected) still imports
- [x] `backend/scripts/split_json.py` (2026-09-28): splits a large JSON import
      file into ~40 MB parts, reading one record at a time (a 264 MB,
      500K-record cloud export: 5 parts in 8 s, 22 MB of memory). Stopgap
      until imports read large files in chunks (Phase 4). Measured: a 42 MB
      part (108K cloud records) imports in 15 s at ~450 MB peak; memory
      follows the record count more than the file size
- Later (Phase 3): cloud misconfiguration findings from cloud inventory
  imports (stopped/public/unencrypted resources raise nothing today), and
  provider/region as filterable columns rather than details
- Known: the frontend test "edits the org's own domain mappings" failed once
  in 5 full-suite runs (never in 12 runs alone); likely a tight wait under
  load, to watch in CI
- [x] Open questions answered (2026-09-28): import reports stay readable by
      every org member through the API (the tracker still shows a report
      only to its uploader); no duplicate cleanup needed, as there's no other
      database with data from before the rewrite
- [x] Your sign-off (2026-09-28): committed as a586bb1, CI green, Part 2
      started
- Later: background imports in a separate worker process and scans left
  "running" by a server restart (now Phase 2d part 3); progress during
  the reading phase (~20 s of "Reading file…" for 500K rows). Reading large
  files in chunks (a 500K-row file peaks at ~1.1 GB while it's read and
  checked whole) moved to Phase 2f, which needs it

### Part 2 — Data lifecycle: archive, restore, purge (uploads, assets, findings)

Decisions (2026-09-28; all as recommended). Organization archive and purge
moved to Phase 2e, since only the Sysadmin will create and remove orgs.

- [x] Archive manually (never automatically): an upload (its scan, report and
      findings, and the assets only it uses), an asset (with all its
      findings), or a manually added finding. Imported findings aren't
      archived one by one (a re-import would re-create them). Archived data
      leaves every list, count, score, search and import match
- [x] Record which uploads touched each asset, from now on (an asset-upload
      link written by every import). Existing data is linked backwards through
      findings where possible; assets from earlier asset-only imports stay
      unlinked (archive them individually, or with the org)
- [x] Changes an upload made to assets it shares with other uploads (e.g. an
      environment or details) stay when it's archived: they can't be reliably
      undone
- [x] Each archive action is a batch: restoring brings back exactly what it
      archived. Restore any time until purged. Archived findings don't count
      for duplicate checks; on restore, one that now duplicates an active
      finding is purged instead (the restore report says how many)
- [x] Purge (permanent) only from the archive, admins only; a purge log keeps
      what, who, when and how many rows
- [x] Auto-purge `ARCHIVE_RETENTION_DAYS` (default 180) after archiving, set
      in `.env` and overridable per organization; each archived item shows a
      countdown ("Deleted in 173 days"). Runs daily in the worker, plus a
      command for Task Scheduler/cron
- [x] Large archives, restores and purges run in the background with progress
      in the import tracker ("Archiving… 120,000 / 500,000"); set-based SQL
      throughout (1.5M assets / 2.15M findings on the dev HDD)
- [x] Who: archive and restore, admins and auditors; purge, retention and the
      purge log, admins; everyone sees the Imports and Archived pages
- [x] Pages: a new Imports page (every upload, with Archive); Archive on asset
      and manual-finding rows; a new Archived page (tabs: Uploads, Assets,
      Findings) with the countdown, Restore and (admins) Purge; retention and
      the purge log under Settings
- [x] Repeat-upload warning: store each upload's SHA-256 content hash;
      uploading a byte-identical file (from anyone in the org; failed and
      archived uploads don't count) warns "already imported on <date> by
      <user>" and only proceeds when the user confirms. Warn, never block

Design (2026-09-28, option C "balanced" of three proposals, approved):
- Rows stay in place with `archived_at` + `archive_batch_id`; new tables
  `archive_batches` (one per archive action, with a finished flag so an
  interrupted archive resumes), `asset_scans` (upload-asset links, written by
  every import, backfilled from findings), `archive_jobs` (background
  archive/restore/purge, same progress shape as scans, shown in the import
  tracker) and `purge_log`; `scans.content_hash`
- Hot indexes become partial (`WHERE archived_at IS NULL`) so lists, the
  dashboard and import matching cost the same however much is archived
- Every read path filters `archived_at IS NULL` explicitly next to its org
  filter; one test per read path proves an archived row never shows
- Large jobs run in chunks of 20,000 rows, each its own short transaction
  under the org import lock, so an import waits seconds, not minutes
- Restore: a restored finding that duplicates an active one (finding_key) is
  the one purged; the active finding is never touched
- One-time migration cost on the dev HDD (backfill + index rebuild) is
  measured on a copy before it runs on the dev data

Built and measured (2026-09-29): migrations 0009 (99 s on the dev data, on
the hard disk) and 0010 (219 s, SSD). On the SSD, archiving a 1.23M-finding
upload takes 3-4 min, restoring ~3 min, purging ~2 min. Speed fixes found on
the way: a restore statement that made Postgres recheck the whole batch for
every chunk, and stale statistics after bulk changes (ANALYZE now runs before
a restore's findings and after large jobs). Buttons show the job's state
(Archiving…, Retry archive, Undo) instead of notes.

Review (3 reviewers, every finding reproduced; 2026-09-29):
- [x] High: archiving an upload took an asset it only matched, when the
      asset was newer than the upload (e.g. added by hand while the upload
      waited). Fixed: asset_scans.created, recorded by imports (migration
      0010; existing links keep the time-based guess)
- [x] Medium: two requests at once (double click, manual purge during the
      daily purge) could start two jobs on one item, and a purge could
      delete findings a restore had just brought back. Fixed: a job-start
      lock per org (separate from the import lock), and purge deletes only
      rows still archived
- [x] Medium: Undo of a large stopped archive was sized at 1 row and ran in
      the request. Fixed: sized by counting its archived rows
- [x] Low: startup marked every running archive job failed, wrong once
      several processes run: resolved in Part 3 with per-job heartbeat/ownership checks
- [x] Low: a restore's "findings kept with their asset" count is now shown;
      the empty-list row spans the viewer's columns; one polling helper for
      both trackers; retention field edit/save/reset tested
- 474 backend + 135 frontend tests pass
- [x] Your sign-off (2026-09-29): committed as e748b25, CI green (CI #7)

### Part 3 — Background worker (signed off 2026-09-30)

Brought forward from Phase 4 (2026-09-29). With the database on the SSD,
imports run ~15x faster (~1,500 findings/s, was ~100), and the web server
became the bottleneck: background imports and archive jobs run inside the
API's own Python process, so while one runs every request waits for it
(measured: 2-3 s per request, even ones returning nothing; pages take
several seconds to switch). Started 2026-09-29; decisions 1-7 as
recommended:

- [x] A separate worker process runs imports, and archive/restore/purge
      jobs; the web server only records the job and answers requests
- [x] The queue is the database itself (the scans and archive_jobs rows,
      claimed with `FOR UPDATE SKIP LOCKED`): no Redis or other new service
- [x] Uploaded files waiting for the worker are saved in `backend/uploads/`
      (configurable; excluded from git) and deleted once imported, instead
      of held in the web server's memory (4 GB for six queued files)
- [x] Files up to IMPORT_SYNC_MAX_BYTES (10 MB) still import during the
      request (instant report); larger ones go to the worker
- [x] One worker, oldest job first (imports into one org already take
      turns); a setting for more later
- [x] Its own window ("AuditMind worker"), plus `start-dev.ps1` opening the
      backend, worker and frontend windows; the web server keeps working if
      the worker is down: jobs show "Waiting for the background worker…",
      and the app warns when the worker hasn't checked in for a minute
- [x] An import cut off by a restart is started again automatically from its
      saved file, once (imports are all-or-nothing, so nothing half-saved
      exists), then marked failed; archive jobs resume as today
- [x] The daily auto-purge runs in the worker

Activity: AuditMind's own event log (requested 2026-09-29; not Phase 2f,
which imports other tools' logs). All as recommended:

- [x] Recorded (every action that changes something or matters for
      security; not page views): sign-in (login, failed login, logout,
      registration); data (imports started/completed/failed with counts,
      archive, restore, Undo, purge incl. auto-purge, repeat upload imported
      anyway, asset or finding added by hand); settings (ingestion and
      retention changes, import profiles created/edited/deleted); people
      (member added; Phase 2e adds user created, role changed, removed,
      deactivated, password changed/reset); system (auto-purge, worker
      started/stopped, event clean-up). Reports and AI runs in Phase 3
- [x] Each event: what, the item, who ("System" for automatic ones), start
      and end time, duration, outcome (completed/failed/stopped), counts,
      criticality
- [x] Criticality: Info (clean import, archive, restore, Undo, sign-in);
      Warning (import with failed rows, job failed or stopped, duplicates
      purged on restore, repeat upload imported anyway, failed login);
      Critical (any purge; in 2e admin role changes, password resets, users
      removed)
- [x] An Activity page (sidebar): newest first, paged, filters by type,
      user, criticality and date; a "Recent activity" list on the Dashboard
- [x] Every member of the org sees it, read-only; no one edits or deletes
      events
- [x] Kept EVENT_RETENTION_DAYS (default 365; per-org override), then
      deleted by the worker's daily job, which records how many it deleted.
      Safety net instead of a hard cap (a flood of events must not push
      real history out): past ~1M events in an org, admins are warned and
      the oldest Info events go first; Warning and Critical kept for the
      full period
- [x] The purge log becomes part of Activity (Settings' purge log replaced
      by Activity filtered to purges; its entries carried over); existing
      uploads, archives and purges get events from their records, so
      Activity isn't empty on day one

Design (2026-09-29, "combined" of three proposals, approved):
- Queue = today's scans (uploads waiting for the worker) and archive_jobs
  rows; `python -m app.worker` claims the oldest with FOR UPDATE SKIP
  LOCKED. A request that runs a small job itself claims it the same way,
  so the worker never runs it twice
- A thread in the worker updates worker_status and the running job's
  heartbeat every ~15 s (the main loop is busy inside a long import); a job
  with no heartbeat for WORKER_STALE_SECONDS is dead: an import is retried
  once from its saved file, an archive job carries on (up to 3 times)
- Large uploads are streamed to backend/uploads/ and hashed as they stream;
  the import's kind and format come from its scan type and file name
- One event per action, written when it ends (start and end time), in the
  same transaction as the change; never updated. Failed logins go to each
  org the account belongs to (an unknown email only to the server log);
  worker start/stop events are shown to every org
- Migration 0011: heartbeat and retry columns, worker_status, events (with
  a backfill from scans, archive jobs and the purge log), purge_log dropped

Consistent list pages (requested 2026-09-30, for every page from now on):
- [x] One layout for Assets, Findings, Imports, Archived and Activity: header
      with the count and main action, toolbar with "Search all columns",
      every column sortable, a filter row under the headers (contains boxes
      for text, pick-lists for fixed values), who and when as separate
      columns, status and criticality badges, row actions right-aligned (red
      for purge), the same empty/loading messages. Shared pieces in
      frontend/src/components/ListPage.tsx; the rules, and a checklist for new
      pages, in docs/UI_CONVENTIONS.md (read by every session through
      frontend/CLAUDE.md)
- [x] Activity shows how long an action waited for the worker and how long
      it ran ("waited 15 min, took 1 min 24 s"): scans and archive_jobs
      record run_started_at (migration 0012, which also drops the zero
      counts of the events carried over)
- [x] Import counts say what they count ("900 assets created, 2,792
      findings created, 4,990 duplicate findings skipped"), in Activity, the
      Imports page and the import report (migration 0013)

Review (3 reviewers, every finding reproduced; 2026-09-30). Security: no
Critical or High (no cross-org leak in Activity, no injection, upload paths
never from file names).
- [x] Medium: an import run by a request, waiting over 30 min for the org's
      lock, was taken for dead (a false failure, then completed: two events).
      Fixed: whoever runs a job holds its own lock (org_lock.job_running);
      the worker reaps only jobs nobody holds (also covers auto-purge jobs)
- [x] Medium: an interrupted import (second Ctrl+C, database down) deleted
      its saved file, so it couldn't be started again. Fixed: the file goes
      only once the outcome is saved; a lost file has its own message
- [x] Medium: any error outside a job (database restarting, a folder in
      uploads/) stopped the worker for good. Fixed: each loop step carries
      on after a pause (up to a minute); the sweep deletes files only
- [x] Medium: the generic findings profile's imports were counted as assets
      created. Fixed in the backend, frontend and history (migration 0014)
- [x] Medium: migration 0013 run again wiped counts. Fixed: names it doesn't
      map are kept
- [x] Medium: an old link with a sort but no order showed ascending while the
      list came newest first. Fixed: the order shown is the order asked for
- [x] Medium: UI_CONVENTIONS promised date filters that Findings, Imports and
      Archived lacked. Added (DateRangeFilter; since/until in paging.py)
- [x] Low: the safety net couldn't trim a flood of failed sign-ins (Warning).
      Now: oldest Info events, then oldest failed sign-ins; other Warnings
      and all Criticals kept for the full period
- [x] Low: failed imports carried over lost their error message; duplicate
      purges carried over twice. Fixed in migration 0014
- [x] Low: notes on closing the worker's window; a leftover type removed
- [x] Intermittent frontend tests: a real race (the map editor and the
      retention field reset themselves just after first showing, dropping a
      row added at once) fixed; test waits raised to 3 s for busy machines
- [ ] Low, Phase 4 hardening: uploads folder permissions (inherited from the
      user's folder on Windows)

After the review (requested 2026-09-30):
- [x] Archived page in the Findings style: one list, "All" by default, chips
      Uploads / Assets / Findings with counts (FilterChips, shared with
      Findings), a Type column (sortable, pick-list); API `type` (any of)
      and `type_counts`
- [x] Words: Upload (a file sent in) vs Import (collected by a connector,
      later); the Imports page is now Uploads (/uploads; /imports
      redirects), "Upload file", "Processing big.csv…", Settings' Import
      profiles are File formats, Activity's "Import" reads "Upload". Rules in
      docs/UI_CONVENTIONS.md; code and API names unchanged
- [x] A small archive, restore or purge (done during the request) now shows
      "Archiving…" (disabled) from the moment it's confirmed, then
      "Archived" until the list reloads; before, the button didn't change
- [x] Several at once (option a, 2026-09-30): checkboxes on Uploads, Assets,
      Findings (hand-added ones) and Archived, "select all on this page",
      kept across pages (cleared when a filter changes; at most 500);
      Archive selected / Restore selected / Purge selected (admins), each
      confirmed. POST /archive-jobs/bulk queues one job per item (one
      archived entry and one Activity event each, as by hand) and lists the
      ones it couldn't start. Each row shows "Queued…", then its own
      progress; past 3 jobs the job panel sums up (the one running, how many
      queued, one result with Dismiss all), and the sidebar lists 3 and
      "N more"
- [x] Pages slow to switch (e.g. Archived to Activity): every API call
      waited ~2 s, because `localhost` is tried over IPv6 first on Windows
      and the backend listens on IPv4 only. The frontend now calls
      127.0.0.1 (default and .env.example): 2.0 s per call became 0.02-0.06 s
- Committed c5872fe; CI #8 failed on one test: Linux Postgres sorts text
  language-aware (ignores punctuation: bad.csv before b.csv), Windows dev
  character by character. Kept the database's own sort order (it's what
  production does, and it keeps sorting indexed: hostname over 2M assets
  instant, 0.63 s if forced to byte order); the test's names now sort the
  same either way (6d487f1). Dev and production can differ only in how
  punctuation sorts
- CI #9 green on 6d487f1 (2026-09-30)
- **Signed off 2026-09-30** after your verification (guide steps 1-6; step
  4: active_directory500K.csv cut off while writing, restarted from its
  saved file and completed, 10,800 created / 489,200 updated). Fixes from
  verification in baad36e; pushed with e5aab0a (CI #10, result to confirm
  on GitHub). Next: Part 4 (review fixes), then Phase 2e
- 509 backend + 144 frontend tests pass; lint, typecheck and build pass
- [x] Only jobs that are really dead are marked failed at startup (review of
      Part 2, finding 4): today every starting process fails every running
      archive job, correct with one process but wrong once the worker and
      web server (or several workers) run side by side. A heartbeat per job
      (updated with each chunk's progress) and "no heartbeat for N minutes"
      instead
- [x] The import tracker and pages unchanged: same status, progress and
      reports
- [x] Found in your verification (2026-09-30): the worker stopped in the
      middle of a 500K import (reading, 24%) and the app gave no warning;
      the upload stayed "running" with its progress frozen. The warning only
      looked at jobs waiting to start. Now scans and archive jobs show
      heartbeat_at (set only by the worker), and the warning also covers
      jobs the worker is running. While the worker is down, every job
      waiting for it or cut off by it reads "Interrupted: the background
      worker stopped." plus what happens when it's back (waiting: starts;
      an upload cut off: starts again from the beginning; an archive job
      cut off: carries on where it left off). Shown in violet with ⚠ (the
      card, its sidebar entry and the sidebar alert), so it stands out from
      running (cyan), failed (red) and report warnings (amber); rule in
      docs/UI_CONVENTIONS.md)
- [x] Auto-purge is low priority (requested 2026-09-30, after an upload
      waited 1 min 23 s behind 4 auto-purges): the worker's daily run ran
      every expired purge itself before looking at the queue. Now it only
      queues them (by System), and the worker takes them when no upload or
      job someone started is waiting; once one has waited
      AUTO_PURGE_MAX_WAIT_MINUTES (default 60), it takes its turn by age
      like any other job, so a busy queue can't put it off for ever. A job
      already running is finished
      first (a purge of 500K rows: ~1-2 min). scripts/purge_expired.py
      still purges at once. While its purge waits, an expired item can't be
      restored ("Another archive, restore or purge … is already running")
- [x] Measured: page requests while a 500K-row import runs (target: as fast
      as with nothing running). 2026-09-30, network_scan 500K file (500K
      assets, 498K findings, ~5.5 min in the worker), all 8 calls a page
      load makes, timed over and over, median per round:
      - The web server is no longer blocked: uploads, archive, events,
        import tracker and worker status stay at 5-10 ms throughout (were
        2-3 s each before the worker)
      - Other orgs unaffected: an org with 500K assets and findings, 2.7 s
        per round idle, 3.1 s during the import
      - The importing org's own Dashboard/Assets/Findings slow down while
        its rows are being written (~0.1-1.1 s, peaks 2.5 s; up to 7 s in
        the first run): the import is one transaction, so their counts step
        over the not-yet-saved rows. That's about what those pages cost once
        the rows are in (next point); nothing is blocked. Met
      - Found: an org with 500K assets and findings is slow with nothing
        running: Dashboard 1.2 s, Assets 0.75 s, Findings 0.7 s, almost all
        of it exact counts. Tracked in Phase 4 (estimated counts)

### Part 4 — Review fixes (CoPilotReview.md; signed off 2026-10-01)

External review of the repo plus the uncommitted import-report change
(2026-09-30). All 8 findings checked against the code and confirmed
accurate; it found no defect in the import-report change itself. Where each
one goes:

| # | Finding | Severity | Decision |
|---|---------|----------|----------|
| 1 | Archived upload still readable/dismissable by ID | Medium | Fix here |
| 2 | Asset discovery answers 202 but does nothing | Medium | Fix here |
| 3 | Report generation answers 202, job never runs | Medium | Fix here (stopgap); real job in Phase 3 |
| 4 | Built-in default `SECRET_KEY` accepted | High | Fix here |
| 5 | `/health` checks nothing | Medium | Phase 4 (with hosting) |
| 6 | Claude calls unbounded (timeout, retries, quotas, cost) | Medium | Stopgap here; built into Phase 3 |
| 7 | Sign-in token in `localStorage` (readable by XSS) | Medium | Phase 2e (sign-in is reworked there) |
| 8 | Unpaged lists: `GET /scans` (no filter), `GET /reports` | Medium | Scans here; reports in Phase 3 |

- [x] 1: `GET /scans/{id}` and `POST /scans/{id}/dismiss` answer 404 for
      an archived upload (it stays reachable from Archived). Tests for both.
      Needed before the new "open a past upload's report" goes out
- [x] 2: `POST /assets/discover` answers 501 Not Implemented until a
      connector exists
- [x] 3: `POST /reports/generate` answers 501 until Phase 3 wires the real
      job (through the worker queue); no more `pending` reports that never
      finish
- [x] 4: The server refuses to start with the default key or one shorter
      than 32 characters, with a message saying how to generate one;
      `.env.example`, CI and the test setup get their own. Documented: a
      new key signs everyone out. Done: checked when the web server and the
      worker start (`check_secret_key`; alembic and scripts unaffected);
      `.env.example` ships an empty key; tests set a random one (CI needs
      nothing); your local `.env` got a random key (2026-09-30)
- [x] 6 (stopgap): the Claude smoke test (`POST /ai/claude/test`) gets a
      timeout and becomes admin-only; provider errors come back as a clear
      502/503, not a 500. Done: CLAUDE_TIMEOUT_SECONDS (60) with 2 SDK
      retries; admin of some org (until Phase 2e ends public sign-up,
      anyone can be that by registering); 503 no key / key refused / busy
      / unreachable, 504 timeout, 502 other errors
- [x] 8: `GET /scans` without `active`/`tracked` (the app doesn't use it)
      removed, or paged like the other lists. Done: removed (400 pointing
      to `GET /uploads`, which is paged)
- [x] README's Status still says "Week 1 foundation" (CoPilotSuggestions,
      2026-09-30): bring it up to date (Phases 1-2d done, what's next), with
      a pointer to PLAN.md for the detail. Also: setup now covers the
      required SECRET_KEY, the worker and start-dev.ps1; says Docker
      Compose is out of date (no worker); RISK_SCORING.md typo
- [x] Retry a failed upload without uploading it again (from Part 3
      verification, 2026-09-30: an upload cut off twice failed and its
      saved file was deleted, so the only way on was to upload it again).
      A large upload's file waits in `backend/uploads/<scan id>.upload`
      (UPLOAD_DIR) and today is deleted as soon as the outcome is saved.
      Keep it for a while after a failure (e.g. 7 days, a setting; the
      worker's daily clean-up deletes it after that), and add a Retry
      button on the failed report and on Uploads, for the uploader and
      admins: it queues the same file again as a new attempt. Not for
      files rejected as unreadable (retrying can't help). Small uploads
      (processed during the request) aren't saved, so they have no Retry.
      Done: a failure that isn't the content's (summary "error": cut off
      twice, an unexpected error) keeps the file UPLOAD_KEEP_FAILED_DAYS
      (7); scans show `retryable`; `POST /scans/{id}/retry` (uploader or
      admin) queues a new upload with the file moved to it and dismisses
      the failed report; Retry on the failed report card and on Uploads
      (still there after Dismiss, which only hides the card). When the same
      content (file hash) later imports successfully, uploaded again by
      hand, earlier failed copies in the org drop their kept file and their
      Retry (it would only import it again); the name plays no part
- [x] A small archive, restore or purge no longer waits for a running upload
      (asked 2026-10-01): an upload writing its rows holds the org's lock
      for minutes, and a small job run during the request waited for it,
      so the click sat on "Archiving…" (e.g. archiving a failed attempt while
      its file is being uploaded again). Now, if the org's lock is taken,
      the job is queued for the worker (202, "Queued…") and runs after the
      upload. Archiving a failed attempt never touches another upload's
      data or file: each upload keeps its file under its own ID, and the
      clean-ups skip uploads that are waiting or running
- [x] An archived upload's report, read-only, on the Archived page (asked
      2026-10-01: only Restore and Purge were offered, so there was no way
      to see what an upload held before deciding). Report on upload rows,
      for every member; `GET /archive/{batch_id}/report` serves it only
      while archived (the normal `GET /scans/{id}` stays closed to archived
      uploads, finding 1); no Retry or Dismiss; gone once purged
- [x] Row actions in three tiers (asked 2026-10-01): Report and Details
      (only show something) white and always underlined
      (`ROW_ACTION_VIEW`; soft grey first, too close to cell text), actions
      that change data cyan, Purge red; rule in docs/UI_CONVENTIONS.md.
      Archived's Purge column shows the date and time under the countdown
- [x] Tests for each: 540 backend + 161 frontend pass, typecheck and lint
      clean (2026-10-01); CI result to confirm on GitHub after the push
- **Signed off 2026-10-01** after your verification (guide Part 4 steps
  1-5). Next: Phase 2e (users and organizations)

## Phase 2e — Users and organizations (implemented; verification refreshed 2026-10-21)

Signed off by the user on 2026-10-01 without completing the verification
guide's Phase 2e checks; parts were checked while verifying (the security
settings form, Activity, lockout and reset, adding people).
Historical commits: c9a4239, bad7799, eaedd46, 232c28a.

Verification refreshed 2026-10-21: requirements traced to code, backend regression
tests and 25 real-Chrome acceptance checks against an isolated real API/worker and
PostgreSQL schema. The later Phase 3 archive/job admission gap is fixed, including
concurrent admission versus archiving. See the scope, checklist, evidence and
production-only qualifications in [docs/PHASE2E_ACCEPTANCE.md](docs/PHASE2E_ACCEPTANCE.md).
This records engineering verification, not a new user sign-off or production approval.
Only organization lifecycle moved here from Phase 2d Part 2; uploads/assets/findings
lifecycle remained implemented in that part. Its stale checkboxes are reconciled.

Requested 2026-09-28: a platform Sysadmin creates organizations and their
admins; each org's admins create its users. Decisions (all as recommended,
plus self-service password change):

- [x] Roles: Sysadmin (platform-wide) above the per-org Admin, Auditor and
      Viewer. A user can belong to several orgs, with a role in each
- [x] Public sign-up turned off: only the Sysadmin creates organizations
      (and their first admin); only an org's admins create its users
- [x] Creating a user: the admin enters email, name and role; the app
      generates a one-time temporary password, shown once, which the user
      must change at first login (no email server yet; email invitations
      later). An email that already has an account gets a new membership
- [x] Every user can change their own password (knowing the current one).
      A forgotten password is reset by their org's admin or the Sysadmin (a
      temporary one again) until email is set up; then self-service reset by
      emailed link
- [x] Admins manage their org's people: change a role, remove a member,
      reset a password. The Sysadmin can also deactivate a user entirely
- [x] The Sysadmin manages organizations and their admins, and can see every
      organization and its details (members, uploads, assets, findings,
      dashboard) read-only; changing an org's data stays with its members. It
      can act in an emergency (e.g. reset an org's admin)
- [x] The first Sysadmin is created by a command on the server
      (scripts/create_sysadmin.py), never through the website
- [x] Organization archive and purge (moved from Phase 2d Part 2): by the
      Sysadmin. An archived org is read-only for its members and shown as
      "Archived" in the picker; the Sysadmin can restore it, or purge it after
      typing its name; the purge log records it
- [x] Sign-in token out of `localStorage` (CoPilot review, finding 7): a
      short-lived token kept in memory plus an `HttpOnly`, `Secure`,
      `SameSite` cookie to renew it (with CSRF protection), so injected
      script can't read it; signing out, a password change or a reset ends
      the user's other sessions. Plus security headers (CSP). Done in
      Part 1 (below)
- [x] From CoPilotSuggestions (2026-09-30): an org can never lose its last
      admin (removing, demoting or deactivating them is refused); a role
      change, removal or deactivation also ends that user's sessions; tests
      that each admin action stays inside its own org

### Decisions (2026-10-01, all as recommended)

- Sign-in: sessions are stored and checked on every request, so ending one
  takes effect at once; the frontend reaches the API through its own
  address (same origin) so the cookie works. Emails are lower-cased
  everywhere (the migration checks for clashes). "Deactivated" is shown only
  after a correct password. A temporary password expires in 7 days
- People: an org admin resets the password only of people who belong to
  that org alone, otherwise the Sysadmin does. Adding someone who already
  has an account gives no temporary password ("they sign in with their
  existing password"). Removing someone's last membership keeps the
  account. The People page is visible to all members; its actions to
  admins only
- Sysadmin: a separate account with no memberships, created only by the
  script. In an emergency it resets passwords, deactivates/reactivates
  users and changes roles, but never changes an org's data. It has a
  Platform section (Organizations, Users, Platform activity) and sees every
  org read-only in the picker
- Organizations: created with name, industry and size plus the first
  admin. Archiving is refused while jobs run; an archived org is read-only
  for everyone and processes no uploads. Never purged automatically: the
  Sysadmin purges after typing its name
- Account menu: Change password, Sign out
- Delivered in three parts: (1) sessions and accounts, (2) people, (3)
  Sysadmin, organization lifecycle and the security settings screens

### Security settings per organization

The Sysadmin sets platform defaults in the app; a new org starts with them,
and its admins can change them within these ranges (Settings > Security).
The password, sign-in and lockout belong to the account, so for someone in
several orgs the strictest value of each setting applies, and a message
names the org that requires it. Every limit is read through one function
(effective_policy, services/security_policy.py): the built-in values, the
platform defaults, then each org's changes. Part 3 adds the screens.

| Setting | Range | Default |
|---|---|---|
| Signed out after idle | 10 minutes to 10 hours | 8 hours |
| Longest sign-in | 2 to 10 days | 7 days |
| Failed sign-ins before locking | 0 (never locks) or 3 to 6 | 5 |
| Window the failures are counted over | 10 to 20 minutes | 15 minutes |
| How long the lock lasts | 10 to 20 minutes, or until an admin unlocks | 15 minutes |
| Password rule | Simple or Complex | Simple |

- Locked until an admin unlocks: any admin of one of the person's orgs, or
  the Sysadmin, can unlock (recorded in Activity); the sign-in page says
  "Your account is locked. Ask your administrator to unlock it."
- Simple: 12 to 128 characters, not the email or the current password
- Complex: the admin sets the minimum length (12 to 64, default 14);
  upper case, lower case, digit and symbol each required or not (default
  all); no reuse of the last 0 to 24 passwords (default 5); expiry after 30
  to 365 days, or never (default never)
- A per-IP limit on sign-in attempts (20 a minute) is a fixed server
  setting, not per org

### Part 1: sessions and accounts (built 2026-10-01; verification refreshed 2026-10-21)

- [x] Sessions stored and checked on every request (`user_sessions`): sign-out,
      idle and longest sign-in end them at once; the access token (15 min)
      lives in the page's memory, renewed by an HttpOnly, SameSite=Strict
      cookie scoped to /api/v1/auth; refresh and logout need the app's
      header and an Origin of ours (CSRF)
- [x] The frontend reaches the API through its own /api (next.config.ts
      rewrites; uploads up to 2 GB pass through); the app's own polling is
      marked background, so an open page still times out when idle
- [x] Lockout (count in a window, timed lock or until an admin unlocks, 0 =
      never), revealed only after a correct password; per-address limit
      of 20 sign-ins a minute (in memory, per web-server process)
- [x] Password rule Simple/Complex with history, expiry, the 7-day
      temporary password and forced change; lengths count characters in any
      language; passwords normalized (NFKC) and hashed whole
      (bcrypt_sha256; old hashes upgraded at sign-in)
- [x] Security settings stored per org (`organizations.security_settings`)
      and as platform defaults (`platform_settings`), strictest wins, with
      the org named in messages; screens come in Part 3
- [x] Change password page (also the forced one) and an account menu
      (Change password, Sign out); emails lower-cased everywhere (migration
      0015 stops on emails differing only in case)
- [x] Security headers: the API's (nosniff, no framing, no-store on /auth,
      HSTS over HTTPS) and the pages' CSP with a per-request nonce
      (src/proxy.ts)
- [x] Service functions ready for Part 2: end a user's sessions, set a
      temporary password, unlock
- Production note: a reverse proxy should send /api straight to the
  backend with the visitor's address; through Next's forwarding every
  sign-in comes from one address (README). CORS_ORIGINS must list the
  site's public address: sign-in checks the browser's Origin against it
- Review (2026-10-01), fixed: a server restart while renewing no longer
  signs people out; Change password locks the account row like sign-in
  (guesses sent together each count); the rules name each org asking for
  a kind of character; .env.example gaps
- Resolved in Part 3: refresh renews the browser cookie's expiry when an
  admin changes the longest sign-in; public sign-up is closed by default.

### Part 2: people (built 2026-10-01; verification refreshed 2026-10-21)

- [x] People page (sidebar), a list page like the others: name, email,
      role, status (Active, Locked, Must change password, Deactivated),
      added; search, filters, sorting, paging. Every member sees it; the
      actions are the admins' (`/orgs/{id}/members`, routes/people.py,
      services/people.py)
- [x] Add person: email, name, role. A new account gets a temporary
      password, shown once (with Copy) and never stored as typed; an email
      that already has an account just gets the membership and keeps its
      own password and name. The Sysadmin's account can't be added
- [x] Change role (pick it in the row, then confirm), Remove (the account
      stays), Reset password (a temporary one, shown once), Unlock. A role
      change, removal or reset ends that person's sessions; the sign-in
      page then says why ("An administrator changed your role")
- [x] An org always keeps an admin, and admins don't change their own role,
      remove themselves or reset their own password: another admin does
      (the org's row is locked while members change, so two admins
      demoting each other can't leave none)
- [x] Names can be edited (agreed 2026-10-01). Everyone edits their own on
      a Your account page in the account menu (beside Change password),
      which also shows their email and their orgs and roles. An org admin
      edits the name of people who belong to that org alone; anyone in
      several orgs is renamed by the Sysadmin (the password-reset rule).
      Each rename is recorded in Activity with the old and new names
- [x] The email (the sign-in ID) can't be edited by its owner or an org
      admin: changing it safely needs a confirmation email. The Sysadmin
      may change it until email is set up (Part 3); self-service with a
      confirmation link comes with email
- [x] Activity: Member added (and whether it's a new account), Member
      removed, Role changed, Name changed, Password reset, Account
      unlocked; renames and unlocks show in each of the person's orgs
- [x] Tests that each admin action stays inside its own org (an admin of
      another org gets 404 or 403)
- Resolved in Part 3: the Sysadmin can reset passwords and rename multi-org
  accounts; organization admins remain restricted to single-org accounts.
- No schema change (no migration). GET /orgs/{id}/users became
  GET /orgs/{id}/members (paged)

### Part 3: Sysadmin, organizations, security settings screens (built 2026-10-01; verification refreshed 2026-10-21)

- [x] The Sysadmin: an account of its own, in no org, created only on the
      server (`scripts/create_sysadmin.py --email … --name …`, a temporary
      password shown once). It reads every org read-only (the picker lists
      them all as "Sysadmin: read-only"; api/deps.py SysadminView) and has a
      Platform section in the sidebar
- [x] Public sign-up off by default (`PUBLIC_SIGNUP`, .env); members no
      longer create orgs (POST /orgs is gone). The sign-in page offers
      "Create an account" only while sign-up is open (GET /auth/options).
      With it on, sign-up still says whether an email has an account
- [x] Platform > Organizations: create one with its first admin (a new
      account's temporary password shown once); archive (refused while its
      uploads or archive jobs wait or run), restore, purge (archived only,
      after typing its name). Migration 0016 (archived_at/by,
      purge_requested_at/by)
- [x] An archived org is read-only for everyone (every change goes through
      require_org_role, which refuses it; the bulk archive jobs too), shown
      "(archived)" in the picker with a banner, and left out of the daily
      auto-purge. Never purged automatically
- [x] Purge: the org is gone for everyone at once; the background worker
      deletes its rows table by table in chunks of 10,000 (each committed,
      so a purge cut off carries on), then the org. Accounts stay. Recorded
      in Platform activity with counts (the org's own Activity goes with it)
- [x] Platform > Accounts: every account with its orgs and roles; edit the
      name or the email (the sign-in), reset the password (anyone, whatever
      their orgs), unlock, deactivate (signed out at once; refused for an
      org's only admin who can sign in) or reactivate, change a role in an
      org (the org keeps an admin). The Sysadmin's own row: Edit only
- [x] "An org keeps an admin" now counts only admins who can sign in
      (a deactivated admin doesn't look after the org)
- [x] Platform activity: events of no org (the Sysadmin's actions, the
      worker). Org Activity shows the worker's events but not the
      platform's; actions on an account also show in each of its orgs
- [x] Security settings screens: Platform > Security defaults (over the
      built-in values) and each org's Settings > Security (over the
      platform defaults; admins edit, members read). Each setting shows
      Default or Changed with "Use default"; the backend checks the ranges
      (422). Recorded as Settings changed
- [x] Part 1 leftovers: the session cookie's expiry is renewed on every
      refresh (follows the longest sign-in if an admin changes it); sign-up
      enumeration answered by closing sign-up
- Historical Part 3 deployment required migration 0016 and a worker restart
  for organization purge. For the current migration head and release procedure,
  use [docs/PHASE3_OPERATIONS.md](docs/PHASE3_OPERATIONS.md); do not target 0016 today.
- Found while verifying (2026-10-01), done: the security settings form
  checks each value as it's typed (red border and the range; Save
  disabled until fixed); an org's Activity shows the worker's events only
  since the org was created
- Asked while verifying (2026-10-01), done: where sign-ins come from.
  Signed in, Failed sign-in, Account locked and Signed out events carry
  the address and browser ("Chrome on Windows", services/client_info.py);
  Your account lists where you're signed in (browser, address, signed in,
  last active) with Sign out for each other one and Sign out everywhere
  else (GET /auth/sessions, DELETE /auth/sessions/{id}, POST
  /auth/sessions/end-others). Locally every address is 127.0.0.1 (the
  frontend forwards /api); behind the production proxy it's the visitor's

## Phase 2f — Activity and audit log sources (after Phase 2e, before Phase 3)

Requested 2026-09-28, after `azure_azure_activity_500000.json` failed as a
generic asset list ("type is required" on all 500,000 rows): no import source
reads activity/audit logs. They record events (who did what, when), not
assets, so they should produce findings. Placed before Phase 3 so the AI
audit can reason over these findings too. Test files:
S:\AuditMind-Scratch\TestData\synthetic_assets\ (azure_azure_activity,
cloudtrail_cloudtrail, gcp_gcp_audit; 142-176 MB, 500K events each).

- [x] Prerequisite, moved here from Phase 4: read large files in chunks
      (saved to disk, processed in batches), so memory stays flat at any
      size; all-or-nothing imports get a check-first pass. Log exports are
      routinely this large (split_json.py is the stopgap until then)
- [x] Imports that resume from where they were cut off (from Part 3
      verification, 2026-09-30: a 500K upload cut off while writing rows
      started again from reading). Today an import is one transaction, so
      a cut-off loses everything and the restart redoes it all (~3-5 min
      for 500K rows). Instead: write rows in committed chunks to a staging
      area users can't see, recording how far it got; then publish in one
      short final step, so users still never see half an upload. A restart
      carries on from the last chunk. Also ends the long transaction that
      slows the importing org's Assets/Dashboard during an import
      (measured ~0.1-1.1 s), and suits many workers (Phase 4, SaaS).
      Builds on the chunked reading above. To settle at the start: matching
      and duplicate checks against rows staged but not yet published, two
      uploads into one org (the org lock stays held until publish?), and
      clearing a staging area left by a failed import (all settled: see
      Part 1 below)
- [x] Sources (import profiles) for Azure Activity Log, AWS CloudTrail and
      GCP Audit Logs, detected from their columns like the existing ones
- [x] Endpoint security events in the OSSEM format (Sysmon/EDR telemetry;
      test file ossem_ossem_events_500000.csv: event_id, timestamp,
      user.name, process.name/pid/command_line, file.path, registry.key,
      network.src_ip/dst_ip, event_type). Signals in the sample: encoded
      PowerShell (-enc), Run-key persistence, DLLs in Temp. It names no host
      (no host.name column): settled by decision 8 (no asset; per host when
      a log names hosts)
- [x] Rules that turn events into findings, grouped rather than one per event
      (500K events would flood the list), e.g. role/permission assignments
      and policy changes (Identity & Access), deletions, firewall/network
      rule changes (Network & Config), repeated failed operations,
      logging/monitoring switched off (Monitoring & Detection)
- Open questions for the start of the phase (all answered by the
  decisions below): which events count as risky
  and at what thresholds; what a finding attaches to, since these records
  name a subscription/resource group/resource type but no resource ID (the
  subscription or resource group as an asset? the caller?); the time window
  (a whole export, or only recent events); whether to keep the raw events;
  what counts as the same activity when grouping (the key repeated events
  are grouped on)
- From CoPilotSuggestions (2026-09-30), for the chunked reading above: a
  test that a file bigger than the worker's memory imports with flat
  memory (done: the readers' flat-memory test); limits for malformed or
  deeply nested JSON (an event log's examples are bounded) and for
  compressed files (still open)

### Decisions (2026-10-01, all as recommended)

Found while exploring: the test logs are flat and random (every row a
different user, subscription, project and IP; CloudTrail has no result,
MFA or target; OSSEM no host), and risky event types make up 25-66% of
each file. The 500K files are in synthetic_assets\Phase4, which also has
firewall, VPN, identity, EDR, Sysmon and vulnerability event logs.

1. Two parts. Part 1: every upload read in chunks with flat memory, and
   imports that resume where they stopped (all uploads, not only logs).
   Part 2: the event-log sources and their rules
2. Resuming: rows are read and checked in chunks into a hidden staging
   table, each chunk committed; once the whole file is read, matching and
   publishing run in one step under the org lock, so no one sees half an
   upload. A cut-off carries on from the last chunk (up to 3 times, like
   archive jobs). All-or-nothing rejects by not publishing; staging is
   cleaned up then, plus a daily sweep
3. JSON read incrementally with the ijson library
4. Upload limit (IMPORT_MAX_BYTES) raised from 100 MB to 1 GB once memory
   stays flat
5. Sources in 2f: Azure Activity, AWS CloudTrail, GCP Audit, OSSEM. The
   other six logs (firewall, VPN, identity, EDR, Sysmon, vulnerability
   events) go to Phase 5 (connectors)
6. Both the flat test layout and the real export layouts (CloudTrail
   Records[] with userIdentity.arn, Azure nested properties, GCP
   protoPayload): nested field names such as userIdentity.arn
7. Grouping: one finding per rule per upload ("Role assignments created:
   2,497 events by 2,497 callers in 2,497 subscriptions"), keeping the top
   10 subscriptions/accounts/projects/hosts and actors, and up to 5
   example events
8. No asset for these findings (tenant-level; "—" in the Asset column).
   If an endpoint log names a host (host.name, computer), group per host
   and attach to that host's asset
9. New finding fields: event count, first seen, last seen, details (the
   breakdowns and examples), by migration; Findings gets an Events column
   and a details view
10. Repeats: recognized by rule plus the events' date range; a newer
    export adds findings for its period, the same file again is a
    duplicate (the "uploaded before" warning already shows)
11. Raw events not kept, only the findings with breakdowns and examples;
    the uploaded file is deleted after success as today
12. Time window: the whole export
13. Default rules, each adjustable in File formats (on/off, severity):
    Azure role assignment created (High if succeeded; Medium if failed),
    many failed operations (Medium); CloudTrail anything by root (High;
    a root console sign-in Critical), security group opened (High), bucket
    policy changed (Medium), IAM user created (Medium), instances
    terminated (Low); GCP firewall changed and succeeded (High), service
    account created (Medium), bucket updated (Medium), permission denied
    (Medium); OSSEM encoded PowerShell (Critical), Run-key persistence
    (High), DLL in Temp (High), new service under HKLM Services (Medium),
    whoami reconnaissance (Medium). Domains: Identity & Access (roles,
    IAM, permission denied), Network & Config (firewalls, security
    groups), Compliance (bucket policies), Incident Response (OSSEM)
14. Same Upload button; the source is detected from the columns; the
    "event logs can't be read yet" block is lifted for these sources

### Part 1: big files and resumable imports (built 2026-10-01, awaiting verification)

Three designs compared (minimal change, clean structure, pragmatic
balance); chosen: the pragmatic one plus the clean one's seam for Part 2.
- Readers over a file path (CSV streamed, JSON with ijson, .nessus with
  iterparse), same row numbers as today
- Worker imports stage rows in chunks of 2,000 into UNLOGGED staging
  tables (a database crash just means reading again from row 0), each
  chunk committed with its cursor and the report so far; uploads of 10 MB
  or less stay in memory (same readers and checks), as fast as today
- Publish in one pass (each row's asset, then its findings) under the org
  lock, from staging in keyset batches into the existing matching and
  COPY writes; set-based SQL for identifiers and repeated-asset warnings
- The row reader has finish() and snapshot()/restore(), so Part 2's
  grouping can count across all rows and survive a resume
- A cut-off resumes from the last chunk up to 3 times; changed settings
  or format mean reading again from row 0; all-or-nothing stops staging
  at the first bad row but keeps counting errors
- Starts with a half-day speed test (500K rows through staging and back)
- Known limit: publishing still keeps the org's matching index in
  memory, so a file of millions of rows needs GBs and holds the org lock
  for minutes; a row cap or warning to follow
- Built: import_readers.py (CSV streamed, JSON with ijson 3.5.1 and its C
  backend, .nessus with iterparse, a host at a time), import_staging.py
  (MemoryStaging, DbStaging, ReadState, Capped lists), migration 0017
  (unlogged import_staging_state and import_staging_chunks), the publisher
  in ingestion_service (_RowChecker, _stage, _Publisher, _RepeatedAssets),
  the worker passing the file's path, resuming up to 3 times and sweeping
  leftover staging daily; IMPORT_MAX_BYTES 1 GB
- Changed from the design after measuring (speed test, 500K rows): staging
  is pickled chunks of 2,000 rows, not JSONB per row (stage 14 s and read
  back 9 s, against 42 s and 29 s). So the identifiers to load and the
  repeated-asset warnings are kept in Python while reading and publishing
  (per asset, not per row) instead of SQL over staging
- Measured, a 500K-row endpoint export (500K assets, 1.24M findings):
  173 s -> 209 s (+21%), peak memory 1,681 MB -> 708 MB; small uploads
  (in the request) unchanged
- Behaviour changes: the progress no longer has a separate "findings"
  stage (each row is written with its findings); the reading total is an
  estimate until the end; a file problem (invalid JSON or UTF-8) late in a
  big file is found when reading gets there, not up front (nothing is
  published either way); when all-or-nothing rejects a file its
  repeated-asset warnings aren't listed (nothing was written)
- Review (3 reviewers, 2026-10-01), fixed: the resume fingerprint was
  built from repr(), which holds memory addresses and set orders that
  change every time Python starts, so a restarted worker never carried on
  (all three found it; confirmed across two processes; now built from the
  values themselves, sorted, with a two-process test); outdated "once" /
  "twice" wording about cut-offs; duplicated staging code; the Part 2 seam
  now tested with a stand-in source whose count survives a resume; test
  clean-ups. Accepted: JSON with NaN/Infinity (not valid JSON) is now
  refused

### Part 2: event-log sources (built 2026-10-01, in review)

- Four built-in sources (families of kind "events"): Azure Activity, AWS
  CloudTrail, GCP Audit, OSSEM; detected from their columns; flat test
  layout and real export layouts (CloudTrail {"Records": [...]} and
  userIdentity.arn, Azure properties.*, GCP protoPayload.*): a field name
  is a literal column or a dotted path into nested JSON
- Rules (decision 13) tally matching events: count, first and last seen,
  top 10 actors and scopes, up to 5 examples; one finding per rule per
  upload (OSSEM with a host column: per host, on that host's asset). The
  tally is saved with each staged chunk (Part 1's seam, with a fresh tally
  per import). Distinct actors/scopes counted exactly up to 5,000, then
  "over 5,000"
- Findings: migration 0018 adds event_count, first_seen, last_seen,
  details; no asset (but OSSEM per host); the category holds the date
  range, so a later export adds findings and the same file is a duplicate;
  they count as findings
- Screens: the "event logs can't be read yet" block lifted for these
  sources; File formats lists each source's rules (on/off, severity);
  Findings shows each one's events and Details (period, top actors and
  scopes, examples); rows without an asset show "—"
- Built: services/event_sources.py (sources, rules, EventTally), the four
  families in import_profiles.py (ProfileConfig.start() gives each import a
  fresh tally; values() reads columns or nested paths), EventLogParams
  (rule settings, unknown rules refused), migration 0018 (findings:
  event_count, first_seen, last_seen, details), findings on no asset with
  their own duplicate check, the profiles API listing each source's rules;
  File formats rules block; Findings shows "N events, first to last" under
  the finding with Details (not a column of its own: every column there is
  sortable, and this one needn't be)
- Measured: each 500K-event test log imports in 17-25 s into 3-6
  findings (Azure 3, CloudTrail 6, GCP 4, OSSEM 5)
- Also fixed (found by the user): dismissing the report of an upload since
  archived or purged said "Scan not found"; the report now just goes, and
  the tracker reloads after archive jobs
- Review (3 reviewers, 2026-10-01), fixed: a failed CloudTrail console
  sign-in (no errorCode, only errorMessage and ConsoleLogin "Failure") was
  counted as a sign-in; two logs of different subscriptions/accounts/
  projects over the same dates collided as duplicates (the title now
  names a single scope, or counts several with a short reference to
  which); hosts differing only in case made two findings; unbounded per
  host groups (at most 500 hosts per rule, then one "other hosts"
  finding), value lengths (300), examples (4 levels, 1,600 characters)
  and the text a pattern checks (8 KB, so a huge command line can't make
  it slow); the dead row reader of event families, duplicated rule
  helpers; outdated tests and notes. The Details toggle under a finding is
  an allowed exception in docs/UI_CONVENTIONS.md (the actions column is
  only shown to those who can change things). Two logs with neither a
  scope nor host columns, over the same dates, still look alike (nothing
  tells them apart)

## Phase 3 — AI audit & reporting (Week 3 of the roadmap)

- [x] Evidence-status/scoring contract approved by user (23 October 2026):
  [proposed contract and acceptance specification](docs/EVIDENCE_ASSESSMENT_DESIGN.md).
- [x] Define seven coverage profiles and trusted qualification rules:
  [profiles and operator workflow](docs/EVIDENCE_COVERAGE_PROFILES.md).
- [x] Implement opt-in schema3/prompt-v4 provider contract, partial scores, server
  aggregation, API/filter/export/UI handling and source-bound qualification.
- [x] Complete verification:1,115 full PostgreSQL backend tests,312 frontend tests,
  18 new-mode +17 legacy Chrome checks; lint/TypeScript/build and migration checks
  pass. [Evidence](docs/EVIDENCE_ASSESSMENT_VALIDATION.md). No new coverage measured.
- [x] Check-in review: untrusted prompt-marker preservation fix and one regression;
  130 focused tests passed afterward, not a new1,116-test full-suite claim.
  [Manual/automated verification guide](docs/EVIDENCE_USER_VERIFICATION.md).
- [ ] Controlled-rollout adoption of profiles/operator qualification. Flag remains
  off by default; no live-AI approval, credentials or consent changes implied.

- [x] Local-testing milestone closed by explicit user approval,23October2026.
  Scoped development-tool risk exception recorded in
  [decision record](docs/LOCAL_TESTING_MILESTONE.md), review/expiry22November2026.
  No production/live-AI sign-off. Insufficient-evidence scoring stays separate;
  Docker and report-date UI remain Future.

23October presentation follow-up: advisory score labels, baseline/confidence and
sampling explanations, complete domain text and evidence references implemented.
307 frontend /71 focused backend tests and17 Chrome checks, lint/TypeScript/build
passed. Latest full backend checkpoint remains1,035 tests (22October); no new
coverage measured. [Details](docs/REPORT_SCORING_UI_REVIEW.md). Insufficient-evidence
scoring was a separate pending decision at that checkpoint; the approved opt-in
implementation above supersedes it. Live-provider release gates remain open.

Closure authority: [PHASE3_CLOSURE.md](docs/PHASE3_CLOSURE.md). Prompt/context limits
and omission provenance are implemented under **audit-evidence-v3**. Fresh target
approval is required; existing reports remain unchanged. Remaining release gates
are genuine provider/model/pricing/quality acceptance and production/live-AI
sign-off, with separate broader advisory disposition required for that scope—not
Docker or browser date fields. Local-testing advisory disposition is recorded above.

Expanded verification (2026-10-22): PostgreSQL-required full backend **1,005 passed**,
zero skips/failures; coverage-driven follow-up **19 passed** (11 new cases).
Cumulative backend coverage 94.19% lines/85.34% branches. Frontend **300 passed**,
91.98% lines/84.85% branches; lint/TypeScript/build pass. Native Chrome Phase 2e
25 and Phase 3 16 checks rerun successfully. See [testing strategy](docs/TESTING.md)
for scope, artifacts and remaining measured gaps; no exhaustive/production claim.

- [x] Native/mock Chrome acceptance (2026-10-22): 16 real-stack checks, 3 document
  roles and 2 report-dialog viewport scenarios; disposable schema cleaned. See
  [acceptance evidence](docs/PHASE3_ACCEPTANCE.md). No genuine model or production certification.

Scope decision (2026-10-22, user-approved): reporting-period browser fields are
a deferred enhancement, not a Phase 3 blocker. Docker/container deployment and
its staging/cache/restart validation move to the **Future phase** below. Current
acceptance targets native local execution with mocked AI only; it is not
production/cloud/container or live-provider certification.

Current review (2026-10-22): [release readiness](docs/RELEASE_READINESS.md)
supersedes older completion assumptions. Production dependency audit and cancellation
retry authorization are remediated; development-tool audit disposition remains open. Automated implementation checks below
are not full Chrome/staging/live-provider acceptance or sign-off.

Release decision (2026-10-21): retain deterministic `/risk/score` and dashboard
scores; provide Claude/RAG assessments through asynchronous reports with separate
captured rule-based scores. Shared score tiers are approved (80/60/40 boundaries),
and new AI assessments now share deterministic tier logic. Remediation confidence
and finding/asset UUID allowlists are implemented under `audit-evidence-v2`;
updated admin consent is required, and retained snapshots are unchanged.
Phase 3a is a separate delivery and
does not block core Phase 3. Phase 3b remains a future proposal. See the current
release-scope decision in [Phase3.md](Phase3.md).

Evidence capture (2026-10-21): independent PostgreSQL repeatable-read capture
keeps counts, samples, rule scores and retrieved sources coherent. Source-use
registration is atomic; serialization/deadlock conflicts retry the complete
capture at most three times. Authorization remains live and the snapshot session
closes before Claude generation. See operations for query-embedding lifetime
and SDK retry limitations. Native/mock Chrome acceptance passed on 2026-10-22;
Docker/container staging is Future scope, not a current core gate.

Operational follow-up (2026-10-20): durable PostgreSQL quota/cost reservations,
organization-scoped report idempotency, configurable terminal-report retention,
and offline embedding API/worker packaging are implemented. Migration head is
`0021`; do not apply it to important databases without the release checks in
[docs/PHASE3_OPERATIONS.md](docs/PHASE3_OPERATIONS.md). Container build/startup/cache
validation is deferred to the Future phase by the user's 2026-10-22 decision. See
[validation evidence](docs/BACKEND_VALIDATION.md). The Phase 3 local-testing
milestone was accepted; production/live-provider acceptance remains separate.
Older unchecked entries are not proof of missing code.

**Scope:** load
CIS/NIST/ISO docs (pgvector is already set up), AI report assessments with RAG
citations and report generation. `/risk/score` remains deterministic; AI report
assessments do not replace that scoring boundary.

- [x] Working-tree implementation has passing automated suites (987 backend/274 frontend on 2026-10-22), plus 24 final focused regressions after adding two direct-provider cases. Production build passes.
- [x] Reviewable commits and development-tool audit disposition for the accepted local-testing milestone; subsequent dependency remediation is recorded separately.
- [ ] Production/live-provider release acceptance and sign-off (not implied by local milestone closure).
- Review fixes (2026-10-06): reproduced before implementation, with regression
  tests for CloudTrail account separation, assetless finding restore, idle-timeout
  renewal, concurrent last-admin deactivation, report recovery/cancellation,
  severity ordering, structured output, reporting dates, and report-list/viewer
  behavior. The existing org gate already resets report state on organization
  changes; its regression passed without changing that behavior.
- Report behavior: missing Claude credentials, provider failures and invalid
  output now fail the job rather than returning a canned assessment. Tests use
  a mocked provider. Scores and tiers must agree, and all seven domains must
  appear exactly once. Failed generation must not be treated as an audit result.
- Reporting dates select **currently active findings created within the inclusive
  UTC date range** (user decision, 2026-10-06); inventory counts are current, not
  reconstructed historical inventory. Reversed ranges are rejected.
- Interrupted report jobs resume up to three times, then fail. Cancellation
  prevents a result being saved, but does not abort an already-issued provider
  request. Report lists expose `overall_score` without including the snapshot;
  an open running report refreshes until it reaches a terminal state.
- CloudTrail uses the recipient account (identity account as a fallback) plus
  region to distinguish findings. Logs without account fields retain the old
  region-only behavior; already imported collisions cannot recover discarded
  evidence automatically. Reimport source logs containing account identifiers.
- Historical October 6 defect-fix scope excluded idempotency, quotas/costs,
  ingestion, provenance and retention/PDF. Subsequent implementation covers these;
  that old exclusion is not a current missing-feature list.
- Claude auth: keep `ANTHROPIC_API_KEY` in `backend/.env` for local dev, and
  keep every Claude call going through `app/services/claude_service.py`, so the
  auth method can change in one place later (see Phase 4).
- [x] Claude operational controls implemented and mock-tested (CoPilot review, finding 6), in
      `claude_service.py`: timeouts, a few retries for temporary errors,
      per-org limits, token and cost recorded per call, provider errors
      mapped to clear messages, and the model's output checked before any
      score or report is saved. Tests with a mocked provider (timeout, rate
      limit, bad output, outage)
- [x] Report generation is a real job (findings 3 and 8): queued for the
      worker like imports, with status, failure details and retries;
      `GET /reports` paged, newest first, full report only by ID
- Scope in detail (from CoPilotSuggestions, 2026-09-30; to settle at the
  start of the phase):
  - [x] Document pipeline for installed/licensed standards and organization documents, loaded as a
        worker job: chunked, embedded, with source and version, each org
        seeing only its own documents plus the shared standards
  - [x] Retrieval with validated citations reaching API responses and reports (automated coverage; live acceptance open)
  - [x] Claude answers in a fixed structure, checked (Pydantic) before use
  - [x] AI scoring never replaces the rule-based score: both are kept,
        with the evidence, model, prompt version and period they came from
  - [x] Remediation recommendations: priority, captured-evidence finding/asset
        UUID references, rationale, bounded model-estimated confidence. Schema/
        prompt v2 rejects invalid references; UI/HTML/PDF preserve the fields.
  - [x] A finished report is a saved snapshot (automated coverage);
        HTML and PDF download for org members only; kept per a retention
        setting
  - [x] Cancellation prevents publication; keyed organization-scoped idempotency avoids duplicate creation.
  - [x] Refresh live job ownership/status/cancellation before each application-level provider attempt/reservation.
  - Deferred to Future: reporting-period UI; API date semantics already implemented. Not a core Phase 3 gate.
  - [x] Resolve production dependency audit; frontend build passes on Next 16.4.2.
  - [x] Complete scoped native/mock browser acceptance; see recorded limits and evidence.
  - [x] Add explicit full-request byte budget, bounded source excerpts and omission provenance; reject references to excluded evidence. Prompt v3 requires fresh approval.
  - [x] Development-tool audit disposition recorded; subsequent dependency remediation removed the earlier advisory blocker without new ignores.
  - [ ] Genuine provider/model/pricing/quality acceptance. Container staging is Future scope.

## Phase 3a — Local and Claude report providers

**Approved scope (2026-10-08):** support both local and Claude report generation
with the same validation and evidence requirements. Start with one local runtime
and one evaluated model, not unrestricted model compatibility.

**Status (2026-10-22):** separate delivery, paused after hardware and Ollama/Qwen/Phi
experiments. No model or local report adapter accepted. The implemented optional
OpenRouter Claude transport is not local generation. See dated evaluation records
in [local reporting plan](docs/LOCAL_REPORTING_PLAN.md).
See [Phase3.md — Phase 3a](Phase3.md#phase-3a--local-and-claude-report-generation)
for decisions, dependencies, implementation steps, and acceptance criteria.

- [x] Assess development hardware and review candidate licenses/evaluation criteria; production sizing remains separate.
- [x] Select approved Ollama/model artifacts for experiments (not production acceptance).
- [ ] Accept a generative model against all agreed quality/resource gates.
- [ ] Introduce a report-provider interface; retain Claude and add a local adapter.
- [ ] Keep report-provider selection independent of embedding-provider selection.
- [ ] Preserve schema/score/citation validation, separate rule scores, and immutable evidence.
- [ ] Define provider-specific consent, endpoint restrictions, and offline behavior;
      never silently fall back from local generation to an external provider.
- [ ] Record provider/model identity and generation parameters per report job/snapshot.
- [ ] Integrate worker limits, timeout/recovery/cancellation, and configuration UI.
- [ ] Evaluate accuracy, citation fidelity, completeness, latency, and memory on a
      fixed evidence set; agree acceptance thresholds before selecting the default.
- [ ] Verify existing Claude behavior, local-only operation, and retained report readability.
- [ ] Document setup and operations, complete quality review, and obtain sign-off.

## Phase 3b — OpenAI hosted report generation (future proposal)

**Request recorded (2026-10-08):** support customers whose only hosted-model credential is an OpenAI API key. This is a documented future extension, not an implementation approval or model selection.

Current report generation supports direct Anthropic and the optional disabled-by-default
OpenRouter Claude transport; neither is an OpenAI report adapter. `OPENAI_API_KEY`
configures embeddings only. A key alone does not switch report providers.
Coordinate this extension with the provider boundary; keep report/embedding
configuration distinct and do not require Anthropic credentials for a future
explicitly selected OpenAI report path.

- [ ] Approve the provider interface, OpenAI model/structured-output approach, and cost limits.
- [ ] Add OpenAI report generation with the existing snapshot validation and evidence protections; never call Anthropic on the OpenAI path.
- [ ] Generalize explicit report consent to provider/model identity; require fresh consent after target changes and pin provider/model to queued jobs.
- [ ] Record provider/model and evidence provenance; preserve existing Anthropic and rule-based snapshots.
- [ ] Test OpenAI-only configuration, missing credentials, mocked API/provider failures, invalid output, consent/routing, and no Anthropic invocation. Do not make live provider calls in tests.
- [ ] Document local key configuration, account/API access, cost, and restart requirements; review and sign off.

See [Phase3.md — Phase 3b](Phase3.md#phase-3b--openai-hosted-report-generation-future-proposal) for requirements and sequencing. No external OpenAI requests or implementation are approved by this entry.

## Phase 4 — Polish & resilience focus (Week 4 of the roadmap)

Current code reconciliation (26 October): [status matrix](docs/PHASE4_STATUS.md).
Subsequent approved [dependency remediation](docs/BACKEND_DEPENDENCY_REMEDIATION.md)
now has clean core/dev, optional and installed audits with no conflicts; the
initial audit blocker described in earlier entries is historical.
The local operations increment adds Dashboard security summary, `/ready`,
multi-file/drop import, product/header branding and configured browser/security CI.
See [contract and remaining blockers](docs/PHASE4_LOCAL_OPERATIONS.md): the initial
34 backend advisory entries were addressed in the subsequent increment above. Organization
logos were pending at that checkpoint and are now implemented locally in migration
0025; [branding contract](docs/ORGANIZATION_LOGOS.md). Broader hardening/performance
remain pending; Phase 4 is not complete.
Latest dependency checkpoint supersedes the earlier 1,229-test run: 1,238 full
PostgreSQL tests (628.60s, warnings as errors), 376 frontend tests (29.03s),
lint/build/TypeScript and 39 Chrome workflow checks passed. Six Documents grouped
checks passed separately; focused results overlap the full suite. All three
backend audit scopes are clean. See the dependency remediation evidence above.
Subsequent clean-install corrections exercised Linux hosted CI: backend 1,244
passed, frontend 377 passed, 39 local Chrome checks and hosted Chromium acceptance
passed. [Exact SHA evidence/final CI status](docs/BACKEND_DEPENDENCY_REMEDIATION.md).
No dependency risk waiver exists; production/live-AI approval remains separate.

Kickoff design prepared 23 October 2026:
[remediation workflow contract and acceptance gates](docs/PHASE4_REMEDIATION_DESIGN.md).
The remediation backend, Findings workflow controls and list filters are implemented;
broader Phase 4 acceptance remains pending. The increment
preserves existing scoring and report snapshots; status-aware scoring needs a
separate approved policy. Historical backlog entries below require verification
against current code before being treated as outstanding implementation work.

**Scope:** per-domain scoring refinement, remediation workflow/lifecycle and
export refinements beyond Phase 3's implemented generated recommendations and
HTML/PDF snapshots; security hardening (rate limiting, audit logging, secrets handling).

- [x] Kickoff: targeted code inspection and proposed remediation contract documented (2026-10-23).
- [x] First backend workflow increment: single/bulk mutations, paged history,
      role/version checks and preservation of edited restore duplicates. See
      [validation and delivery limits](docs/PHASE4_VALIDATION.md).
- [x] Findings workflow UI: role-aware single/bulk editor, assignee/history
      paging, URL-backed status/assignee/overdue filters and workflow sorting.
- [x] Manual finding entry UI; contextual manual-archive availability and clearer
      horizontal sort headings. Finding deadlines use inclusive US Eastern dates
      (`America/New_York`, EST/EDT); existing dates reinterpreted without rewriting.
- [x] Browser-timezone correction: persist author zone and fixed UTC expiry;
      legacy dates migrate as Eastern (0023). Full verification and demo rollout;
      supersedes the application-wide Eastern rule above for new deadline writes.
- [x] Record [imported-finding archive/reconciliation design](docs/FINDING_RECONCILIATION_DESIGN.md).
- [ ] Approve and implement stable identity, individual imported suppression and
      comparable-scan absence review. Design-first only; no automatic resolution.
- [x] Shared full-day date-filter processing in browser timezone without new time
      controls; compact local-time display and one general signed-in notice.
- [x] Finding-ID traceability: expandable/copyable IDs, exact UUID search and
      organization-scoped workflow/report/Activity finding links; no snapshot changes.
- [x] Shared routine job-success auto-dismiss after 10 visible seconds with
      interaction/visibility pauses; warnings/failures remain manual. Full-width Settings.
- [x] Documents/Shared standards preview aligned with Uploads reports: inline row
      panel, version toggle, local loading/retry, keyboard scrolling and focus restoration.
- [x] Unified Findings selection with both bulk actions, 100-workflow/500-archive
      limits, all-manual archive eligibility, frozen confirmations and sticky row Actions.
- [x] Local remediation verification: 1,218 full PostgreSQL tests (deadline
      increment); subsequent shared-selection tree passed 372 frontend tests,
      lint/TypeScript/production builds and 37 Chrome checks. Final pre-push
      rerun: 54 overlapping focused PostgreSQL tests and 372 frontend tests.
      Migration round-trips/drift passed at 0024. Separate Documents Chrome
      evidence remains historical. No production/global Phase 4 sign-off.
- [x] Shared date-input contrast, today's inclusive deadline validation and
      creation-date boundaries; Archived/Assets/Uploads row-versus-bulk actions,
      immutable confirmation targets and modal interaction safeguards.
- [x] UI polish listed below (local application scope; requested 2026-09-28, needs no other
      phase):
  - [x] File upload: drag/drop and multiple files with individual source choices,
    cancellation, errors and reports (up to 20 queued cards).
  - [x] Product logo (sidebar, login/register and browser tab).
    Platform → Product branding offers platform-admin-only sidebar size choices
    Small 144×40 / Medium 180×48 (default) / Large 192×64; versioned/audited storage
    uses existing platform_settings. Authentication/company branding is unchanged.
  - [x] Shared Show/Hide password control across login/register, change-password
    fields and temporary-password handovers; hidden by default, keyboard accessible,
    independent per field, no submission/value/autocomplete changes.
  - [x] Organization logos: admin upload/replace/remove, authenticated header display,
    bounded normalized PNG storage, stale-write protection and migration 0025.
    See [contract and user steps](docs/ORGANIZATION_LOGOS.md).
  - [x] Organization name/company logo in the common UI header; product branding
    appears in the sidebar and once above authentication cards, without duplication.
    Admin-controlled header-name visibility defaults on (migration 0026); missing
    or broken logos retain the name. Compact product logo box is 180×48px.
    Header organization-logo size is configurable (Small/Medium/Large), default
    Medium 160×64px, preserving proportions; migration 0027.
    Header company name size: Small 16px / Medium 20px (default) / Large 24px,
    admin-configurable with stale-edit protection; migration 0028.
  - [x] Dashboard "Recent activity" replacement (raised 2026-10-02). Historical rationale: it
    lists every Info event (sign-ins, worker started/stopped), so routine
    noise fills it. Decided (2026-10-02): replace it with a security
    summary: a few counts for the last 7 days (failed sign-ins, new users,
    role changes, data purged), each linking to Activity filtered to those
    events. Implemented member additions, role changes and completed purge-operation
    counts, with exact rolling-seven-day Activity links. Failed-sign-in attribution
    is unavailable, not guessed; worker/sign-in events stay in full Activity.
- [ ] Keyless Claude auth for deployed environments (no long-lived API key):
      identity federation with the host platform's workload identity, or
      Amazon Bedrock / Google Vertex AI with cloud IAM if hosted on AWS/GCP.
      Decide once hosting is chosen; confirm what the Claude API supports at
      that point. Likely shape: a `CLAUDE_AUTH_MODE` setting read by
      `claude_service.py`, with local dev staying on the API key.
- [x] Local readiness check (CoPilot review, finding 5): `/health` stays a cheap
      "the process is up"; a new `/ready` checks the database, the uploads
      folder and the worker's last check-in (quickly, without revealing
      connection details). Local implementation complete; hosted load-balancer
      exposure and dependency/OS timeout acceptance remain separate.
- [ ] Big orgs' list pages (found measuring Phase 2d Part 3, 2026-09-30):
      with 500K assets and findings, Dashboard 1.2 s, Assets 0.75 s,
      Findings 0.7 s, mostly exact counts. Estimated counts ("about
      500,000") and cached pick-list values, as proposed in
      [docs/DATABASE_PERFORMANCE.md](docs/DATABASE_PERFORMANCE.md); can be
      brought forward if it bothers users sooner
- [ ] Uploads folder permissions (from the Phase 2d part 3 review): the
      folder holding uploaded files should be readable only by the app's
      service account, not inherit the user's folder permissions
- [ ] Production database (decided 2026-09-29): a managed Linux Postgres,
      not a self-run or Windows one: Azure Database for PostgreSQL (Flexible
      Server), AWS RDS/Aurora or Google Cloud SQL, with pgvector enabled
      (all three support it), on SSD storage, sized per
      [docs/DATABASE_PERFORMANCE.md](docs/DATABASE_PERFORMANCE.md). Why:
      backups, patching, failover and monitoring built in (it holds
      customers' vulnerability data); Postgres is developed and tuned on
      Linux. Pick it with the hosting platform (same cloud as the app and the
      keyless Claude auth above). Dev stays on Windows Postgres, moved to the
      C: SSD (2026-09-29); Postgres in Docker (WSL2) is an option later for
      parity with CI's `pgvector/pgvector` image.
- [ ] Scaling for SaaS (discussed 2026-09-30): today one worker runs every
      job, oldest first, across all orgs (a 500K-row upload ~3-5 min, a
      500K-row purge ~1-2 min), so one tenant's queue or the auto-purge
      delays everyone (seen in verification: an upload waited 1 min 23 s
      behind 4 auto-purges in another org). Already in place: workers claim
      jobs with `FOR UPDATE SKIP LOCKED` (safe with several), one upload at
      a time per org, per-job check-ins. To add, roughly in order:
  - Several workers, scaled automatically on the number of waiting jobs
    (imports resuming from where they were cut off, Phase 2f, keeps a
    worker restart or scale-down cheap)
  - Fair turns between tenants (round-robin by org, a cap on each org's
    running jobs) instead of strictly oldest first
  - Separate worker groups: uploads; archive/purge (auto-purge already low
    priority; run it off-peak too); Phase 3's AI reports
  - Uploaded files in object storage (Azure Blob / S3) instead of
    `backend/uploads`, so any worker on any machine can read them
  - Database: a larger managed instance plus read replicas for list pages
    and the Dashboard; estimated counts (above); assets and findings
    partitioned by org, so purging an org or a big upload is near instant;
    later, a database of their own for very large tenants
  - Per-tenant limits by plan: file size, uploads running at once, rows
    per month
  - Monitoring: queue wait per tenant, job durations, alerts when waits
    grow
  - A dedicated queue service (Azure Service Bus, SQS) only if the
    database queue can't keep up
- [x] Core remediation workflow (original CoPilotSuggestions item): statuses,
      assignee, due/review dates, notes/history and role/version-safe bulk edits.
      Existing duplicate import/restore paths preserve edited workflows within
      current matching rules; this is not cross-scan reconciliation.
- [ ] Separate remediation policy work: stable imported identity/suppression and
      absence review; approved status-aware scoring/report semantics. Existing
      scores and saved reports remain unchanged. Ticketing integrations later.
- [ ] Production operations (CoPilotSuggestions, 2026-09-30), with the
      hosting choice: infrastructure as code; separate dev, staging and
      production; automated backups with point-in-time recovery and a
      restore actually tested; runbooks for migrations and rolling back a
      release (including the known `alembic` drift and the pgvector
      downgrade limit noted in Phase 2a)
- [ ] Security hardening, the rest of it (CoPilotSuggestions): secrets in
      the cloud's secret manager, with a rotation procedure; rate limits on
      sign-in, uploads and Claude calls; upload checks (content type, a
      malware-scanning policy); CORS reviewed for the production domain
- [x] Local observability implementation (CoPilotSuggestions): structured logs with request,
      job, org and user IDs to follow one action through web and worker;
      error tracking and alerts (worker not checking in, jobs failing
      repeatedly, database or storage nearly full, Claude outages);
      credentials, tokens and personal data never written to logs
- [ ] Hosted observability acceptance: persistent/exported telemetry, external
      alert delivery and production load/operational verification. Existing
      in-memory metrics and local tests are not production acceptance.
- [ ] Remaining automated checks (partial foundations already exist): a Playwright browser suite in
      CI for what's checked by hand today (sign-in, org switching, roles,
      uploads, worker recovery, archive/restore/purge, Activity, isolation
      between orgs); CI scans for vulnerable dependencies (pip-audit,
      npm audit), committed secrets and common code flaws (SAST); a
      separate, opt-in performance suite with million-row files
      Browser/dependency/secret/high-severity Bandit gates are now configured;
      Linux execution and dependency remediation passed in hosted run
      40377211631 at c008efc. Lower-severity static triage and opt-in performance
      CI remain pending. See the dependency compatibility record.

Work started on 2026-10-15:
- Observability: implementing structured JSON logs with request/job/org/user correlation IDs, metrics for latency/queue depth/worker heartbeat/import throughput/failures, error aggregation and alerts (stale workers, repeated failures, storage pressure, provider outages), traceability from reports/findings back to source scans/prompts, and redaction rules for credentials/tokens/PII — per CoPilotSuggestions.md Section 9
- Automated checks: backend/frontend, portable Linux browser acceptance and security scans passed hosted CI at c008efc. Opt-in performance CI and lower-severity static triage remain pending. See the current Phase 4 status matrix; historical delivery order is not current status.

## Phase 5 — Live connectors (not yet scheduled)

From CoPilotSuggestions (2026-09-30): only file uploads exist today;
CONNECTORS_SPEC.md describes identity, cloud, scanner, SIEM and backup
connectors, and `POST /assets/discover` is a placeholder (501 from Part 4).
Start with one per category, read-only, on a common pattern:

- [ ] The pattern: test connection, sync now, schedule, scope, cancel;
      credentials encrypted at rest and never returned by the API; health
      (last successful sync, duration, row counts, why it failed); retries
      and rate-limit handling; every configuration change and sync in
      Activity. Syncs run on the worker like uploads
- [ ] Suggested order: one cloud provider, one identity provider, the Nessus
      API, then SIEM and backup

## Deferred backlog — Standards and evidence expansion (after Phase 3)

**Decision (2026-10-08):** document additional standards, guidance, threat feeds,
and operational-evidence capabilities for a later phase. Not scheduled; no new
phase number assigned. These additions do not block Phase 3 sign-off.
Detailed scope, dependencies, and acceptance criteria are in
[Phase3.md — Deferred backlog](Phase3.md#deferred-backlog--additional-standards-and-evidence-sources).

- [ ] Expand beyond the agreed NIST baseline with selected SP 800-53/53A,
      contingency-planning and incident-response catalogs; add CISA performance
      goals and licensed ISO continuity/privacy sources as applicable.
- [ ] Add CISA KEV, FIRST EPSS, and NVD/CVE enrichment with refresh jobs,
      timestamps, stale-data handling, CVE matching, and report snapshots of
      the actual facts used.
- [ ] Add inventory-aware vendor guidance, product-specific CIS Benchmarks,
      and OWASP application/API guidance.
- [ ] Add MITRE ATT&CK threat/detection mappings with version and rationale.
- [ ] Add organization-selected regulatory/assurance packs (for example PCI
      DSS, SOC 2 criteria, HIPAA, GDPR, NIS2, DORA) only after applicability and
      licensing review; do not represent reports as certification or attestation.
- [ ] Add structured operational evidence: recovery objectives, restore-test
      results, incident exercises, and criticality-based evaluation.
- [ ] Extend cross-source governance: applicability selection, sourced versus
      inferred mappings, and prevention of duplicate risk deductions for the
      same finding across frameworks.

Phase 3 still includes the agreed CIS/NIST/ISO baseline, organization-policy
text/Markdown ingestion, source/version identity, organization isolation,
retrieval citations, and evidence provenance. Exact baseline editions remain
subject to the Phase 3 architecture decision. Verify source rights before
acquiring, processing, or distributing additional material. Scheduling this
backlog requires a separate decision; no additional integrations are being
implemented now.

## Test policy

- **Unit tests** (`backend/tests/unit/`): pure logic, no DB, always run.
- **Integration tests** (`backend/tests/integration/`): hit a real Postgres
  via `TEST_DATABASE_URL`; auto-skip with a clear reason if unreachable so CI
  and local runs never silently pass or hang.
- **Frontend**: `npm run build` + `npm run lint` gate every phase; component/
  interaction tests get added once real API wiring replaces the placeholder
  dashboard data (Phase 2).
- New backend logic ships with a unit test in the same change. New endpoints
  that touch the DB ship with an integration test in the same change.

## Future phase — Deferred delivery

User-approved deferrals (2026-10-22; scheduled-import addition 2026-10-27);
not core Phase 3 release gates:

- [ ] **Scheduled location-based imports:** user-defined schedule/time zone,
  server-accessible source or local agent, least-privilege credentials/location
  access, complete-file detection, retries/checkpoints and audit history. Reuse
  exact-file policy; unattended jobs must not wait for a browser prompt. A browser
  folder selection alone does not provide persistent server filesystem access.

- [ ] **Docker/container deployment:** review/update deployment packaging; build
  API and worker images; verify non-root permissions, secrets, network/health
  configuration and database migration readiness on the deployment host.
- [ ] **Persistent embedding/model cache:** provision the pinned model separately,
  mount it read-only, verify offline startup/retrieval and persistence across
  container replacement; prove no implicit model download or provider fallback.
- [ ] **Container operations/staging acceptance:** verify worker restart/recovery,
  logs/readiness, retained uploads, backups, rollback and browser behavior against
  the deployed stack before any container/production release claim.
- [ ] **Reporting-period browser controls:** optionally expose existing API date
  filters with clear UTC/current-inventory semantics and corresponding tests.

Existing Docker/cache instructions remain reference material for this phase,
not evidence of execution or approval to deploy. Current Phase 3 browser checks
use native local services, isolated synthetic data and mocked inference only.

## Upload wording follow-up (27 October 2026)

- [x] Implement shared source guidance, Remove/confirmed Close and Show/Hide labels.
- [x] Validate and activate locally without interrupting active imports.

Shared Assets/Findings uploads now distinguish compatible-source guidance from
unsupported files, visibly disable invalid Upload actions, use Remove per file,
and confirm Close before discarding queued files. Submitted imports continue.
Submission summaries are location-neutral; report disclosures use Show/Hide
labels matching their expanded state. Frontend regression: 428 tests passed;
lint and isolated production build passed. No backend contract changed.

## Resilience presentation follow-up (27 October 2026)

- [x] Retain former layout; apply shared risk-tier text colors only.
- [x] Implement explicit empty-organization Not assessed API/UI handling.
- [x] PostgreSQL/frontend/Chrome regression, production build and local activation.
- [x] Draft evidence-qualified dashboard contract using existing report profiles.
- [ ] Approve qualification contract, reviewer authority and organization-wide scope.
- [ ] Implement/review/test qualified domain and partial-overall scoring after approval.
- [x] Review exact scope/secrets and check in completed work in scoped commits.
- [ ] Push the reviewed commits and verify hosted CI for this tree (separate approval).

Next design increment: [Dashboard evidence-qualified scoring contract](docs/DASHBOARD_EVIDENCE_SCORING_DESIGN.md)
is drafted for approval, reusing existing seven report coverage profiles. No
partial-evidence dashboard scoring behavior has changed. Reviewer authority,
organization-wide scope and persisted qualification workflow require approval
before implementation.

Empty-organization safeguard: dashboard API explicitly returns `not_assessed`
with null overall/domain scores and tiers when active assets AND findings are
both zero; UI displays neutral Not assessed labels in existing cards. No database
migration. Asset-only/partial evidence, risk snapshots and saved reports retain
their existing contracts pending separate domain-coverage design. Frontend 434
tests passed; 61 focused PostgreSQL scoring/dashboard/archive tests and 70 Chrome
checks passed; lint/build/activation pass. The 61 include the initial 9 dashboard
tests, not a fresh full backend run. Earlier 1,281 full-backend results are historical.

Per user feedback, preserve the former compact layout and dashboard gradient;
change score/tier text colors only: Critical/red, High/orange, Medium/amber,
Low/green. No new badges, tinted domain surfaces or explanatory blocks.
Evidence and confidence remain separate; missing report scores stay neutral.
No scoring thresholds, stored
assessments, or exported report templates changed. Frontend: 433 tests passed;
ESLint and isolated production build passed.
