# Backend verification

Clean CI installation: `requirements-dev.txt` explicitly includes both `httpx`
(existing adapters/tests) and `httpx2` (modern Starlette TestClient). Installing
the optional OpenAI SDK must not be required to collect tests without warnings.
Real synchronous/asynchronous transports for both clients are blocked by default.
Hosted browser CI enables `vector` and `pg_trgm` in its fresh PostgreSQL database
before fixture setup; the server image alone does not enable extensions.

Remediation verification (2026-10-22): full suite **987 passed** with warnings as
errors. Final expanded/strengthened cancellation/provider regressions **24 passed**,
including two direct-Anthropic cases added after the full run was collected.
No live inference. Disposable auditmind_test restored to 0021 after all DB fixtures;
Alembic metadata check clean and repeated upgrade a no-op.
See [current code review and release gates](../../docs/RELEASE_READINESS.md).

For acceptance runs, use `--require-postgres` with warnings as errors and branch
coverage. It fails on unavailable PostgreSQL or skipped tests. Real httpx
transports are blocked by default; provider tests must install mocked transports.
See [testing strategy and reproducible coverage commands](../../docs/TESTING.md).
Install `requirements-dev.txt` for pinned coverage tools. Integration fixtures
use real PostgreSQL/pgvector, never a SQLite substitute.

Run commands from `backend` with the backend virtual environment.
Set `TEST_DATABASE_URL` in `.env` to the dedicated PostgreSQL database
`auditmind_test` (see `.env.example`). It must have the `vector` extension.
The test fixtures create and drop application tables; never use the development
database as the test target. SQLite and database names without `_test` are refused.
Metadata-based fixture cleanup also removes Alembic revision markers so an empty
test database cannot falsely advertise an applied migration history.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

This runs unit, API integration, worker, regression, and migration tests.
JWT and Starlette test-client deprecation warnings are errors in `pytest.ini`,
including during test collection. Other warning categories remain visible; there
are no new ignore filters. For a stricter local run, use `pytest -q -W error`.
Database tests skip when the configured test database is missing or unreachable;
check the result for skipped tests rather than treating those as verification.
CI supplies `auditmind_test` with PostgreSQL and pgvector.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_migrations.py -q
```

The migration regression uses Alembic rather than SQLAlchemy `create_all`.
Inside `auditmind_test`, it creates a random isolated schema, upgrades from an
empty schema to head, rolls back to `0018`, inserts a legacy report, upgrades
again, verifies the preserved report and reporting indexes, and runs Alembic's
schema/model drift check against the isolated migrated schema. It then removes
only that temporary schema. This also runs as part of the complete suite.

Ordinary `alembic` commands still target `DATABASE_URL`, which is the application
database. Do not run them expecting `TEST_DATABASE_URL` to be selected automatically.
Schema/model drift (`alembic check`) is distinct from whether migrations execute
successfully; both results should be reported.

Operational regressions are in `integration/test_report_operations.py`: separate
PostgreSQL sessions exercise concurrent quota admission and idempotent requests,
restart-resistant ledger state, token/cost recording, blocked network calls, and
terminal-report retention. `unit/test_embedding_packaging.py` checks offline cache
loading and static deployment contracts. These do not build/start containers;
follow [the staging checks](../../docs/PHASE3_OPERATIONS.md) on a Docker-capable host.

`integration/test_evidence_snapshot.py` exercises real PostgreSQL repeatable-read
capture with independent concurrent writers: insert/archive/update/delete races,
document publication conflicts and whole-capture retries, atomic source usage,
source purge protection, pool isolation reset, live consent/profile changes,
pending caller-state preservation and report ownership checks. Provider calls are
mocked; synchronization uses events rather than sleeps.

## Dependency warning compatibility

PyJWT 2.15.1 replaces python-jose/ecdsa after the 26 October dependency audit.
Security regressions cover token expiry, signed round trips, session identifiers,
wrong signing keys and unsigned-token rejection, alongside the auth/session API
tests. No token format or password hashing changes are intended.

The coordinated stack is pinned to FastAPI 0.162.0, Starlette 1.10.0 and AnyIO
4.14.2; multipart parser 0.0.32 and pytest 9.0.3 address the other audited pins.
No warning suppression or site-packages patch is used. Legacy independently
signed HS256 tokens remain a compatibility fixture; malformed session-claim
types must return unauthorized rather than raise server errors. See
[dependency remediation](../../docs/BACKEND_DEPENDENCY_REMEDIATION.md).

`integration/test_demo_setup.py` verifies local-only target/schema selection,
disabled external credentials, closed sign-up and idempotent synthetic seeding
without resetting passwords or user edits. Its database fixtures still use only
`auditmind_test`. The actual local browser tour uses a separate demo schema;
see [the user manual](../../docs/USER_MANUAL.md). The optional root script
`scripts/browser-demo-smoke.cjs` uses installed Chrome and credentials supplied
through AUDITMIND_DEMO_PASSWORD / AUDITMIND_PLATFORM_PASSWORD, never hardcoded keys.
