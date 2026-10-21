# Phase 3 operational controls

## Database and release order

Migration `0021` adds the durable `ai_usage` ledger and organization-scoped report
idempotency constraint. Back up and test restore first; run `alembic upgrade head`
once as a release task before starting the new API and worker. Application startup
does not run migrations. Do not roll the schema back while new processes are active.
The migration regression covers fresh installation and rollback/re-upgrade in an
isolated test schema; no development or production migration is authorized by tests.

## Quotas and estimated cost

Every organization-scoped SDK attempt reserves admission in PostgreSQL before
network I/O. Transaction-scoped advisory locks serialize admission per organization
across processes. `CLAUDE_ORG_CALLS_PER_HOUR` (100) and
`CLAUDE_ORG_MAX_COST_PER_HOUR_USD` (50) apply over a rolling hour; retries each count
as an attempt. Admission failure returns 429 on the smoke endpoint and fails report
jobs clearly. The smoke endpoint attributes calls to the caller's first administered
organization ordered by ID. Report calls use the report's organization.

Each attempt reserves the larger of `CLAUDE_ATTEMPT_RESERVE_USD` (1) and an estimated
input/output bound. Successful SDK usage replaces that reservation with estimated
cost and records input/output tokens. Failed, interrupted, or unknown outcomes
retain their reservation for the remainder of the rolling hour. Database admission
failure is fail-closed; no provider request is made. Restarting a worker does not
reset admission. Metrics in memory remain diagnostic only, not the quota authority.

Costs use the application's model-family rate estimates, not live provider billing.
They are not an invoice or a guaranteed dollar spending cap. Validate/update rates
for the configured model and use provider-side billing limits for a hard budget.
The ledger stores model, tokens, costs, timestamps and status, never prompt text or
response contents. It is retained until organization deletion; ledger archival is
a separate operational decision. Settings changes require restarting API/workers.

## Report idempotency

Send `Idempotency-Key` (1–128 nonblank characters) to
`POST /api/v1/orgs/{org_id}/reports/generate`. Matching retries return the same report
with 202; a key reused with different title/frameworks/dates returns 409. Locks and
a unique database constraint prevent concurrent duplicates. Organization boundaries
remain enforced. Requests without a key deliberately create a new report.

The browser retains a key for an unchanged request after a failed submission and
clears it after success; changes to organization, mode or payload produce a new key.
This retry state is page-local, not persisted across a full reload. Clients needing
cross-reload recovery must retain their key. Deletion/retention removes a report's
key; keys are not permanent tombstones and must not be reused for a new intent.

## Report retention

`REPORT_RETENTION_DAYS` defaults to 365. Worker daily housekeeping deletes terminal
reports in batches of at most 500; pending/running reports are excluded and locked
rows are skipped. Expiry uses completion time, falling back to cancellation/last
heartbeat/run-start/creation for failed or legacy records. Evidence-use links
cascade with report deletion. This is permanent deletion: recover only from backups.
Configure the value to meet the organization's retention requirements before
deploying. Retention runs independently of archive auto-purge; no running worker
means no automated report retention. Large backlogs need repeated housekeeping
passes. Report retention does not delete usage ledger entries.

## Embedding image and offline model cache

`backend/Dockerfile` supports `INSTALL_EMBEDDINGS=true`, runs as UID 10001, and
excludes `.env`, uploads, tests and the virtual environment from its build context.
The model cache is external to the image. No model download occurs at startup.
The API also needs the embedding runtime because retrieval embeds queries.

1. In a controlled environment with adequate CPU/RAM/disk, install
   `backend/requirements-embeddings.txt`. Set `AUDITMIND_MODEL_CACHE` to an explicit
   cache directory, then run `python scripts/setup_embeddings.py --download` from
   `backend`. This explicitly permits downloading the pinned BGE-M3 revision.
2. Run the same script without `--download` to verify cache-only semantic retrieval.
   Copy that complete cache to the deployment host, readable by UID 10001. Do not
   commit model weights, private documents, secrets, or runtime uploads.
3. Provide `backend/.env` through your deployment secret mechanism and set
   `AUDITMIND_MODEL_CACHE_HOST` to the populated host cache. `DATABASE_URL` must be
   reachable from containers; `localhost` inside a container is not the host DB.
4. From the repository root, run
   `docker compose -f infra/compose.embeddings.yml build api`, then
   `docker compose -f infra/compose.embeddings.yml run --rm api alembic upgrade head`,
   then `docker compose -f infra/compose.embeddings.yml up -d api worker`.
5. Verify cache access inside the image with
   `docker compose -f infra/compose.embeddings.yml run --rm api python scripts/setup_embeddings.py`.
   Verify API health, a document indexing job, retrieval, worker recovery and report
   generation in staging before production. The cache is mounted read-only; uploads
   use a shared writable volume. Supply reverse proxy/TLS and frontend separately.

Runtime sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; missing cached weights
fail explicitly. The old `infra/docker-compose.yml` is a legacy development setup,
not the embedding deployment package. Docker is unavailable on the current Windows
validation machine: container build/startup and mounted-cache smoke tests remain
required on a Docker-capable staging host. No live provider calls or new model
downloads are included in the automated tests.
