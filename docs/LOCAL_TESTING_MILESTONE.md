# Local-testing milestone — approved and closed

**Decision date: 23 October 2026 (America/New_York).** The user explicitly approved
the scoped development-tool risk exception and closure of the local-testing
milestone. This records that decision, not a production/live-AI release.

## Approved scope

Controlled local synthetic testing, native browser workflows, PostgreSQL-backed
regressions and mocked-provider reporting. Live inference remains disabled in the
demo; no paid calls, production deployment, public hosting or provider enablement
are authorized. Existing application safeguards and organization consent remain.

Acceptance relies on recorded evidence, not tests newly rerun for this decision:
307 frontend tests, 71 focused backend tests, 17 native Chrome checks and
lint/TypeScript/build passed. The earlier full backend checkpoint is 1,035 tests;
focused results do not replace it or establish new overall coverage. See
[testing](TESTING.md) and [browser acceptance](PHASE3_ACCEPTANCE.md).

## Scoped risk exception: braces

- Advisory: GHSA-vfj7-8cjw-p6xm, development dependency braces3.0.3; last recorded
  audit showed seven propagated development entries, zero production entries.
  This decision does not assert a fresh audit or that the vulnerability is fixed.
- Risk: crafted deeply nested patterns can crash the Node process processing them.
  Existing review found no ordinary application-input path to that tooling.
- Accepted only for trusted local development/test configuration and repositories.
  Do not expose development servers publicly or process untrusted repositories/
  glob configuration. Untrusted contributions need isolated CI without secrets.
- Keep the advisory visible; no global suppression or forced dependency replacement.
- Decision owner: the approving project owner/user. Implementation follow-up:
  project maintainers. No external security approval is implied.
- **Review due: 22 November 2026 (30 days), or earlier** on upstream fix, tooling
  migration, new exploitability evidence, public exposure or production planning.
  Exception expires at that review date unless explicitly renewed. Broader exposure
  requires a new decision; this is not a permanent or production risk acceptance.
- Permanent remediation: supported upstream update or reviewed tooling migration,
  with dependency audits, regression tests, lint/TypeScript and production build.

## Open/separate work

- Production/live-AI release sign-off: **not granted**.
- Real provider/model access, pricing, context capacity and actual report quality:
  **not accepted**, requires separate approval and evaluation.
- Insufficient-evidence scoring: separate schema/design task, not implemented or
  implicitly authorized here.
- Docker deployment and report-date UI: remain **Future** as user directed.
- Existing coverage/load/soak limitations remain documented, not waived globally.

This decision does not authorize pushing commits, changing credentials, granting
external data-processing consent, or running inference.
