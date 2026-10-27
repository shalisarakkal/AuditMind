# Phase 4 status and next milestone

## Current local closure review — 27 October 2026

Reviewed code paths against the recorded validation and activation evidence.
The following increments are **complete locally**, not production release approval:

- [x] Shared multi-file queue: ready-first sequential submission, grouped duplicate
  decisions, source-attention/failure groups, retry/stop and accepted-file exclusion.
- [x] Organization Ask/Skip/Reimport policy, in-flight duplicate protection,
  organization/hash serialization and audited skips.
- [x] Page-wide multi-file drag/drop without browser file navigation.
- [x] Clear source guidance, visibly disabled invalid Upload, per-file Remove,
  confirmed Close preserving submitted work, and contextual Show/Hide disclosure.
- [x] Original resilience layout retained, risk-tier text colors shared across
  Dashboard/browser Reports; no downloaded-template or scoring-threshold changes.
- [x] Empty-organization dashboard: zero active assets AND findings returns
  explicit not_assessed/null scores and neutral Not assessed cards.
- [x] Local activation and health: idle restart, data/accounts preserved,
  database/uploads/worker ready and frontend login HTTP 200.
- [x] User manual, validation, verification and plan follow-ups synchronized.
- [x] Evidence-qualified dashboard **draft prepared** using existing report profiles.

Latest combined increment evidence: **434 frontend tests**, **61 focused PostgreSQL
scoring/dashboard/archive tests**, **70 Chrome executions**, ESLint and production
builds passed. The 61 include the initial 9 dashboard tests; do not add counts.
The earlier **1,281 full backend tests** belong to the duplicate-policy checkpoint,
not a fresh full run of the current tree. See [validation](PHASE4_VALIDATION.md).

Still open:

- [ ] Approve [evidence-qualified dashboard contract](DASHBOARD_EVIDENCE_SCORING_DESIGN.md),
  reviewer authority and organization-wide scope, then implement qualifications
  and partial-domain/overall scoring. Asset-only domains can still baseline at 100.
- [x] Review exact commit scope/secrets and check in completed work in scoped groups.
  Backend duplicate policy: `d26f525`; empty dashboard API: `e2288a6`; shared
  frontend: `b223613`; acceptance/documentation accompany this closure record.
- [ ] Push the reviewed commits after approval and verify hosted CI; no push
  performed by this check-in. Local credentials/original branding files excluded.
- [ ] Existing broader Phase 4 exclusions, live-provider approval, production
  operations and Future items remain unchanged. No whole-phase closure implied.

The sections below are **historical checkpoints**. Their counts and statements
about pending activation describe those checkpoints, not the current running demo.

## Historical increment — file-drop navigation fix, 27 October 2026

Assets/Findings accept multi-file drops across page content, and signed-in pages
guard against Chrome's file-open default. Native file inputs/text drags remain
intact; unrelated modals/busy queues ignore file intake. Fresh **428 frontend
tests**, **68 Chrome executions**, lint and isolated build passed. Backend is
unchanged from the earlier full 1,281-test policy run. See latest validation for
idle-job check, activation and health results; no paid/inference calls. The fix
is now active locally after a successful idle-queue rebuild/restart; API, worker
and frontend health checks passed, with data/accounts/settings preserved.

## Latest increment — exact duplicate file policy, 27 October 2026

Ask/Skip/Reimport now persists in organization Ingestion settings (server default
Ask). Backend admission is serialized per organization/hash; queued/running
identical imports always skip. Skip is audited without a job/report; Reimport
does not promise record updates. All shared import formats/sources use it.
Documents/logo single-item flows remain separate. No migration is required.
Fresh 1,281 full PostgreSQL tests and 425 frontend tests, lint and isolated build
passed; test database restored to 0028 with no drift. **67 Chrome executions**
passed, including Settings changes, real Skip/Reimport, Activity and reset to Ask.
Local activation completed on 27 October after the user approved a restart and
the demo queue had no pending/running imports. API, worker and frontend restarted
after a successful normal production build; readiness and login HTTP 200 passed.
Live OpenAPI exposes Ask/Skip/Reimport. Existing data, passwords and organization
settings were preserved; no paid/inference calls or commit/push.

## Latest local increment — grouped upload decisions, 27 October 2026

Implemented across every shared Assets/Findings import format/source: ready-first
submission, grouped explicit duplicate skip/reimport, separate failure/source
attention groups, failure-only retry and accepted-file exclusion. Documents/logo
single-item version/replacement rules are unchanged. See latest validation for
fresh test evidence; preceding checkpoints retain their original counts. The
demo/worker have not been restarted and these changes remain uncommitted.
Fresh validation: **422 frontend tests**, **64 Chrome executions**, lint and isolated production build/
TypeScript passed; focused results overlap the full frontend suite. Browser
artifacts/results are in the latest validation record, not the older counts below.

## Latest presentation follow-up — not yet activated in demo

Shared upload dialog, fixed-height header buttons, compact Detected badges and
grouped expandable progress/reports are implemented. Fresh 420 frontend tests, 63 Chrome executions,
lint and isolated production build passed. See latest validation for Chrome.
The running demo and worker remain untouched to protect current imports; a later
controlled restart is needed to expose the new UI. No commit/push or inference.

## Latest local increment — shared batch upload

Assets/Findings now share one-click sequential multi-file submission with
per-file source/report preservation, locked source/queue edits, stop/retry and
explicit duplicate confirmation. Individual uploads remain available outside
batch submission. Fresh 417 frontend tests, 61 Chrome executions, lint and builds passed; demo rebuilt
and healthy. See [latest validation](PHASE4_VALIDATION.md) for Chrome acceptance.
Backend/full-suite counts in the earlier handoff below are historical. This
increment is local-only and uncommitted; broader Phase 4 exclusions are unchanged.

## Current handoff — 26 October 2026

Organization logo management and header name/size preferences, platform-admin
product-logo sizing, active approved SVG assets, single-brand authentication
presentation and shared Show/Hide password controls are implemented locally.
Migrations 0025–0028 cover organization branding; platform presentation uses the
existing platform_settings table. Final combined-tree review passed: **1,268 full
PostgreSQL tests**, **413 frontend tests**, **61 Chrome executions**, lint/build,
migration checks and dependency/static gates. Scoped commits, push and hosted CI
verification are approved. Four scoped commits were pushed through **b91ade6**;
hosted acceptance is tracked by [per-SHA run and latest-tip links](PHASE4_VALIDATION.md),
not by historical local-only notes below. The subsequent handoff update is docs-only.

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
