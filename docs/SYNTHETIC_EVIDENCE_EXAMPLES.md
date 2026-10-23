# Persistent synthetic evidence examples

Validated 23 October 2026. Local testing only; not a production or live-AI release.

At http://localhost:3000, use your existing organization-admin account, select
**Evidence examples - SYNTHETIC ONLY**, then **Reports**. Four saved reports show
sufficient, limited, insufficient and conflicting evidence across all seven domains.
The sufficient fixture has a simulated 70/100 score. All other fixtures have null
scores and tiers. Complete/Partial filters return one/three reports respectively.

These fixed snapshots intentionally bypass provider generation and qualification;
they demonstrate presentation, not evidence acceptance or model quality. Their
provenance explicitly records simulation and no operational approval. No findings,
assets, real standard text, remediation recommendations or model confidence values
are invented as actual organizational records. No consent or provider configuration
is changed, and demo startup explicitly disables real inference and new-mode generation.

The separate organization preserves the original demo organization and passwords.
Run `scripts/demo.py seed-evidence-examples` with the backend virtual environment
to create missing examples; existing snapshots and edits are not overwritten.
The CLI accepts local demo targets only; the seed helper also accepts the exact
`auditmind_test` database for integration tests. Neither performs migrations.

## Verification evidence

- 14 demo/example tests passed, including PostgreSQL persistence/idempotency,
  schema validation, unsafe-target refusal, HTML/PDF rendering and default-off guards.
- 112 focused report/evidence regression tests passed against PostgreSQL.
  These results are focused runs, not a new full backend-suite result.
- 313 frontend tests passed; lint and production build (including TypeScript) passed.
- 14 installed Chrome 155 checks passed: four report views, eight downloads and
  two completeness filters; no browser page errors. Screenshot visually reviewed.
- PostgreSQL test database restored to Alembic 0021: 29 public tables, no remaining
  isolated browser schemas; downgrade/upgrade round trip and drift check passed.

Chrome artifacts: `temp/auditmind-demo/evidence-examples/` (four screenshots,
four HTML files, four PDFs and `results.json`). These are local ignored artifacts.
PDF checks verify rendering/download/file signature, not a separate PDF visual audit.

The initial password recorded in the ignored sign-in file was rejected. It was not
reset. Chrome verification therefore used a temporary server-created local demo
session, removed immediately afterward. This does not claim password-login acceptance.
Normal users continue using their current password/session. No inference or paid calls
were made. This is a local-testing milestone, not production or live-AI acceptance.
