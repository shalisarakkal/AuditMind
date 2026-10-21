# AuditMind Code Review

**Review date:** 2026-09-30
**Review target:** Current repository plus the uncommitted change set shown by `git status`. The change set adds skipped/duplicate row details to import reports and lets users open a past upload report from the Uploads page.

## Findings

### 1. Medium - Archived upload reports remain directly accessible

**Location:** `backend/app/api/routes/scans.py:68-92`

`GET /orgs/{org_id}/scans/{scan_id}` and `POST .../dismiss` check the organization and membership, but do not check `Scan.archived_at`. The list endpoints correctly exclude archived scans, so an archived upload disappears from the Uploads page while a caller who retains or guesses its UUID can still retrieve its complete report, including row-level errors, warnings, skipped items, duplicate items, and raw import metadata. A caller can also mutate its dismissal state after archival.

This conflicts with the archive contract in `archive_service`/the roadmap that archived data leaves every list and normal read path. It is not a cross-organization leak, but it breaks the lifecycle boundary and can expose data that an administrator intended to remove from active access.

**Suggested fix:** Add `Scan.archived_at.is_(None)` to both lookups, or centralize an active-scan lookup helper. Add integration tests proving that an archived scan returns `404` from both endpoints while its archive record remains available through the Archived workflow.

### 2. Medium - Discovery advertises an accepted job that cannot run

**Location:** `backend/app/api/routes/assets.py:208-213`

`POST /orgs/{org_id}/assets/discover` returns `202 Accepted` and a `not_implemented` status. A client can interpret `202` as a queued discovery and wait for a scan that will never exist. This is especially risky because the endpoint is presented as a real asset workflow in the architecture/API documentation.

**Suggested fix:** Until the connector worker exists, return `501 Not Implemented` with a documented error schema, or remove/hide the route. Once implemented, create and return a real scan/job ID and test completion and failure behavior.

### 3. Medium - Report generation creates jobs that never complete

**Location:** `backend/app/api/routes/reports.py:21-35`

`POST /orgs/{org_id}/reports/generate` returns `202 Accepted` but only inserts a `pending` report. There is no report worker, Claude orchestration, RAG retrieval, status transition, generated content, or output location connected to this route. The frontend reports page also tells users that generation arrives in Phase 3.

The endpoint therefore accepts work without a completion path. API consumers can permanently poll a pending report, and the database accumulates records that look like real report jobs.

**Suggested fix:** Keep this endpoint unavailable until the Phase 3 pipeline is wired, returning `501`, or implement a report job using the existing worker queue with explicit retries, failure details, idempotency, and a completion test. Do not expose `202` for a job that cannot progress.

### 4. High - Production can start with a known default signing secret

**Location:** `backend/app/core/config.py:23`

`SECRET_KEY` defaults to `change-me-to-a-random-secret`, and application startup does not reject that value. If deployment configuration is incomplete, JWTs can be forged by anyone who knows the repository default. This is a deployment-fatal security configuration, not merely a development convenience.

**Suggested fix:** Make `SECRET_KEY` required outside an explicitly selected development environment and reject the known default and weak values during startup. Add a configuration test and document secret rotation and token invalidation.

### 5. Medium - Health endpoint cannot detect unusable service dependencies

**Location:** `backend/app/main.py:52-54`

`GET /health` always returns `200 {"status": "ok"}` without checking PostgreSQL, the worker heartbeat, upload storage, or required AI configuration. A load balancer or orchestrator can keep routing traffic to an instance that cannot serve authenticated requests or process queued jobs.

**Suggested fix:** Keep `/health` as a cheap liveness probe and add `/ready` with bounded checks for the database and required storage/worker conditions. Return dependency-specific status without leaking credentials or internal connection details. Add tests for healthy and unavailable dependencies.

### 6. Medium - Claude failures and resource usage are not bounded

**Location:** `backend/app/services/claude_service.py:8-23` and `backend/app/api/routes/ai.py:12-18`

