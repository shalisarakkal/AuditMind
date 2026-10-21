# AuditMind - Additional Support Required

**Review date:** 2026-09-30
**Scope:** Review of the current repository, roadmap, API surface, frontend pages, tests, and architecture documents.

## Executive assessment

AuditMind has a solid ingestion and data-management foundation. Multi-tenant organization membership, role checks, CSV/JSON/Nessus imports, import profiles, progress tracking, archive/restore/purge workflows, activity history, server-side list filtering, and a substantial automated test suite are already present.

The main gap is that the current product is still primarily a secure data-ingestion and rule-based scoring application. The capabilities that make it an AI-powered cyber-resilience auditor - standards retrieval, Claude-backed analysis, explainable remediation, report generation, and live connectors - are still planned rather than implemented.

## Priority 0 - Required before calling the product production-ready

### 1. Complete the AI audit and reporting pipeline

**Current state:** `backend/app/api/routes/ai.py` exposes only a Claude smoke-test endpoint. `backend/app/api/routes/reports.py` creates a pending report record but does not generate a report. The risk engine remains rule-based v1. The `documents`/pgvector model exists, but ingestion, embedding, retrieval, citations, and prompt orchestration are not wired together.

**Support required:**

- A standards/document ingestion job for CIS, NIST, ISO, and organization documents.
- Chunking, embedding, metadata, source versioning, and tenant isolation for RAG documents.
- Retrieval with citations that survive into the API response and generated report.
- Structured Claude responses validated by Pydantic schemas rather than free-form text.
- AI-assisted domain scoring that preserves the deterministic score as a baseline and records model, prompt version, input period, and evidence used.
- Remediation recommendations with priority, affected assets/findings, rationale, owner/status, and confidence.
- Background report jobs with progress, retry, cancellation, failure details, and idempotency.
- HTML and PDF output, download authorization, report retention, and immutable report snapshots.
- Token/cost/latency tracking, model timeouts, bounded retries, and provider failure handling.

**Recommendation:** Treat this as the next major product milestone after the currently planned Phase 2e/2f prerequisites. Do not make AI output overwrite the deterministic score without storing both values and the evidence used.

### 2. Finish identity and organization administration

**Current state:** Organization membership and per-organization roles exist, but the roadmap still requires a platform Sysadmin, controlled organization creation, user creation, role changes, deactivation, password reset, and organization lifecycle administration.

**Support required:**

- Sysadmin role and protected platform administration routes/UI.
- Admin-managed user invitations or temporary-password creation.
- First-login password change and self-service password change.
- Admin/Sysadmin reset flow, account deactivation, membership removal, and role changes.
- Protection against removing the last organization administrator.
- Session invalidation after password change, reset, deactivation, or role change.
- Email delivery integration later, with a local/non-email fallback for development.
- Organization archive/restore/purge rules and explicit cross-tenant access tests.

### 3. Make large-file ingestion memory-bounded

**Current state:** The worker and upload persistence are implemented, but large-file parsing still reads too much data into memory. `backend/scripts/split_json.py` is explicitly a stopgap. This is especially important for the planned 142-176 MB activity-log exports.

**Support required:**

- Streaming CSV and incremental JSON parsing from the saved upload.
- A check-first pass for all-or-nothing imports.
- Batch-level transactions and progress for both reading and writing.
- A memory ceiling test across files larger than available worker memory.
- Cleanup and recovery for orphaned upload files after worker/database failure.
- Explicit limits for decompression, malformed input, and pathological JSON.

## Priority 1 - Required for a useful audit product

### 4. Add activity-log and security-event import support

The roadmap identifies Azure Activity Log, AWS CloudTrail, GCP Audit Logs, and OSSEM/EDR events as missing. These sources should produce grouped findings rather than one finding per event.

Before implementation, define:

- Which event families are risky and their thresholds.
- The time window represented by an import.
- How events attach to an asset when no host is present.
- Which raw events are retained and how they are queried or sampled.
- Deduplication and grouping keys for repeated activity.

### 5. Implement connectors incrementally

`CONNECTORS_SPEC.md` defines identity, cloud, vulnerability scanner, SIEM, and backup connectors, but the repository currently supports file-based imports rather than live connectors. The placeholder discovery route in `backend/app/api/routes/assets.py` confirms this boundary.

Start with one connector per category, preferably read-only, and establish a common connector contract:

- Credential validation and least-privilege documentation.
- Encrypted secret storage and rotation.
- Test connection, sync now, schedule, scope, and cancellation.
- Connector health, last successful sync, duration, row counts, and failure reason.
- Retry/backoff and rate-limit handling.
- Idempotent scans and normalized source metadata.
- Audit events for configuration and sync operations.

Suggested first connector order: one cloud provider, one identity provider, Nessus API, then SIEM and backup integrations.

