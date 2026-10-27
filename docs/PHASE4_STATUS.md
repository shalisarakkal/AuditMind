# Phase 4 status and next milestone

## Current handoff — 26 October 2026

Organization logo management and header name/size preferences, platform-admin
product-logo sizing, active approved SVG assets, single-brand authentication
presentation and shared Show/Hide password controls are implemented locally.
Migrations 0025–0028 cover organization branding; platform presentation uses the
existing platform_settings table. Final combined-tree review passed: **1,268 full
PostgreSQL tests**, **413 frontend tests**, **61 Chrome executions**, lint/build,
migration checks and dependency/static gates. Scoped commits, push and hosted CI
verification are approved and in progress. [Authoritative acceptance record](PHASE4_VALIDATION.md).

Phase 4 remains partial. Large-org broad-search/count/facet performance, ACLs/
throttling/malware policy, lower-severity static triage, tenant-fair scheduling and
production hosting/monitoring acceptance remain open. Imported identity and
status-aware scoring need separate design approval. Docker/cache deployment and
report-date UI remain Future. None is silently waived by local test success.

## Historical local checkpoints

Latest password UI: shared hidden-by-default Show/Hide control for all password
entry fields and temporary-password handovers, independent/keyboard accessible;
no storage/API changes. 411 frontend tests, 61 Chrome checks and lint/build passed. Backend evidence
below is historical, not rerun for this UI-only change. [Acceptance](PHASE4_VALIDATION.md).
Local changes remain uncommitted/unpushed; hosted CI has not run this tree.

Latest platform branding: platform-admin-only sidebar product size under Platform
→ Product branding, Small/Medium/Large; authenticated readers use it platform-wide.
Sign-in/company branding unchanged. 406 frontend and 54 focused backend/migration/
platform checks and 55 Chrome executions passed, plus lint/build. Uses existing platform_settings; no new
migration (head 0028). [Current evidence](PHASE4_VALIDATION.md). Uncommitted/unpushed.

Latest company-name size setting: Small 16px, Medium 20px (larger default), Large
24px, saved per organization/admin-only; selector and product branding unchanged.
Migration 0028 retains logos/preferences. 399 frontend and 28 focused/migration
PostgreSQL and 52 Chrome checks passed, plus lint/build. [Current evidence](PHASE4_VALIDATION.md).
Local changes remain uncommitted/unpushed; hosted CI has not run this tree.

Current logo-size follow-up: admin-configurable Small/Medium/Large header logo,
default Medium 160×64px; matching Settings preview, no product-logo changes.
Migration 0027 retains existing images/name preferences. 395 frontend, 27
focused/migration PostgreSQL and 50 Chrome checks passed; lint/build passed. These local changes
are uncommitted/unpushed. [Current evidence](PHASE4_VALIDATION.md).

Latest header branding: larger 180×48 sidebar product-logo box, 16px organization
name and admin-only saved header-name visibility preference (migration 0026).
Missing/broken logos retain the name. 391 frontend tests, 24 focused backend tests,
two migration tests and 48 Chrome executions passed; lint/build passed. Earlier
full backend counts below are not reruns. [Validation](PHASE4_VALIDATION.md).

Latest auth presentation: one larger user-supplied product logo above the shared
login/register card; 385 frontend tests and 47 grouped Chrome executions passed.
Backend/authentication policy unchanged. [Validation scope](PHASE4_VALIDATION.md).

Product-asset follow-up: fixed replaceable SVG wordmark/favicon paths, 383 frontend
tests and 43 Chrome checks passed. [Replacement instructions](PRODUCT_BRANDING.md).
Defaults remain provisional; this local follow-up is uncommitted/unpushed.

Latest local increment: [organization logos](ORGANIZATION_LOGOS.md), migration
0025, 1,260 full PostgreSQL / 382 frontend / 42 Chrome checks passed. This feature
is uncommitted/unpushed; hosted CI at c008efc remains the preceding green baseline.
Roadmap entries incorrectly listing baseline CI/dependency remediation pending
have been reconciled. Hardening/performance and production acceptance remain open.

