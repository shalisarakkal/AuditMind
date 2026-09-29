# AuditMind AI — Delivery Plan

Tracks progress against the roadmap in `Blueprint.md` / `Architecture.md` (section 9).

## How this works

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
- Known follow-up (pre-existing, not Phase 2): `alembic check` reports model
  vs. migration drift on enum column types and the `users.email` index
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

- [x] Full suite green locally and in CI (413 backend, 77 frontend; CI green
      on fbaca45)
- [x] Your review + explicit approval to close out Phase 2 (2026-09-28)

**Status:** Closed 2026-09-28. Known gaps carried into Phase 2d part 1:
background import progress is lost on navigation, and pages are slow during
very large (500K-row) imports.

## Phase 2d — Imports at scale, then data lifecycle (next; Phase 2 signed off)

Its own phase, built with the feature-dev workflow once Phase 2 is signed off
and before Phase 3, so Phase 3's reports and documents get the same lifecycle
from the start. Two parts, each tested and checked in with you before the
next: part 1 first, because part 2 changes the same import write path.
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
      (activity logs), the note says so and Cancel is the way out. Judged per
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
- [ ] Your sign-off
- Later (Phase 4 hardening, not this part): background imports in a separate
  worker process; scans left "running" by a server restart; progress during
  the reading phase (~20 s of "Reading file…" for 500K rows). Reading large
  files in chunks (a 500K-row file peaks at ~1.1 GB while it's read and
  checked whole) moved to Phase 2e, which needs it

### Part 2 — Data lifecycle: archive, restore, purge

- [ ] Archive manually (never automatically): an upload (its scan, report and
      findings), a manually added asset or finding, or a whole organization.
      Archived data leaves the dashboard, scores and lists, and shows in an
      Archived view
- [ ] Shared assets, the safe approach: record which uploads touched each
      asset; archiving an upload archives only assets no other active upload
      uses, and its facts on the others
- [ ] Restore any archived item until it's purged. Archived findings don't
      count for duplicate checks; on restore, one that now duplicates an active
      finding is purged instead (the restore report says how many)
- [ ] Purge: only from the archive, admins only; an organization purge asks
      for its name. A purge log keeps what, who, when and how many rows
- [ ] Auto-purge `ARCHIVE_RETENTION_DAYS` (default 180) after archiving, set
      in `.env` and overridable per organization; each archived item shows a
      countdown ("Deleted in 173 days"). Runs daily in the app, plus a
      command for Task Scheduler/cron
- [ ] Organization archive: frozen for members; admins can restore or purge
- [ ] Repeat-upload warning (decided 2026-09-28): store each upload's SHA-256
      content hash; uploading a file whose hash matches an active upload in
      the same org warns ("already imported on <date> by <user>") and only
      proceeds when the user confirms. Warn, never block: re-importing after a
      settings or profile change is legitimate. Archived uploads don't count

## Phase 2e — Activity and audit log sources (after Phase 2d, before Phase 3)

Requested 2026-09-28, after `azure_azure_activity_500000.json` failed as a
generic asset list ("type is required" on all 500,000 rows): no import source
reads activity/audit logs. They record events (who did what, when), not
assets, so they should produce findings. Placed before Phase 3 so the AI
audit can reason over these findings too. Test files:
S:\AuditMind-Scratch\TestData\synthetic_assets\ (azure_azure_activity,
cloudtrail_cloudtrail, gcp_gcp_audit; 142-176 MB, 500K events each).

- [ ] Prerequisite, moved here from Phase 4: read large files in chunks
      (saved to disk, processed in batches), so memory stays flat at any
      size; all-or-nothing imports get a check-first pass. Log exports are
      routinely this large (split_json.py is the stopgap until then)
- [ ] Sources (import profiles) for Azure Activity Log, AWS CloudTrail and
      GCP Audit Logs, detected from their columns like the existing ones
- [ ] Endpoint security events in the OSSEM format (Sysmon/EDR telemetry;
      test file ossem_ossem_events_500000.csv: event_id, timestamp,
      user.name, process.name/pid/command_line, file.path, registry.key,
      network.src_ip/dst_ip, event_type). Signals in the sample: encoded
      PowerShell (-enc), Run-key persistence, DLLs in Temp. It names no host
      (no host.name column): decide what its findings attach to
      (network.src_ip? a host column in real exports?)
- [ ] Rules that turn events into findings, grouped rather than one per event
      (500K events would flood the list), e.g. role/permission assignments
      and policy changes (Identity & Access), deletions, firewall/network
      rule changes (Network & Config), repeated failed operations,
      logging/monitoring switched off (Monitoring & Detection)
- Open questions for the start of the phase: which events count as risky
  and at what thresholds; what a finding attaches to, since these records
  name a subscription/resource group/resource type but no resource ID (the
  subscription or resource group as an asset? the caller?); the time window
  (a whole export, or only recent events); whether to keep the raw events

## Phase 3 — AI audit & reporting (Week 3 of the roadmap)

**Scope:** load
CIS/NIST/ISO docs (pgvector is already set up), Claude-driven risk scoring with RAG citations, full report
generation endpoint.

- [ ] Not started
- Claude auth: keep `ANTHROPIC_API_KEY` in `backend/.env` for local dev, and
  keep every Claude call going through `app/services/claude_service.py`, so the
  auth method can change in one place later (see Phase 4).

## Phase 4 — Polish & resilience focus (Week 4 of the roadmap)

**Scope:** per-domain scoring refinement, remediation generation, PDF/HTML
export, security hardening (rate limiting, audit logging, secrets handling).

- [ ] Not started
- [ ] UI polish (requested 2026-09-28; can be done any time, needs no other
      phase):
  - File upload: drag and drop, and several files at once (each gets its own
    source choice and report)
  - Logos: an AuditMind product logo (sidebar, login/register, browser tab),
    plus each organization's own logo, uploaded by its admins (needs a small
    backend addition to store it)
  - Product name and the current organization's name shown in the UI header
- [ ] Keyless Claude auth for deployed environments (no long-lived API key):
      identity federation with the host platform's workload identity, or
      Amazon Bedrock / Google Vertex AI with cloud IAM if hosted on AWS/GCP.
      Decide once hosting is chosen; confirm what the Claude API supports at
      that point. Likely shape: a `CLAUDE_AUTH_MODE` setting read by
      `claude_service.py`, with local dev staying on the API key.

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
