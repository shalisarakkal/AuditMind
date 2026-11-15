# Guarded scanner-field publication actions

Local implementation checkpoint (2026-11-15). Normal application database activation remains separate. This increment adds no migration; it requires the retained publication storage, integrated consumer revisions and all seven lifecycle guards from migrations 0056 through 0058.

## Availability and authorization

Settings > Scanner-field publication is a separate organization option, Off by default. Organization admins may change it with an expected setting version. Members may inspect availability; platform status alone does not authorize an organization write. Missing storage, receipt admission columns, lifecycle functions or enabled source triggers fail closed.

Off blocks new Publish operations. Authorized Undo and exact receipt replay remain possible. Legacy private transaction entry points stay closed. The earlier read-only scanner-field preview never authorizes a write.

## Finding workflow

For a single finding, expand Source observations, then Preview scanner-field differences. Review publication opens a separate fixed-target review with a fresh server token and generation. Unsaved workflow edits must first be saved or cleared. Review the before/after values, provide a rationale and acknowledge the consequences before Publish scanner fields is enabled.

Expand Publication history to review Undo for an active integrated publication. Undo requires retained, unchanged snapshots and valid current source context; it restores the exact before-snapshot. It does not recreate purged data or restore an earlier scoring approval. Approved scoring proof must be explicitly revoked before either operation, including expired approved proof.

Only the reviewed severity, description, details, raw data and observed first/last times may change. Finding identity, original import/asset ownership, domain, category and current workflow are preserved. Consumer invalidation, source updates, receipt, activity and generation changes commit atomically. Lists/counts, Dashboard and scoring become current through their existing invalidation paths; saved reports remain unchanged.

## Conflicts and uncertain outcomes

Stale source, policy, workflow or generation rejects the operation and requires another preview. A network/server failure may have happened after commit. Retry same request preserves the exact request ID, token, generation and rationale. A denied retry does not prove the first attempt failed. Close and refresh inspects current history; closing never cancels a committed operation. During submission, dismissal is blocked.

Missing, purged, altered or unsupported source context is blocked; administrators must review retained history and recovery instructions rather than reconstructing source payloads.

## HTTP surface

Under `/orgs/{org}/observation-publication`:

- `GET/PATCH /settings` reads availability or changes the versioned organization policy.
- `POST /findings/{finding}/observations/{observation}/preview` prepares a fresh Publish review.
- `POST /findings/{finding}/observations/{observation}/publish` commits the confirmed review.
- `POST /findings/{finding}/undo-preview` prepares Undo.
- `POST /findings/{finding}/undo` commits confirmed Undo.

Write bodies forbid replacement scanner data and extra fields. Apply requests require request ID, expected generation, review token, rationale and explicit boolean confirmation.

## Verification

Post-fix isolated backend checks: **94 passed** (public actions, retained read surface, private transaction regressions and closed-entry-point gates). Additional consumer/storage/consolidation regressions: **117 passed**, including indexed dependency probes, large retained histories and unrelated asset purge checks. These targeted checks are not a new SaaS capacity benchmark.

Frontend: **602 tests passed**; TypeScript, ESLint and the isolated production build passed. Full real-Chrome acceptance: **108 checks passed**, including guarded native Publish, policy-off Undo, unchanged workflow/ownership, mobile widths and Axe; no AI calls or browser page errors. An earlier six-check focused Chrome run and seven focused UI safety checks also passed.

Evidence logs (ignored local artifacts): `temp/stageb-actions-final.log`, `temp/stageb-actions-regression.log`, `temp/stageb-actions-frontend-closeout.log` and `temp/stageb-actions-browser-full.log`. Chrome artifacts: `temp/testing/finding-workflow/phase3_browser_58aefef37cd0`.

No commit/push, hosted CI or normal database activation is claimed for this increment.

Review reproduction: removing the retained dependency table incorrectly left availability enabled. The new regression failed before the fix (`temp/stageb-actions-readiness-repro.log`); readiness now requires that table too. The post-fix 94-check run includes the formerly failing case and passes.