Code/document reconciliation: 26 October 2026, after pushed checkpoint
`79c4a66`, followed by the user-approved local operations increment. See
[implementation, validation scope and security blocker](PHASE4_LOCAL_OPERATIONS.md).
Phase 4 is **partially delivered**, not globally complete. The local remediation
increment is delivered; production/live-AI approval is separate.

The subsequent dependency increment now has clean core/dev, optional and installed
audits, plus conflict-free resolution. The initial 34-entry blocker below is
historical; see [compatibility/test record](BACKEND_DEPENDENCY_REMEDIATION.md).

## Roadmap checked against code

| Item | Verified status | Evidence / remaining scope |
|---|---|---|
| Remediation status, assignment, deadlines, notes/history, bulk edits | Implemented for local testing | `backend/app/services/finding_workflow.py`; Findings UI; version/role checks and atomic workflow bulk validation. |
| Browser-local deadlines and date filters | Implemented | Author timezone/fixed expiry, today through inclusive local end of day, creation boundary; global dark native date inputs. Legacy Eastern metadata retained. |
| Selection, archive confirmations, IDs and shared UI | Implemented for documented scope | Findings, Archived, Assets, Uploads; manual finding entry; inline Documents preview; full-width Settings; timed routine notices. |
| Workflow preservation on import/restore | Partial, bounded | Existing matching skips exact duplicates; archive restore protects edited workflow (`workflow_version = 0` duplicate purge guard). This is not stable cross-scan identity or absence reconciliation. |
| Imported individual suppression and comparable-scan absence review | Design only | `FINDING_RECONCILIATION_DESIGN.md`; implementation and identity contract still require approval. |
| Status-aware scoring / report changes | Separate design decision | Scoring/report snapshots intentionally unchanged. Do not mark this implemented merely because workflow is delivered. |
| Further per-domain refinement and export polish | Baseline exists; additional scope not defined | `scoring_service.py` implements deterministic domain scores; reports route exports HTML/JSON/PDF. Phase 4 refinements beyond those delivered features require concrete acceptance criteria, not duplicate implementation or a blanket completion checkbox. |
| Dashboard security summary | Implemented locally | Three completed organization-event counts; exact Activity links; global failed sign-ins explicitly unavailable. Scores unchanged. |
| Drag/drop and multiple-file import | Implemented locally | Independent per-file source/duplicate/cancel/error/report flow; 20 queued-card limit. |
| Product/organization logos and common header branding | Implemented locally | Product mark in sidebar/authentication and browser icon; organization name/company logo only in header. Org-admin logo/visibility/name and image sizing, migrations 0025–0028; platform-admin product sizing with version checks. See ORGANIZATION_LOGOS.md / PRODUCT_BRANDING.md. |
| Password visibility | Implemented locally | Shared masked-by-default keyboard-accessible Show/Hide on auth/change-password fields and temporary handovers; copy without reveal. Values/autocomplete/submission retained. |
| Dependency readiness endpoint | Implemented locally | `/health` remains cheap; `/ready` checks PostgreSQL, upload access and worker freshness with redacted responses. Hosted acceptance pending. |
| Large-organization list performance | Partial | Indexed selective Findings search delivered; short/broad searches remain slow. Dashboard/list exact counts remain; estimated counts and cached facets not completed. |
| Security hardening | Partial | Sign-in process-local limiter and durable AI accounting exist. Shared/distributed request limits, dedicated upload request throttling, malware policy, service-account ACL validation and production secrets/CORS need further work. File-size limits are not request-rate limits. |
| Observability | Local implementation present; hosted acceptance pending | Structured logs/correlation, worker metrics/alerts and unit tests exist. Metrics are in-memory; external alert delivery/load/production monitoring is not certified. |
| CI automation | Hosted jobs exercised; final per-SHA status linked | Required PostgreSQL/warnings-as-errors, npm ci, Linux Chromium and security gates exercised. Clean-install failures corrected; Linux backend 1,244 passed, hosted browser/frontend/security passed. See dependency record for final run. Medium/low SAST triage and opt-in performance jobs remain pending. |
| Multi-worker SaaS fairness/storage/scaling | Partial foundations; pending rollout | `FOR UPDATE SKIP LOCKED`, resumable jobs and heartbeat exist. Tenant-fair scheduling, autoscaling, separate worker groups, shared object storage and plan limits are not delivered as a SaaS operating model. |
| Hosting/keyless provider auth/managed DB/backups/production operations | Hosting-dependent, not implemented/accepted | Hosting choice and separate deployment authorization required. Existing local test success is not backup/restore, workload-identity or production acceptance. |

