# Backend dependency remediation — 26 October 2026

Separate user-approved compatibility increment, following the Phase 4 local
operations features. No new provider inference, consent, deployment or migration.
This document supersedes the earlier audit-blocker status only to the extent
verified by the final audit/test results below; hosted CI is separate.

## Changes and rationale

| Area | Previous | Selected pins |
|---|---|---|
| Web framework | FastAPI 0.115.6 / Starlette 0.41.3 | FastAPI 0.162.0 / Starlette 1.10.0 |
| JWT | python-jose 3.5.0, ecdsa 0.19.2 | PyJWT[crypto] 2.15.1; obsolete packages removed from the local environment |
| Async / multipart | AnyIO 4.14.1 / python-multipart 0.0.20 | 4.14.2 / 0.0.32 |
| Test / packaging tools | pytest 8.3.4, pip 24.2, setuptools 84.0.0 | 9.0.3 / 26.2.2 / 84.1.0 |
| CA bundle / image parser | certifi 2026.7.22 / Pillow 12.3.0 installed | 2026.10.19 / 13.0.0 explicitly pinned |
| Optional embeddings | sentence-transformers 3.4.1 / transformers 4.57.6 | 5.6.0 / 5.20.2; filelock 4.2.1 |
| Optional OpenAI client | manifest 1.68.2, installed 3.28.0 | Pin 3.28.0, preserving the existing installed SDK and satisfying an unrelated installed Azure SDK constraint |

The initial core/dev manifest audit reported 34 advisory entries in six packages
(including duplicates). An installed-environment audit separately reported 64
entries in seven optional/tooling/transitive packages. These are different scopes,
not additive unique vulnerability counts. No ignores or exception expansion.

Transformers 5.10.0 was rejected after pip reported it yanked; the final pin is
the non-yanked 5.20.2. Model ID/revision and embedding profile settings are not
changed; no re-indexing or model download is authorized by this upgrade. Mocked
adapter/offline tests and package import checks are not vector-quality certification
of the upgraded optional runtime against an existing production index.

## Compatibility boundary

The application uses JWT encode/decode only, not JWE. PyJWT preserves HS256
signature/claim format. Existing independently generated legacy tokens, expiry,
session ID, wrong-key, unsigned and wrong-algorithm regressions remain. Configured
algorithm allowlists stay explicit; they are never inferred from token headers.
Invalid non-string session claims now return unauthorized rather than raising a
UUID-conversion server error. Password hashing, session rows and signing keys are
unchanged; no password reset/key rotation is performed.

Modern Starlette deprecates old 413/422 symbolic names; code now uses the modern
names with the same numeric HTTP statuses. Deprecations remain errors in tests,
not ignored. No third-party package source was patched.

## Verification record

Hosted follow-up: the first run at `9720777` passed frontend and dependency/security
jobs, but backend collection failed because the clean dev installation lacked
`httpx2`. Locally it had been supplied indirectly by the optional OpenAI SDK.
The browser fixture separately failed because its fresh database did not enable
`vector`. These failures invalidate any claim of hosted acceptance, not the
historical local results below. The correction explicitly pins `httpx2==2.13.1`
in dev requirements, adds dependency/import smoke checks, enables browser database
extensions and targets the correct database in PostgreSQL health checks. Test
network guards now cover both HTTP client stacks. Final rerun evidence is recorded
separately after completion; no warning suppression or live inference is used.

Initial compatibility rerun after status-alias fixes: **73 passed** (77.65s).
JWT unit regressions including malformed session claims: **14 passed** (0.99s).
Final full PostgreSQL regression: **1,238 passed in 628.60s**, using
`--require-postgres -W error`. This includes the focused checks above and all
new secret-guard/JWT cases; counts are not additive.

Fresh frontend validation: **376 passed** (29.03s), lint, isolated production
build, normal route type generation and TypeScript check passed. Installed Chrome:
**39 workflow checks** passed (`phase3_browser_df711584fa08` under
`temp/testing/finding-workflow`). Documents acceptance separately passed **6
grouped checks** (`temp/auditmind-demo/browser/documents-ui.json`, intercepted
fixtures); these are different scopes, not 45 equivalent browser checks.

Final dependency resolution: `pip check` reports no conflicts; pip-audit reports
**no known vulnerabilities** for each of the core/dev manifest, optional embeddings
manifest and the actual installed environment. Offline imports of
sentence-transformers 5.6.0 / Transformers 5.20.2 passed without model loading or
downloads. High-severity Bandit and tracked-file secret guard passed. The demo
was restarted with existing data/passwords and live `/ready` reports all checks
true. Optional constructor/encode signature checks also passed without model
instantiation. The disposable PostgreSQL test database was restored to revision
0024: upgrade/downgrade/upgrade and drift checks passed, with 30 public tables and
no leftover browser schemas. Hosted CI and real embedding/model quality remain
unverified; these results close local compatibility testing only.

Primary references checked for selection/implementation:
[PyJWT decode API and algorithm warning](https://pyjwt.readthedocs.io/en/stable/api.html),
[FastAPI release notes](https://fastapi.tiangolo.com/release-notes/), and PyPI
release metadata for [FastAPI](https://pypi.org/project/fastapi/0.162.0/),
[Starlette](https://pypi.org/project/starlette/1.10.0/),
[Transformers](https://pypi.org/project/transformers/5.20.2/).
