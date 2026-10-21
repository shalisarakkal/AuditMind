# Backend validation — 2026-10-20

The local test target is restored to PostgreSQL `auditmind_test`, with pgvector
0.8.6. The ignored local `backend/.env` was corrected; `.env.example` already
contains the proper target. The development database was not migrated.

## Changes reviewed

- Test target validation rejects SQLite, malformed URLs (including invalid ports),
  and names without `_test`, before destructive fixture setup.
- Fixture cleanup removes stale Alembic revision markers together with application
  tables. Previously the database claimed revision `0009` with no application tables.
- Alembic accepts an explicitly supplied connection and version-table schema for
  isolated migration tests. Ordinary CLI commands continue to use `DATABASE_URL`.
- Migration regression creates a random schema only inside `auditmind_test`,
  upgrades from empty to head, rolls back to `0018`, upgrades a legacy report,
  checks reporting indexes and timestamps, repeats the upgrade, then cleans up.

## Results

- Complete backend suite: **783 passed, 7 failed, 0 skipped**, 450.40 seconds.
- After the final fixture changes, all unit and health tests, authentication and
  report API integrations, database safety regressions, and migration regressions:
  **395 passed**, 26.08 seconds.
- Fresh Alembic upgrade of `auditmind_test`: **passed**, revision **0020 (head)**,
  27 application tables. A repeated upgrade also passed.
- `alembic check` against that freshly migrated database: **failed**. Differences
  include enum VARCHAR lengths, reporting/document indexes missing from ORM
  metadata, and the users email unique constraint/index representation.
- Changed tracked test infrastructure passes `git diff --check`; Python
  compilation checks pass.

The complete run was started before the new test-infrastructure regressions were
added; the focused follow-up validates those additions and the final fixture code.
These results do not constitute a green complete suite.

## Baseline review findings (resolved below)

1. Five cases of `test_claude_problems_come_back_as_clear_errors` fail because
   `api/routes/ai.py` catches `ValueError` but the tested Anthropic exceptions
   propagate. Expected HTTP error mapping is not preserved.
2. `test_bulk_retire_and_remove_versions` expects purge to succeed while pending
   publication jobs still reference the versions; the API correctly reports a
   conflict under its current protection rule. Reconcile the test/workflow contract.
3. `test_reactivate_retired_version_reindexes_before_publishing` ends with a 503.
   Its embedding mock does not accept the retrieval adapter's `query=True` keyword.
4. Additional code review found that `claude_service.ask_claude()` references an
   undefined `get_client()`. Mocked report-generation tests do not cover this real
   provider initialization path.
5. Schema/model drift was unresolved in this baseline; resolved in Step 4 below.

No provider requests, model downloads, or development-database migrations were
performed. The unrelated AI/document behavior and existing migration history were
preserved for separate fixes.

See [backend testing instructions](../backend/tests/README.md) for repeatable
unit/integration/regression and migration test commands.

## Step 4 — Schema/model drift resolved

The migrated schema was already correct. ORM declarations now preserve its seven
legacy `VARCHAR(50)` enum columns, named email unique constraint and separate
lookup index, and three composite reporting/document indexes. Newer enum columns
retain their inferred lengths. No migration file or existing data was changed.

Review confirmed that uniqueness enforcement, enum conversion/validation, and
organization-first index column ordering remain intact. The changes pass Python
compilation and scoped whitespace checks.

- Focused schema-contract and migration regressions: **14 passed**.
- Complete backend suite, including the final changes: **805 passed, 7 failed,
  0 skipped**, 453.10 seconds. The same five Claude error-mapping and two document
  cases listed above remain; no new failures appeared.
- Migration regression now runs `alembic check` after a fresh migration and
  rollback/re-upgrade cycle in its isolated schema.
- Read-only `alembic check` against the development database: **passed**;
  current revision remains `0020`. No development migration was run.
- After the suite, `auditmind_test` was rebuilt from empty through Alembic:
  fresh upgrade, drift check, and repeated upgrade all **passed**. It is left at
  `0020 (head)` with 27 application tables and pgvector intact.

