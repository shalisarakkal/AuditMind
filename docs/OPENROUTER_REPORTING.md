# Claude reporting through OpenRouter

Remediation follow-up (2026-10-22): live report ownership/status/cancellation is
refreshed before every application-level provider attempt and quota reservation,
for either transport. Adapter/mock tests are not live-provider acceptance. Real
inference remains disabled unless separately approved; the free-model probe did
not yield a completion. Issued requests cannot be aborted by cancellation.
See [current code review and release gates](RELEASE_READINESS.md).

Status: implemented for **mock-only testing**, not enabled or live-accepted.
No paid calls, real model inference, new database or application migration were
performed for this integration. Existing direct Anthropic behavior remains the
default; local report generation remains unaccepted and separate.

## Explicit processing route

`REPORT_AI_PROVIDER` selects `anthropic` or `openrouter` on the server. It is not a
user-supplied URL or per-request arbitrary model. The OpenRouter transport uses a
fixed HTTPS endpoint, disables redirects and environment proxies, bounds request
time, and delegates retries to the existing application retry budget. There is no
automatic fallback to direct Anthropic, another model, or another downstream
provider. Only the `Anthropic` provider is allowed, with fallbacks disabled,
parameter support required, data collection denied and ZDR required. Unsupported
model/provider/privacy combinations must fail rather than relax these rules.

