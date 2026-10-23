# Phase 2e acceptance evidence — 2026-10-21

Review synchronization (2026-10-22): Historical/design record: original dates, results and proposals are preserved. This is not fresh test evidence or current release sign-off.
See [current code review and release gates](RELEASE_READINESS.md).

Engineering verification of PLAN.md Phase 2e Parts 1–3 and the lifecycle transferred
from Phase 2d Part 2. The original standalone verification guide was not present in
the current tracked tree; this checklist is reconstructed from the plan's actual
requirements and checked against code. Historical user sign-off is retained; this
document does not grant a new sign-off or production deployment approval.

## Real browser acceptance

`node scripts/browser-phase2e.cjs` passed 25 grouped checks in installed Chrome
155.0.8059.85, headless, desktop 1440×1000. No API behavior was mocked: browser
requests used a transport-only redirect from the running frontend to a separate
loopback API on 8011. A real worker and PostgreSQL schema were used. All external
provider credentials were blank; no model downloads or generation calls occurred.

Prerequisites: the existing production frontend running at `http://localhost:3000`,
installed Playwright/Chrome and backend dependencies, a reachable local
`auditmind_test` configured in `backend/.env`, and port 8011 free. The fixture
processes load settings from the backend working directory. Do not point this
harness at a public site; the fixed loopback transport is intentional.

| Part | Browser acceptance — passed |
| --- | --- |
| 1 | Closed registration and hidden sign-up link; real CSP/anti-framing headers |
| 1 | Token absent from localStorage; HttpOnly/Strict cookie scoped to auth; renewal on reload |
| 1 | Mandatory first-password change; protected page cannot bypass it |
| 1 | Role change, reset and deactivation revoke existing sign-ins |
| 1 | Failed sign-ins lock the account; correct password reveals lock; admin unlocks |
| 1 | Account session listing and sign-out of other browsers |
| 1 | Self rename; weak/reused password rejection; password change revokes other sessions |
| 1 | Idle and maximum session expiry; expired temporary password rejection |
| 1 | Explicit logout clears the renewal cookie and returns to login |
| 2 | Admin creates a person and receives the temporary password once |
| 2 | Viewer reads People without management actions; non-Sysadmin platform denial |
| 2 | Role selection/confirmation, rename, reset, unlock and membership removal |
| 2 | Existing account reused without password/name replacement; account survives removal |
| 2 | Multi-org rename/reset restricted; own-row demote/remove/reset actions absent |
| 3 | Sysadmin reads organization data without membership and without write actions |
| 3 | Organization creation with first admin; existing-account first-admin reuse |
| 3 | Last active admin deactivation refused; Sysadmin self-row restricted |
| 3 | Sysadmin changes multi-org name/email; deactivation and reactivation |
| 3 | Organization security range validation, save/reload, reset to default |
| 3 | Platform defaults propagate; complex password policy enabled |
| 3 | Organization archive makes member UI read-only; restore re-enables actions |
| 3 | Running report and document-index fixtures each block archive in the UI |
| 3 | Exact-name purge confirmation; real worker removes organization, accounts survive |
| 2/3 | Organization and platform Activity show administration events |

Long time limits were tested by aging only the isolated fixture rows through the
restricted fixture CLI, not by waiting days or changing the operating-system clock.
Running-job browser fixtures have no provider work and are explicitly terminalized
after the archive refusal check. Screenshots and machine-readable results are in
ignored `temp/auditmind-demo/browser/phase2e/`; passwords are not written there.

The harness creates a unique `phase2e_browser_<12 hex>` schema only in local
`auditmind_test`, and refuses reuse. It stops its own child API/worker processes,
then drops only that validated synthetic schema in `finally`. The accepted run
confirmed cleanup. Existing application/demo accounts, SA01, passwords, consent
and platform defaults were not modified. Browser fixtures use ORM-created tables;
migration validation is a separate test-database check, not browser proof.

## Archive boundary and code review

- Count pending/running uploads, archive jobs, reports and organization-owned
  document indexes. Shared standards or other organizations' work do not block.
- Job admission takes an organization `FOR SHARE` lock through its commit;
  organization archive takes `FOR UPDATE`, then counts jobs. State is re-read
  directly from columns, not trusted from an older ORM identity-map value.
- Apply admission to reports, document uploads/reindex/reactivation, import
  upload admission/retry/manual scans, and archive job creation.
- Fail legacy report jobs closed for archived/purging/missing organizations before
  generation. Index jobs check lifecycle before work, each embedding batch and
  publication. Already-issued external operations cannot be recalled.
- Regression tests exercise both concurrent orderings: archive wins and admission
  refuses after waiting; admission wins and archive sees the committed active job.
- No database migration or consent change is required by this fix.

## Automated and environment qualifications

Full backend run: **918 passed**, `pytest -q -W error`, 536.17 seconds, no skips.
Final focused run against the admission refinements: **139 passed**, `-W error`,
149.05 seconds, no skips. Test database restored to **0021**, 28 application tables;
`alembic check` found no new upgrade operations, repeated upgrade succeeded, and
no temporary browser schemas remained. See also
[BACKEND_VALIDATION.md](BACKEND_VALIDATION.md).
Frontend: **274 passed**; ESLint passed. Frontend implementation was unchanged.

Backend tests additionally exercise policy ranges/strictest multi-org composition,
CSRF/origin rejection, per-address rate limiting, Unicode/history/expiry rules,
cross-org API denial, concurrent last-admin protection, archive/purge scope,
worker recovery and source-retention rules. These are backend checks, not claims
that every parameter combination was independently clicked in Chrome.

Local HTTP intentionally uses non-Secure cookies; production Secure-cookie/TLS,
real reverse-proxy client-address forwarding, multi-instance rate-limit behavior,
mobile/cross-browser testing and deployment acceptance remain separate. Email
invitation/confirmation/reset links remain future email-service scope, not omitted
Phase 2e functionality. Phase 3 provider/staging gates are not closed by this work.
