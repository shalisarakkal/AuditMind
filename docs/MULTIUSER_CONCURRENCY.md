# Same-organization multi-user concurrency review

25 October 2026. Local/testing review, not a production/load certification.
No real inference, paid calls or schema changes are part of this increment.

## Findings interaction

Checkbox selection now disables individual row Workflow, Archive and Undo actions.
Use the selected-actions bar, or Clear selection to return to row actions. This
also applies to unselected rows while any selection exists. Selection is local
to the browser, not an organization-wide reservation. Confirmation dialogs make
their own browser background inert; they do not block another person's browser.

## Backend concurrency contract

Lifecycle/authorization follow-up: privileged organization mutations now use
`api/deps.authorize_org_write` through `require_org_role`. Lock order is job
admission, Organization **NO KEY UPDATE**, then fresh organization/membership/
active-account validation. The fence lasts until commit/rollback. Readers remain
unlocked; same-organization write-admission transactions serialize and may wait.
NO KEY UPDATE preserves compatibility with background inventory foreign-key
KEY SHARE checks; the regression suite exercises that distinction explicitly.
Bulk archive admission repeats the check for every independently committed job.
If access is lost after prior jobs committed, their IDs remain in the result and
later items are refused, not silently queued and not falsely rolled back.

Manual finding creation takes the inventory advisory lock before refreshing its
references. Archived/cross-organization references return 422; references with
unfinished archive batches return 409. Organization archive/purge and role/member
changes cannot overtake a privileged transaction that has already acquired its
fence. A waiting transaction instead observes the committed change and is refused.

| Operation | Existing protection / increment | Important boundary |
| --- | --- | --- |
| Workflow single/bulk | Expected versions, row locks, organization/job coordination; stale version returns 409; bulk transaction rolls back all targets | Reload conflict explicitly; no silent overwrite |
| Archive/restore/purge | Job-admission advisory lock, one active job per batch, transactional chunks under organization lock | Bulk jobs can partially start; refusals are explicit, not atomic bulk workflow semantics |
| Imports | Organization advisory lock coordinates asset matching and publication against archive chunks | Browser selection does not reserve inventory |
| Ingestion/security settings | This increment locks and refreshes cached Organization before JSON merge | Different omitted fields survive; same explicitly submitted field is last successful writer, not version-conflict detection |
| Import profiles | This increment serializes create/update/delete per organization and refreshes cached profiles before merge | Name checking is serialized, including case-insensitive names; supplied maps replace whole maps; same-field last writer wins |
| Consent | This increment serializes first creation and updates, refreshing existing rows | Last successful approval/revocation wins; no new UI version token |
| People | Organization-row serialization protects last-admin checks for role/removal; role/removal end sessions; account operations have specific locks | This is not proof that all account/permission races across organizations are covered |
| Reports | Organization lifecycle check, scoped idempotency-key lock, accounting and worker row locks | Distinct/no idempotency keys can intentionally create distinct reports |
| Documents | Document/version/index row locks and organization lifecycle admission; retirement/index checks | Separate new documents are not deduplicated merely because titles match |
| Organization lifecycle | Exclusive organization-row locking and active-job boundary | Not a general lock on every currently open browser form |

Implementation references: `services/finding_workflow.py`, `archive_service.py`,
`org_lock.py`, `ingestion_service.py`, `people.py`, `platform.py`,
`report_service.py`, `knowledge_service.py`; routes `orgs.py`, `documents.py`,
`import_profiles.py`. API role/tenant checks remain required independently of UI.

## Review limits and remaining requirements

- Open lists do not provide an organization-wide real-time push guarantee. Another
  user's action may not appear until reload; backend validation is authoritative.
- Settings/profile/consent edits intentionally do not have workflow-style version
  tokens. Rejecting every stale form, including same-field changes, requires a
  separate API/UI optimistic-concurrency contract; serialization alone does not
  implement it. Full-map submissions count as explicit replacement, not a field merge.
- The admission fence covers privileged organization HTTP mutations, not platform
  routes, read-only endpoints, personal notification dismissals or every direct
  service invocation. Service-only lifecycle/worker guards remain necessary.
  Work already admitted and committed is not revoked retroactively; queued jobs
  are not cancelled merely because their initiator's role changes later.
- Existing tests cover representative races, not every operation pair, deadlock,
  retry, multi-worker crash or sustained high-concurrency load scenario.
- Selective Findings search is now indexed; short/broad search and sustained-load
  certification remain limited. See [search measurements](FINDING_SEARCH_PERFORMANCE.md).

These limits must not be represented as application-wide concurrency acceptance.
Indexed search is delivered in migration 0024, with a subsequent 1,203-test full
PostgreSQL regression pass. Version-token UX for settings/
profile/consent remains a separate optional contract, not provided by these locks.

## Reproduce tests

Latest lifecycle/authorization acceptance: **1,201 full PostgreSQL tests passed
in 604.85s**, warnings as errors, including all **10 new real-wait race cases**.
Those cases also passed focused in 6.71s; 76 existing focused tests passed in
91.03s before the full run (overlapping, not additive). Frontend 367 tests, lint,
isolated/normal production builds passed; 35 installed Chrome checks passed
(`phase3_browser_95ae93ed5925`). Demo restart and cancel-only live Chrome smoke
passed. Test DB restored to revision 0023, 30 tables, no browser schemas and clean
Alembic drift check. Search optimization remains pending step 3.

Measured: full backend 1,187 passed in 563.87s; then final focused configuration
file 7 passed in 4.34s after four cases added beyond the full run's collection.
These are overlapping results. Frontend 367 tests/lint/build and 35 installed
Chrome checks passed (`phase3_browser_ea1eb15a3a45`). Normal demo rebuild and
cancel-only live Chrome smoke passed. No paid or real inference calls.

From backend, use the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_multiuser_configuration.py --require-postgres -W error -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_write_admission.py --require-postgres -W error -q
.\.venv\Scripts\python.exe -m pytest --require-postgres -W error -q
```

New tests use distinct PostgreSQL sessions and distinct administrator identities;
they do not share a TestClient SQLAlchemy session across concurrent threads.
The suite blocks real HTTP calls. Browser acceptance remains in
`scripts/browser-finding-workflow.cjs` and includes conflict/reload, atomic bulk
conflicts, selected-vs-row action separation and modal background inertness.