No account-specific model availability or privacy-policy eligibility was verified
through live inference. Strict checks require the response to identify the selected
model and Anthropic provider; live compatibility still requires later approval.
Reference: [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

## Disabled until separately approved

Defaults:

```dotenv
REPORT_AI_PROVIDER=anthropic
OPENROUTER_INFERENCE_ENABLED=false
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
```

Selecting OpenRouter or supplying a key alone does not enable inference. A future
operator-approved rollout also requires an explicit `anthropic/claude-...` model
ID and positive finite `OPENROUTER_INPUT_USD_PER_MILLION` and
`OPENROUTER_OUTPUT_USD_PER_MILLION` price ceilings. Do not paste secrets into chat,
commit them, or expose them to the frontend. **Do not turn on the enable switch as
part of the current no-paid-call testing.**

The demo launcher unconditionally clears the OpenRouter key and disables its
inference switch, just as it clears other external provider keys. No active demo
settings, consent, user passwords or data were changed. The existing
`/ai/claude/test` endpoint remains direct-Anthropic-only; it does not provide an
alternate OpenRouter path around report consent.

## Consent and queued-job safety

Documents > Data processing consent displays a target starting `openrouter:` and
identifying the model, prompt version, Anthropic-only/ZDR policy and policy hash.
Direct-Anthropic consent does not authorize OpenRouter. The hash also covers price
ceilings; changing the route/model/policy requires renewed approval.

New report jobs pin that target in existing JSON storage, and idempotency hashes
include it. Reusing an idempotency key with a different target conflicts rather
than returning or admitting a differently routed request.
Existing keys admitted before this route-aware fingerprint was introduced may
conflict; use a fresh key rather than silently reinterpret historical intent.
Workers check the target before capture/generation and publication; the generation pipeline checks again
before each attempt and after generation. Current org activity and report consent
remain independently enforced. Legacy unpinned jobs cannot run via OpenRouter.
Legacy unpinned direct-Anthropic jobs retain their prior behavior; deployments
should drain/review them before changing configuration.

Pending/running report data can contain an internal `_processing_target` marker;
it is not a completed assessment and the report-detail API hides that internal
job metadata. Failed generation clears this internal marker;
new completed snapshots retain provider/model/route/target provenance. Existing
saved reports are not rewritten. No schema migration is introduced; the existing
`0021` accounting/idempotency migration remains a prerequisite.

## Transport validation and costs

Only one nonempty text completion with `finish_reason=stop`, the selected model,
Anthropic provider, valid nonnegative integer token counts and a finite nonnegative
reported `usage.cost` is accepted. Redirects, partial output, missing usage/cost,
provider/model mismatches and malformed/error envelopes fail closed. Report JSON
then passes the existing production Pydantic schema and captured-citation,
finding and linked-asset validators. The adapter never repairs report output.

The shared durable ledger reserves before network I/O, using configured input /
output price ceilings and the existing minimum reservation. The request includes
matching provider `max_price` bounds. On a valid transport response, the ledger
uses **OpenRouter-reported USD cost**, not the legacy direct-Anthropic estimator;
the ledger model identity is prefixed `openrouter:`. This is provider-reported
usage, not independent invoice reconciliation. A later report-validation failure
still consumed the upstream completion and remains accounted for.

Timeouts, temporary HTTP failures and rate limits use bounded application retries;
authentication/credit errors and invalid output are not retried. Authorization or
target changes stop further attempts before admission. Unknown outcomes retain
their reservation, so a timeout/restart cannot erase potential spend. Missing
provider usage/cost is rejected and retains the reservation. Actual cost may only
be known after the request; app quotas do not replace account-level credit caps.

References: [request/response API](https://openrouter.ai/docs/api/reference/overview)
and [provider privacy controls](https://openrouter.ai/docs/guides/privacy/provider-logging).

## Verification and remaining gates

Unit tests use HTTPX mock transports with real network transports forbidden.
Integration tests exercise the real API, consent, queue, worker, schema/reference
validation, ledger persistence and HTML/PDF export against `auditmind_test`, with
only the external HTTP boundary mocked. Test-only monkeypatches enable the route;
no real environment configuration is enabled.

Coverage includes disabled/missing/invalid configuration, route and policy target
changes, direct-consent rejection, cross-org authorization, idempotency, revoked
consent, queue/publication changes, missing/malformed usage, provider/model
mismatch, redirects, truncation, empty/multiple choices, timeout/connection errors,
bounded retries, invalid schema and invented evidence references. Existing report
and cancellation regressions remain applicable.

Still outstanding: account/model metadata readiness, verified price ceilings and
privacy-compatible endpoint availability, a separately budget-approved real SA01
call, model-output quality evaluation, and live Chrome report acceptance. Mocked
PDF/HTML success is not proof of real Claude quality or release sign-off. No live
provider inference or browser interaction was performed for this implementation.

### Recorded verification (2026-10-21)

- Complete backend suite: **965 passed**, `pytest -q -W error`, 524.07 seconds.
- Following final review hardening and additional malformed-envelope/cancellation
  tests: **93 focused tests passed**, `-W error`, 27.27 seconds. This includes
  OpenRouter/Claude units and OpenRouter, reference, operations and worker
  integration regressions. The earlier full-suite count does not include tests
  added during final review; it is not represented as a fresh full-suite run of
  every final addition.
- Frontend: **274 tests passed**; lint and TypeScript no-emit checks passed.
  Existing non-failing React `act(...)` diagnostics remain. No frontend source was
  changed, production build was not rerun, and the running demo build was not
  replaced.
- Syntax compilation and `git diff --check` passed. Git reports existing
  line-ending normalization notices in other dirty files; no unrelated rewrite
  was performed.
- After DB tests, only `auditmind_test.public` was restored through migration
  `0021`; Alembic metadata check found no new operations, repeated upgrade was
  clean. There are 28 application tables plus `alembic_version`. No ordinary/demo
  migrations or data changes occurred.
- Effective regular settings still select `anthropic`; OpenRouter inference is
  **false**. Presence of a configured OpenRouter key does not enable calls. No
  credentials were displayed or changed, and no live generation was performed.

Final focused command, from `backend`:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_openrouter.py tests/unit/test_claude_service.py tests/unit/test_report_ai.py tests/integration/test_openrouter_reports.py tests/integration/test_assessment_references.py tests/integration/test_report_operations.py tests/integration/test_worker_reports.py -q -W error
```
