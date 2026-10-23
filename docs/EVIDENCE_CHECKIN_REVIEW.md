# Evidence-aware reporting: check-in preparation

Follow-up approval: the user subsequently authorized proceeding with four grouped
local commits. The preparation record below is historical; it does not authorize
a push, rollout, inference or production release. Existing test checkpoints retain
their stated scope; no new tests are implied by creating the commits.

23 October 2026. User requested preparation and verification instructions, not a
commit or push. The intended staged scope is the evidence-aware implementation,
associated tests/browser fixtures and documentation. `cline.json`, credentials,
temporary evaluation results, build caches and uploads are excluded.

## Proposed reviewable commit groups

1. **Backend contract and qualification:** new schemas/policy service, opt-in
   settings/example, version/target identity, generation and export validation,
   list projection/filter, unit and PostgreSQL regression tests.
2. **Frontend states and navigation:** nullable score/status types, report cards,
   completeness filter, evidence explanations, legacy/future handling and tests.
3. **Browser verification:** synthetic fixture and new-mode completeness assertions.
4. **Documentation:** approved design, profiles, rollout boundary, data model,
   roadmap/status/test records and user verification guide.

All paths staged explicitly, without `git add .`. These groups are review/commit
boundaries; Git still has one shared staging index. Commit each group by its
explicit paths when authorized; do not accidentally commit the entire index as
one group. No automatic commit/push is authorized by this preparation record.

## Review findings and evidence

- Fixed a prompt-construction bug found during this review: a source/title marker
  could become the first delimiter and truncate evidence. Use the final fixed
  delimiter instead; preserve source/title text and selection metadata in a new
  regression. No source record or model result is rewritten.
- **130 focused tests passed after the fix**, PostgreSQL required, warnings as
  errors. Last full checkpoint **1,115** precedes this narrow fix; collection now
  includes one additional test. Do not claim a1,116-test full run or combine counts.
- Existing final frontend checkpoint: **312 tests**, lint/TypeScript/build passed.
  Backend-only marker fix does not change the frontend build.
- After the marker fix, **18/18 new-mode Chrome checks passed**, zero page errors
  and schema cleanup verified. Latest evidence folder: `phase3_browser_50059684831c`
  under `temp/auditmind-demo/browser/phase3/`.
- Exact staged blobs receive a redacted heuristic credential/artifact scan plus
  manual candidate review. This is not a comprehensive secret-detection guarantee.
  All six candidates were unchanged existing example/default or synthetic fixture
  values; no new live credential identified. Staged whitespace and relative-link
  checks passed. **38 files** explicitly staged; no unrelated staged changes.
- Real test schema restored after focused tests; upgrade/downgrade/upgrade and
  Alembic drift/no-op checks pass,29 public tables, zero browser schemas remain.
- New mode stays off by default. Trusted operator qualifications are a controlled
  single-organization pilot; no qualification file configured or ordinary consent
  changed. No inference, paid calls or production/live-AI approval.

## How the user verifies

Follow [the exact UI/PowerShell checklist](EVIDENCE_USER_VERIFICATION.md).
The normal demo proves compatibility, not new-mode generation. Saved PNG/HTML/PDF
and the isolated mocked Chrome runner prove the partial workflow. Unit/component
and PostgreSQL tests cover other evidence states, reviewed scoring and failure
cases. The temporary fixture is cleaned; it does not create persistent sign-ins or
sample reports in the ordinary demo. Do not enable external inference to inspect it.
