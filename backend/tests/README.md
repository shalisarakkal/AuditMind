# Backend verification

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
