# Dependency audit — 26 October 2026

Latest user-approved remediation: core/dev requirements, optional embeddings
requirements and installed-environment audits now report **no known
vulnerabilities**, and `pip check` reports no conflicts. PyJWT replaces
python-jose/ecdsa; the framework/async/multipart/tooling and optional model runtime
pins were compatibility-upgraded. No advisory ignore or risk waiver added.
See [precise versions and test evidence](BACKEND_DEPENDENCY_REMEDIATION.md).
The failing backend audit described below is historical, not the current scan.
Final compatibility acceptance: 1,238 full PostgreSQL tests (warnings as errors),
376 frontend tests, lint/build/TypeScript and 39 Chrome workflow checks passed;
six Documents grouped checks are separate. Hosted CI remains unverified.

Historical intermediate backend audit (subsequently resolved above): a
`pip-audit -r requirements-dev.txt`
reported **34 advisory entries across six packages**, including duplicates and
two packages with no listed fixed version. See
[local operations / exact audit scope](PHASE4_LOCAL_OPERATIONS.md). No new risk
exception or dependency upgrade was made. The resolved frontend finding below
must not be read as an all-backend/all-dependency clearance. Fresh npm audit: zero.

**Resolved after explicit user approval on 26 October.** Targeted updates changed
only `frontend/package-lock.json`: `undici` **8.11.2 → 8.12.3**, `zod` **4.6.5 →
4.6.7**, and their resolved URLs/integrity values (6 added/6 removed lines).
`package.json`, direct dependencies and all other package versions are unchanged.
Both full and production-only npm audits now report **zero vulnerabilities**.

Initial pre-update frontend audits: `npm audit --omit=dev --json` reported **zero**
vulnerabilities; full `npm audit --json` reported **two high vulnerable-package
entries**, zero critical. Four underlying advisory records are aggregated into
those two packages. These are transitive development dependencies, not proven
application exploits or production dependencies.

- `undici@8.11.2`, through `jsdom@30.1.1`: affected range 8.0.0–8.12.1, patched
  threshold 8.12.2; npm reports a fix available. Advisory reports:
  [EventSource resource exhaustion](https://github.com/advisories/GHSA-4qv8-2p9j-2685),
  [integrity-token validation](https://github.com/advisories/GHSA-f72v-6w45-q472),
  [content-encoding error handling](https://github.com/advisories/GHSA-xjj6-f33q-929c).
- `zod@4.6.5`, through `eslint-config-next@16.4.2` →
  `eslint-plugin-react-hooks@7.1.1` (also `zod-validation-error`): affected below
  4.6.6; npm reports a fix available. Advisory report:
  [constrained-collection resource exhaustion](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5).

The previous [local milestone exception](LOCAL_TESTING_MILESTONE.md) covered
**braces**, not these findings. It has not been expanded. A production-only npm
audit does not certify all code, deployment settings or non-npm dependencies.
The two transitive lockfile updates above fix these findings; no new risk
exception was accepted. The later user-authorized frontend commit is **c995e5e**;
no push was performed.

## Post-update validation

Fresh 26 October results: **367 frontend tests** passed in 51.92s; lint and
TypeScript/isolated production build passed; full and production-only audits zero.
**35 installed Chrome workflow checks** passed against the fresh isolated build
(`phase3_browser_f712c790a5e4`), plus **6 grouped Documents checks** on the unchanged
demo UI using intercepted fixtures (`temp/auditmind-demo/browser/documents-ui.json`).
These are separate browser scopes, not 41 equivalent checks. No real inference.

The dependency blocker is resolved for the scoped local-testing check-in. The
historical **1,203 full backend tests** remain 25 October evidence, not a new run
for this dependency-only change. Backend commit **86a1c2e** is separate; the lockfile
is included in frontend commit **c995e5e**. Acceptance/docs are committed separately.
Production/live-AI release and push approval remain separate.
