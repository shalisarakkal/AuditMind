# Phase 3 operational controls

## Report input limits — audit-evidence-v3

See [closure/budget contract](PHASE3_CLOSURE.md#budget-contract) for exact selection
and omission semantics. New defaults: `REPORT_AI_MAX_INPUT_BYTES=65536` for the
complete prompt/schema/system text and `REPORT_AI_FINDING_TEXT_BYTES=2048` per
description; 256-byte labels, existing 20-finding/8-citation sample caps and
4096-token output ceiling. Limits are byte-based, not exact model token limits.
Oversized fixed metadata fails before report-provider admission; partial finding
text and whole-record omissions are disclosed in provenance and to the model.
Citation text/hashes/spans are not silently clipped. Source data is unchanged.

This is prompt version **audit-evidence-v3**. Budget settings are included in
consent/queued-job targets. After a deployment using this version, an authorized
organization admin must review/reapprove the new target before new AI work.
Old pinned jobs fail on target change. Existing reports retain their saved values.
No consent, keys, provider enablement or live inference was changed by implementation.

Remediation follow-up (2026-10-22): production dependency audit is clean and
provider-attempt authorization now refreshes live job ownership/status/cancellation
before quota reservation. Seven development-tool audit entries rooted in unpatched
braces remain; model/pricing readiness requires separate approval. The native/mock
Chrome checklist passed; see [acceptance evidence](PHASE3_ACCEPTANCE.md).
Date fields and Docker/container staging are deferred to Future by user approval.
Ledger estimates are not provider-enforced billing ceilings. An issued
request cannot be aborted; do not enable inference solely because consent is approved.
See [current code review and release gates](RELEASE_READINESS.md).

## Approved core release scope — 2026-10-21

`/risk/score` remains deterministic, local and independent of Claude consent,
availability and quotas. Claude/RAG assessments run through asynchronous reports.
Reports retain the captured deterministic baseline separately from AI scores;
dashboard scores remain deterministic and current rather than report snapshots.
This preserves reproducibility, explicit transmission consent, predictable cost
and latency, and one auditable AI job lifecycle.

Approved shared tiers are Low 80–100, Medium 60–79, High 40–59, Critical 0–39.
New AI assessments and rule-based test reports now share deterministic tier logic;
do not reinterpret saved legacy reports. Phase 3a is delivered separately; local
embeddings do not generate reports. Phase 3b is a future proposal, not current
report-provider support.

## Database and release order

The agreed Claude/local provider direction and synthetic local feasibility
procedure are documented in [Local reporting plan](LOCAL_REPORTING_PLAN.md).
Local generation remains a separate implementation; it is not enabled by this plan.

Migration `0021` adds the durable `ai_usage` ledger and organization-scoped report
idempotency constraint. Back up and test restore first; run `alembic upgrade head`
once as a release task before starting the new API and worker. Application startup
does not run migrations. Do not roll the schema back while new processes are active.
The migration regression covers fresh installation and rollback/re-upgrade in an
isolated test schema; no development or production migration is authorized by tests.

## Report consent

Optional OpenRouter transport is implemented for mock-only testing and remains
disabled by default. See [OpenRouter reporting](OPENROUTER_REPORTING.md) for its
explicit route, consent target, pinned jobs, actual reported cost handling and
remaining live gates. It does not enable local generation or automatically switch
the active provider. No new migration is required beyond `0021`.

Organization archive is refused while org-owned uploads, archive jobs, reports or
document indexes are pending/running. Job admission is serialized against archive
with organization row locks; legacy queued jobs fail closed for inactive orgs.
See [Phase 2e acceptance](PHASE2E_ACCEPTANCE.md) for concurrency and Chrome evidence.

Report consent is rechecked before each provider attempt, including retries after
timeouts or temporary failures. A revoked approval stops the next attempt before
quota admission; it cannot undo an already-issued request. The consent read
transaction ends before provider I/O. Publication also requires current consent.

## Assessment contract v2

New AI reports use prompt `audit-evidence-v3`, schema version 2, and scoring rubric
`shared-tiers-v1`. The consent target includes the prompt version and budget settings, so prior v1/v2
consent no longer authorizes new generation: an organization admin must approve
the displayed updated target in Documents settings. Queued jobs lacking current
consent fail closed. No database migration or existing-report rewrite is required.

Each AI remediation requires confidence in [0,1] and explicit UUID lists
`affected_finding_ids` / `affected_asset_ids`. Confidence represents model-estimated
support, not a calibrated likelihood, verified certainty, or certification. Finding
IDs must appear in the captured sample; asset IDs must link to the findings cited
by that action. Malformed, duplicate and invented/out-of-sample IDs fail generation
before snapshot persistence. References do not assert coverage of every finding.

General guidance may use empty lists and must explain evidence limitations; an
assetless finding never gets a fabricated asset ID. Reference absence is displayed
explicitly. Non-AI test reports use null confidence, not invented model confidence.
Report UI, HTML and PDF preserve confidence and identifiers. Retained v1 reports
without those fields remain readable and show unavailable metadata rather than
being assigned new confidence, references, or tiers.

## Consistent evidence capture

Report inventory totals/categories, finding counts, sampled finding values,
deterministic scores and retrieved document excerpts are read in one independent
PostgreSQL `REPEATABLE READ` transaction. The caller's identity map and isolation
settings are not reused or changed. Default embedding-profile initialization is
committed separately before starting the evidence snapshot.

The capture transaction also registers report/source-version usage. Source locks
are acquired in UUID order; registration commits atomically with the capture and
the capture session closes before Claude generation/retries. Purge remains blocked
for sources used by an active report. Later retirement does not rewrite captured
evidence. A source change that causes a serialization conflict restarts the entire
capture, at most three attempts; repeated conflicts fail the report instead of
mixing results or committing partial usage registrations. Deadlocks use the same
bounded retry policy. A report ID must belong to the evidence organization.

Provenance records `evidence_capture` (isolation level, attempt count and database
clock start/read-completion timestamps), plus captured inventory totals/categories.
Reporting dates still select currently active findings created within inclusive
UTC dates, not historical inventory reconstructed for that period.

Authorization is deliberately not historical. External query-embedding consent
and selected-profile identity are checked through a fresh `READ COMMITTED` session;
revocation or profile changes cannot be hidden by the older evidence snapshot.
Claude consent is independently checked before generation attempts and publication.

The evidence transaction spans query embedding and retrieval, so slow model loading
or embedding operations can lengthen it; source row locks are acquired only at the
registration stage. It does not span Claude generation, backoff or retries. Monitor
capture latency and database connection capacity in staging. Embedding authorization
is checked at query-operation boundaries; an already-issued SDK operation (including
its provider-managed internal retries) is not aborted by revocation.

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

## Future phase: embedding image and offline model cache

User decision (2026-10-22): Docker/container deployment and the associated
build/startup/cache-persistence/restart acceptance are deferred, not Phase 3
blockers. Instructions below are retained for that future work, not execution
approval or a claim of deployment readiness. Native browser acceptance continues.

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
validation machine: container build/startup and mounted-cache smoke tests are
Future-phase acceptance on a Docker-capable host, not core Phase 3 gates. No live provider calls or new model
downloads are included in the automated tests.

## Local browser demonstration

For a synthetic, loopback-only tour, use `start-demo.ps1` and the
[user manual](USER_MANUAL.md). This uses an isolated `auditmind_demo` schema,
leaves ordinary application tables/revision untouched, disables external provider
credentials and enables explicitly non-AI test reports. Local Chrome smoke testing
covers navigation, sessions, worker readiness and HTML/PDF reports; it is not full
Phase 3 browser acceptance, real-provider testing or a production deployment.
