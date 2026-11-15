# Frontend dependency remediation - 15 November 2026

Local implementation and compatibility verification are complete. Exact-commit hosted CI is the post-push delivery gate for this increment; the earlier successful `15ad820` CI applies to the preceding application delivery only. Consult this increment's Actions run for its delivery result.

## Finding and reproduced failure

`npm audit --json` reproduced seven moderate development-chain findings, with zero production findings. They share the `minimatch` glob-pattern amplification advisory [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249). The advisory identifies `11.0.1` as patched; the [upstream fix](https://github.com/isaacs/minimatch/commit/77a0f5c) caps preprocessing expansion.

The installed TypeScript ESLint parser chain resolved `minimatch@10.2.6`. A bounded eight-segment reproduction at optimization level 2 generated 256 patterns despite a limit of 64. The security regression failed before the fix (`temp/dependency-cleanup-repro.log`) and passes afterward. The small reproduction avoids the unbounded input from the original report.

## Compatibility-tested change

- Scope the override to `@typescript-eslint/typescript-estree > minimatch`, pinned to `11.0.1`. Keep unrelated `minimatch@3.1.5` consumers unchanged.
- Preserve existing ESLint, TypeScript ESLint, Next.js, React and application versions. Do not apply the audit tool's forced TypeScript ESLint downgrade.
- Update the lockfile: one development dependency changes and one development-only helper is added. Production dependencies are unchanged.
- Add `npm run test:dependency-security` to the frontend CI job. It resolves the parser's actual transitive package, checks ordinary glob behavior, tests the amplification cap and exercises TypeScript ESLint's real project service with a dotfile/default-project glob.

This is a deliberate transitive major-version override, not an upstream parent dependency-range update. Keep the guard and review/remove the override when the parent dependency adopts a patched compatible version. Node 22 is configured in hosted CI; local compatibility checks ran on Node 24.20.0. Hosted Linux verification must be checked against this increment's pushed commit.

## Completed local verification

- Full audit: **zero vulnerabilities**, down from seven moderate findings; production-only audit also reports zero.
- Final security regression and actual project-service integration pass in the workspace and a separately created clean-install directory.
- Fresh `npm ci` completes successfully and its audit reports zero vulnerabilities. The final ESM guard passes against that clean installation.
- All **602 frontend tests** pass; TypeScript and ESLint pass.
- The isolated Next.js production build passes. It uses `.next-acceptance` and preserves the running application's normal chunks; generated type references are restored afterward.
- Lockfile review confirms only the scoped development-chain changes. No application UI, database migration, publication policy or running-service restart is part of this increment.

Ignored local evidence: `temp/dependency-cleanup-audit-before.json`, `temp/dependency-cleanup-audit-after.json`, `temp/dependency-cleanup-production-audit.json`, `temp/dependency-cleanup-repro.log`, `temp/dependency-cleanup-unit.log`, `temp/dependency-cleanup-lint-closeout.log`, `temp/dependency-cleanup-types-final.log`, `temp/dependency-cleanup-build.log`, and `temp/dependency-cleanup-clean-install-final.log`.

Backend and Chrome suites were not rerun for this development-tool-only change; the existing application acceptance remains separate from this increment's lint/build/parser checks. No SaaS capacity or production rollout claim is added.