Step 4 is complete. At that checkpoint, the remaining AI/document failures and
missing Claude client factory still prevented a green complete suite; these are
resolved in the follow-up below.

## AI/document follow-up — complete suite green

Restored synchronized, lazy Claude client initialization with the configured
timeout and SDK retries disabled, so application retries bound total attempts.
Provider failures now preserve explicit HTTP status mapping without exposing raw
provider evidence. Attempt statistics are counted once, and invalid structured
responses no longer log their contents.

Retirement now cancels queued publication work and disables publication by running
jobs. Purge remains blocked until running work acknowledges retirement. Review
also corrected a stale-session race by refreshing index status under its row
lock. The retrieval embedding mock now accepts the adapter's query keyword.

- Focused Claude/document/API regressions: **41 passed**.
- Final complete backend suite: **827 passed, 0 failed, 0 skipped**, 475.10 seconds.
- The suite emitted **1,740 warnings**, suppressed in its summary run; this is
  not a warning-free result.
- Python compilation and scoped tracked whitespace checks: **passed**.
- After the suite, fresh Alembic upgrade, schema-drift check, and repeated upgrade
  of the verified `auditmind_test` target: **passed**. The test database is left
  at revision **0020**, with 27 application tables.
- Migration regression coverage includes rollback/re-upgrade in an isolated
  schema. No development-database migration was performed.

All five baseline review findings above are resolved. Provider calls were mocked;
these results do not establish live Claude connectivity or production readiness.

## Operational completion and repository cleanup — 2026-10-20

Item 5 implementation now includes PostgreSQL-backed per-attempt quota/cost
reservations, durable token accounting, concurrent organization-scoped report
idempotency, configurable terminal-report retention, and an offline embedding
API/worker image with an external read-only model cache. Migration `0021` adds
the ledger and idempotency constraint; no existing migration was rewritten for
these additions. See [operational contracts](PHASE3_OPERATIONS.md).

Review checked transaction boundaries (no quota lock held during provider I/O),
cross-process admission serialization, conservative charging of unknown outcomes,
idempotent replay/conflict and organization isolation, active-job retention
exclusion, evidence-link cleanup, and page-local retry-key reuse. Provider failure
paths remain mocked. Tests cover independent concurrent database sessions, durable
state after process-metric reset, token/cost recording, and no network call after
quota rejection. Static packaging tests verify offline pinned-model loading,
cache configuration, secret exclusion, non-root image identity, and release-task
migrations rather than startup migrations.

- Final complete backend suite: **837 passed, 0 failed, 0 skipped**, 472.21 seconds.
- **1,774 warnings** remain; this is not a warning-free result.
- Frontend: **239 tests passed**, ESLint passed, production build and TypeScript
  checks passed.
- Python compilation, scoped/staged whitespace checks, and `pip check`: passed.
- Fresh upgrade, schema-drift check, and repeated upgrade of `auditmind_test`:
  passed at **0021**, with **28 application tables**. Rollback/re-upgrade coverage
  is included in the complete suite's isolated-schema migration test.
- No development-database migration, provider request, or model download was run.

Item 6 cleanup reconciles the current roadmap/status with these results, adds
line-ending rules and normalizes pending source/docs, and removes the empty stray
`backend/[--part-mb` artifact (no data was stored there). The application and
archived NIST catalogs still match the documented SHA-256. Project work is grouped
into local source-data, backend/deployment, backend-regression, frontend, and
documentation commits; unrelated local `cline.json` remains untouched. No push is
part of this task.

**Release gate still open:** Docker is unavailable on this machine. Container
build/startup, mounted-cache semantic verification, and staging end-to-end/live
provider checks have not run. Packaging is implemented and statically checked,
not runtime-certified. Full Phase 3 acceptance and production sign-off remain
separate from the green automated suite. The new migration must be applied through
an approved release procedure before these changes run against a real database.