User-approved Future items remain Future: Docker/container deployment, persistent
embedding/model-cache deployment, container/staging acceptance and report-period
UI. Other hosting-dependent requirements remain recorded in Phase 4; this review
does not silently defer or waive them. Phase 5 live connectors are not started.

## Dashboard security summary milestone

Implemented locally in this increment. The following acceptance contract explains
the scope; this is not a production/hosted security clearance.

Replace the noisy Recent activity panel with the previously requested seven-day
organization security summary. Preserve scores, source evidence and reports.

1. Define the precise window and matching Activity deep links. Prefer an exact
   rolling seven-day UTC interval shared by counts and destination filters;
   browser-local rendering is presentation only. Document that it is not seven
   calendar dates. If Activity cannot express the same interval, extend its filter
   contract rather than link to a different range.
2. Count organization-scoped member additions, role changes and completed purge
   events. Distinguish membership additions from globally created user accounts,
   and purge operations from counts of deleted records. Do not infer missing
   history from current memberships or invent totals.
3. Resolve failed-sign-in attribution before adding that card: never expose
   platform/global authentication events to unrelated organizations or attribute
   an event to every organization a user belongs to. Omit/label unavailable data
   until a safe source contract exists; do not display a misleading zero.
4. Retain routine sign-ins/worker events in full Activity, not summary cards.
   Provide accessible links, loading/error/empty states and responsive layout
   using existing UI controls. Avoid full event-log transfer to the browser.
5. Test with PostgreSQL: tenant/role boundaries, exact interval boundaries,
   correct event categories, purge counts and unrelated/global events. Add
   component/link/error regressions and installed-Chrome desktop/mobile/Axe
   acceptance. Run full backend/frontend/build gates before delivery.

`/ready` and portable browser/security CI are also implemented/configured locally.
The dependency increment resolves the initial audit findings without ignores;
local regression acceptance is recorded below; subsequent hosted evidence is in
[dependency follow-up](BACKEND_DEPENDENCY_REMEDIATION.md).
Organization logos are delivered in the subsequent local increment. ACL/throttling/malware policy, static-analysis triage and large-
org performance remain pending. Scoring, reconciliation and hosting stay separate.

## Current validation baseline

Subsequent clean-install follow-up: Linux backend **1,244 passed**, frontend
**377 passed**, **39 local Chrome checks**, hosted browser/frontend/security
passed; [exact SHA scope and final CI link](BACKEND_DEPENDENCY_REMEDIATION.md).
The preceding checkpoint below is retained as history.

After dependency remediation, full PostgreSQL: **1,238 passed** (628.60s), warnings
as errors. Focused compatibility **73 passed** and JWT **14 passed** overlap this
full run. Frontend: **376 passed** (29.03s), lint/production build/TypeScript and
**39 Chrome workflow checks**, plus **6 separately grouped Documents checks**.
All three backend audit scopes are clean; dependency resolution has no conflicts.
Focused counts overlap the full suite and are not additive; hosted CI/security
clearance is not implied. See [validation history](PHASE4_VALIDATION.md),
[release boundaries](RELEASE_READINESS.md) and
[user walkthrough](PHASE4_USER_VERIFICATION.md).