### 6. Add remediation workflow support

The UI currently displays findings and imports, but the planned AI experience needs a lifecycle for remediation:

- Finding status: open, accepted, mitigated, resolved, and false positive.
- Assignment, due date, notes, evidence, and history.
- Bulk status/assignment changes with authorization checks.
- Re-import behavior that does not erase analyst decisions.
- Status-aware scoring and report generation.
- Optional integrations with ticketing systems after the local workflow is stable.

## Priority 1 - Production operations and security

### 7. Establish deployment and disaster-recovery support

The project has local Docker assets and CI validation, but not a complete production operating model. Before customer data is hosted, add:

- A chosen cloud architecture and infrastructure-as-code.
- Separate development, staging, and production environments.
- Managed PostgreSQL with pgvector, SSD storage, automated backups, point-in-time recovery, and tested restore procedures.
- Database migration and rollback runbooks, including the known pgvector extension ownership limitation.
- Object storage for uploads, reports, and documents rather than relying on local disk.
- Worker/web scaling rules and a strategy for multiple workers.
- Health/readiness checks for database, worker, storage, and AI provider dependencies.
- Deployment rollback and schema compatibility rules.

The current Windows PostgreSQL-on-HDD setup is suitable for development but should not be used as the production performance baseline. The documented SSD and managed-Postgres work in `docs/DATABASE_PERFORMANCE.md` should be completed or explicitly accepted as a development-only limitation.

### 8. Improve secrets and access security

- Fail startup when production uses the default `SECRET_KEY` or weak configuration.
- Use a cloud secret manager or equivalent for database, Claude, connector, and signing secrets.
- Define key rotation and JWT/session revocation procedures.
- Encrypt connector credentials at rest and never return them through settings APIs.
- Add rate limits and quotas, especially for authentication, uploads, connector syncs, and Claude calls.
- Add upload content-type validation, malware scanning policy, decompression limits, and service-account-only upload-directory permissions.
- Review CORS, security headers, CSRF implications of browser token storage, and cookie/token strategy before external deployment.

### 9. Add observability and operational alerting

The activity log is useful for audit history, but it is not a replacement for service observability. Add:

- Structured JSON logs with request/job/org/user correlation IDs.
- Metrics for request latency, database timings, queue depth, worker heartbeat, import throughput, failures, report generation, and Claude cost/tokens.
- Error aggregation and alerts for stale workers, repeated job failures, database/storage pressure, and provider outages.
- Traceability from a report or finding back to its source scan, document chunks, prompt version, and model response.
- Redaction rules for credentials, tokens, raw sensitive data, and personal information.

## Priority 2 - Quality and maintainability support

### 10. Automate browser, accessibility, and security validation

The repository has strong backend and frontend unit/integration coverage, but browser E2E verification is described as manual. Add a Playwright suite covering:

- Login, organization switching, role restrictions, uploads, worker recovery, archive/restore/purge, activity, and report download.
- Cross-organization isolation and expired-session behavior.
- Large-file progress after navigation and refresh.

Also add CI jobs for dependency auditing, secret scanning, SAST, container scanning, API security checks, and accessibility smoke tests. Keep a small representative fixture set and a separate opt-in performance suite for million-row data.

### 11. Resolve known technical debt before the schema grows

- Resolve or document the `alembic check` model/migration drift.
- Make downgrade behavior explicit around the pgvector extension, or provide a supported rollback procedure.
- Add trigram/full-text search where contains-search performance becomes unacceptable at multi-million-row scale.
- Complete the measured page-request performance check while a 500K-row job is running.
- Add contract tests for consistent error response shapes and pagination/filter semantics.
- Update the README status, which currently describes the project as Week 1 even though the roadmap records substantial Phase 2 progress.

## Suggested delivery order

1. Complete user/organization administration and memory-bounded imports.
2. Add activity-log sources and define their finding/grouping semantics.
3. Build the document/RAG pipeline and deterministic-plus-AI scoring contract.
4. Implement background report generation, citations, remediation workflow, and export.
5. Add one production-grade connector and use its patterns for the remaining connector families.
6. Harden deployment, secrets, backups, observability, and automated browser/security validation.

## What is already well supported

- Multi-organization membership and organization-scoped authorization.
- CSV, JSON, Nessus, and profile-based imports with validation and deduplication.
- Large-job queueing, worker recovery, progress tracking, and activity events.
- Archive, restore, purge, retention, and bulk operations.
- Paginated, searchable, sortable asset/finding/activity/archive views.
- Rule-based risk scoring and dashboard aggregation.
- Security-focused parser tests, real-PostgreSQL integration tests, and frontend interaction tests.

The project does not need a broad rewrite. It needs the unfinished product capabilities and operational controls above to be completed around the existing ingestion core.
