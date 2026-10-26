# Phase 4 local operations increment

Subsequent approved dependency remediation: core/dev, optional embeddings and
installed audits are now clean, with no conflicts/ignores. The initial blocker
and old versions below are historical evidence. See
[current dependency compatibility record](BACKEND_DEPENDENCY_REMEDIATION.md).

26 October 2026. Synthetic/local testing only. No hosting, production deployment,
status-aware scoring, imported-finding reconciliation or live inference enabled.

## Dashboard and Activity

The noisy Recent activity feed is replaced by a security summary. Cards count
completed `member_added`, `role_changed` and `purge` events whose **start time**
falls in the exact rolling seven-day interval `[window_start, window_end)`.
Membership additions are not globally created accounts; purge operations are
not deleted-record totals. Event retention can limit historical completeness.

`GET /orgs/{org_id}/dashboard/security-summary` returns the interval and counts
using organization membership authorization. Global/platform events are excluded.
Failed sign-ins are labelled unavailable rather than attributed to unrelated
organizations or displayed as a misleading zero.

Each card opens Activity with its organization, type, completed outcome and exact
UTC instants. The displayed period uses the browser timezone. `window_start` and
`window_end` must be paired, aware datetimes in increasing order; invalid requests
return 422. Existing day filters intersect API windows, but changing a day filter
in the UI replaces the exact window. Clear filters removes both. Zero-count cards
remain links; load failure shows an error/retry, not fabricated counts.

## Readiness

`GET /health` remains cheap process liveness. `GET /ready` returns 200 only when
all three checks pass, otherwise 503; responses are non-cacheable and contain
only `status` and boolean `checks.database`, `checks.uploads`, `checks.worker`.

- Dedicated PostgreSQL connection, no shared pool wait; connect timeout 2 seconds
  per connection attempt and statement timeout 1 second. This is not a strict
  wall-clock bound on DNS, OS filesystem calls or multiple resolved host addresses.
- Upload directory must exist and pass process read/write/traverse access checks.
  The probe creates no directories/files and is **not** a service-account ACL,
  malware, disk-capacity or durable-write certification.
- Worker heartbeat must exist, not be future-dated and be younger than half
  `WORKER_STALE_SECONDS`, matching the existing worker-status freshness policy.

No URLs, credentials, paths or exception text are returned. Hosted exposure/rate
policy belongs to deployment hardening, not this local probe. A 503 for an absent
upload directory or stopped worker is intentional; do not weaken the checks just
to make them green.

## File import and product branding

Choose several files or drop files onto the upload area (up to 20 queued cards).
Each file has its own source detection/selection, duplicate confirmation, cancel,
error and report. Upload controls reuse the existing backend import endpoints and
worker behavior; this is not an atomic multi-file transaction. Accepted files
remain tracked even if another file fails. Cancel dismisses only that file's
pending card. Organization changes discard unsubmitted cards.

The code-native product mark is shared by Sidebar and sign-in/register; the
browser icon uses the same shield/check motif. The signed-in header shows product
and current organization. **Organization-uploaded logos are not implemented**;
file validation/storage/permissions must be completed separately, including the
compatibility testing documented in the subsequent dependency remediation record.

## CI and security gates

CI configuration now uses required PostgreSQL/warnings-as-errors backend tests,
explicit pgvector/pg_trgm prerequisites, `npm ci`, frontend lint/tests/build and
npm dependency audit. A separate Linux browser job installs Chromium, builds the
isolated frontend and runs mocked-inference acceptance with artifact upload.
The harness supports Linux Python paths/process-group cleanup and keeps installed
Chrome as the local default. **Linux/hosted CI execution is not yet verified**;
Windows Chrome success is not proof of hosted CI success.

Security job config adds pinned pip-audit 2.10.1, Bandit 1.9.4 high-severity checks,
and `scripts/check_tracked_secrets.py`. The secret guard reports locations only
and detects selected provider/private-key patterns and forbidden credential files;
it does not scan ignored files/history or replace a full secret-scanning service.
Bandit medium/low findings remain to be triaged, not silently waived. A
deterministic non-security MD5 feature bucket now explicitly uses
`usedforsecurity=False`; vector values are unchanged.

**Initial backend audit (subsequently remediated):** 34 reported
advisory entries across six packages (entries include duplicates), from
`pip-audit -r requirements-dev.txt`:

| Package | Audited version | Reported remediation state |
|---|---|---|
| python-jose | 3.5.0 | No fixed version listed |
| ecdsa | 0.19.2 | No fixed version listed |
| anyio | 4.14.1 | Fix listed at 4.14.2 |
| python-multipart | 0.0.20 | Fixes listed through 0.0.31 |
| pytest | 8.3.4 | Fix listed at 9.0.3 |
| starlette | 0.41.3 | Multiple advisories, fixes listed through 1.3.1 |

These were scanner observations that motivated the separately approved upgrade.
See the current remediation record above; no ignores, forced overrides or new
risk exception were added. npm audit also reports zero vulnerabilities. Hosted
CI still requires actual execution before being considered passed.

Remaining local Phase 4 work includes organization logos, upload-directory ACL
policy, broader request throttling/malware policy, full static-findings triage,
large-org count/facet improvements and opt-in performance CI. Hosting, scoring,
reconciliation and other user-approved deferrals remain separate.

## Validation and handoff

This is the preceding local-operations checkpoint. The dependency remediation
record above supersedes its original audit result and dependency-stack evidence.

- Full PostgreSQL regression: **1,229 passed** in 651.52s, required PostgreSQL,
  warnings as errors. Collection preceded the four new secret-guard cases and
  final response-schema/non-security-hash refinements.
- Final focused PostgreSQL/unit rerun: **20 passed** in 7.08s, covering the final
  summary schema, readiness, embedding behavior and all four new guard tests.
  This overlaps the full run and is not an additive full-suite total.
- Final frontend: **376 passed** in 21.87s; lint and production builds passed.
- Installed Chrome: **39 checks passed**, isolated PostgreSQL/API/worker and
  mocked inference (`phase3_browser_70424e695eb3`). Includes Dashboard scoped Axe,
  desktop/mobile screenshots, exact Activity links and both real file imports.
- npm audit: zero vulnerabilities. Tracked-file secret guard and Bandit
  high-severity gate passed. Bandit still reports 12 low/16 medium findings outside
  that gate; no all-severity static clearance is claimed.
- CI YAML parsed locally. Linux hosted execution is not yet verified. The backend
  dependency audit is failing as documented, not green or waived.

No new inference/provider calls or migration required. At this historical
checkpoint changes were uncommitted; scoped commits are now authorized and
recorded in [check-in preparation](CHECKIN_PREPARATION.md). The unrelated
`cline.json` is untouched.
The demo was rebuilt/restarted with data/passwords retained. Live `/health`
returned `ok`; `/ready` returned `ready` with all three checks true. Disposable
`auditmind_test` was restored to 0024: migration round-trip/drift checks clean,
30 public tables and zero leftover browser schemas.