The Claude client call has no timeout, retry policy, circuit breaker, request quota, token/cost accounting, or normalized provider-error handling. The authenticated smoke-test route can be called repeatedly by any authenticated user and turns provider failures into generic server errors. The same design would be unsafe to reuse for report generation.

**Suggested fix:** Put provider calls behind a service boundary with explicit connect/read timeouts, bounded retry for transient errors, a circuit breaker, per-organization/user quotas, structured error mapping, and usage telemetry. Validate structured model output before persisting scores or reports. Add mocked timeout, rate-limit, malformed-response, and provider-error tests.

### 7. Medium - Browser authentication remains exposed to XSS

**Location:** `frontend/src/lib/apiClient.ts:1-29`

The JWT is stored in `localStorage`, so any successful script injection in the frontend can read and exfiltrate the token. The current React rendering is generally text-safe, but the application accepts imported content and will gain connector/reporting surfaces, increasing the amount of untrusted data and third-party code around authenticated pages.

**Suggested fix:** Prefer a short-lived access token in memory plus a refresh token in an `HttpOnly`, `Secure`, `SameSite` cookie, with CSRF protection where required. If `localStorage` is retained temporarily, add a documented threat-model exception, strict CSP/security headers, dependency scanning, and an explicit token-revocation strategy.

### 8. Medium - Active-list and report APIs will become unbounded

**Locations:** `backend/app/api/routes/reports.py:14-18`, `backend/app/api/routes/scans.py:20-47`

`list_reports` returns every report for an organization with no pagination, ordering, or archive filter. `list_scans` returns the full matching list when neither `active` nor `tracked` is selected. These endpoints are acceptable for the current small dataset but will degrade as uploads and reports accumulate, especially because report summaries can contain up to 1,000 row notes.

**Suggested fix:** Apply the existing paging conventions, default ordering, and active-row filters. Keep list responses brief and fetch a full report only by ID. Add a large-history integration test and query-plan/performance coverage.

## Current change-set assessment

The new import-report behavior is coherent and well covered:

- `RowNote` is consistently represented in the backend schema and frontend types.
- Duplicate notes distinguish an earlier upload, an earlier row in the same file, and a manually added finding.
- The Uploads page fetches the full scan only when a user expands a report, avoiding full report payloads in the list response.
- React renders the imported item/message values as text, not HTML.
- The expanded report is available to organization members, matching the documented report-visibility decision.

No blocking defect was found in the changed import matching/report logic during this review. The archived-scan issue above is adjacent to the new full-report retrieval path and should be fixed before relying on that UI in production.

## Test and validation results

- Backend: **514 passed** using `backend\.venv\Scripts\python.exe -m pytest`.
- Frontend: **153 passed** using `npm test -- --run` from `frontend`.
- Frontend lint: passed.
- Frontend production build/typecheck: passed.
- Workspace diagnostics: no errors reported.
- `git diff --check`: passed; only existing line-ending warnings were reported by Git.

## Test gaps and residual risk

- No automated browser E2E suite is present for archive, report expansion, worker recovery, and cross-organization flows.
- No CI SAST, dependency audit, container scan, secret scan, or API rate-limit test is visible.
- No test currently asserts that archived scans cannot be fetched or dismissed directly.
- Claude is covered by wiring/smoke behavior rather than deterministic contract tests for timeouts, malformed output, cost limits, and provider outages.
- Connector discovery, RAG, report generation, remediation workflow, and production user administration remain planned functionality rather than implemented behavior.

## Review conclusion

The ingestion and archival implementation is comparatively mature and the current report-detail change is supported by passing backend/frontend tests. Before external deployment, fix the archived-scan access path and the insecure default secret, then make placeholder/unfinished endpoints fail explicitly or connect them to real jobs. The next substantial engineering milestone remains the Phase 3 AI/RAG/report pipeline, with operational controls built into that work rather than added after customer data is present.
