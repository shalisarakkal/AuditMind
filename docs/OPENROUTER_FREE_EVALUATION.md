# Free OpenRouter model probe — 2026-10-22

Review synchronization (2026-10-22): Historical/design record: original dates, results and proposals are preserved. This is not fresh test evidence or current release sign-off.
See [current code review and release gates](RELEASE_READINESS.md).

Status: **blocked at routing; no model-quality conclusion or application enablement**.
The user approved a synthetic-only evaluation of one fixed free model, not paid
fallbacks, relaxed privacy rules or changes to the report integration.

## Selection and frozen probe

Public catalog and endpoint metadata were inspected without inference. The
Nemotron 3 Super 120B free candidate advertised structured output but its endpoint
reported status -5 and zero recent uptime; it was not used for inference.
The chosen probe was `google/gemma-4-31b-it:free`, pinned to Google AI Studio
(`google-ai-studio`). Its endpoint reported status 0, zero prompt/completion
pricing and response-format support. It was also present in the account-filtered
model listing. None of these metadata checks guarantees an eligible live endpoint.

`scripts/evaluate_openrouter_free.py` is separate from the production Claude-only
adapter. It imports no application modules and accesses no database. The script
reads only the saved backend `.env` key, never prints it, and does not alter the
inherited environment, app credentials, consent or provider settings.

Ten existing synthetic holdout-v1 cases (now known regression fixtures) and the
existing evidence-v2 system prompt/reduced schema were frozen before inference.
One request per case was planned, maximum 700 output tokens, temperature zero,
non-streaming JSON-object output. No expected answer is sent. This is not the
production seven-domain report contract or a new unseen holdout.

Safeguards: exact free model and single provider, no fallback model, zero maximum
prompt/completion/request/image prices, no plugins/tools, no redirects/environment
proxies, 90-second timeout, no retries, denied data collection and required ZDR.
Published endpoint prices and health are checked before each request. Generated
responses must identify the pinned model/provider, complete without truncation,
report zero actual cost, and pass unchanged schema/reference/confidence checks.
Missing/nonzero cost or any request failure stops further inference, without repair.

## Result

- Authentication succeeded; key had $1 remaining spending allowance and 50/50
  free-model daily requests available before the attempt. These are caps, not
  account funds or a promise of endpoint availability.
- Account balance was **-$0.192819662** before and after the probe. No change in
  reported balance was observed; this is not independent billing reconciliation.
- **One** synthetic completion request was attempted and rejected with **HTTP 404**.
  No completion was returned; no other cases were sent, retried or routed elsewhere.
- The harness exited 1 and retained incomplete evidence. It did not enable or
  change the application's real inference route. No model downloads, migrations,
  source-data imports or application/database writes were performed.

The HTTP error body was intentionally not retained by this initial harness, only
status and a fixed safe diagnostic. Therefore the precise rejection cause is
**not established**. In particular, do not attribute 404 to the negative balance,
claim the model is universally unavailable, or assume that removing ZDR would fix
it. Account/provider/privacy preferences and zero-price routing constraints need
further diagnosis. The negative balance remains a separate documented risk:
[OpenRouter credit limits](https://openrouter.ai/docs/api/reference/limits) state
that it can block even free models.

Raw ignored evidence:
`temp/auditmind-demo/browser/free-evaluation/gemma4-free-1792687359542664000.json`.
It retains frozen fixtures/prompt/schema/policy, hash, endpoint metadata and the
rejected attempt's status/timing, without credentials or authorization headers.

## Tests and review

Four new harness self-tests passed: zero-price validation (including hidden request
fees, nonfinite/negative/boolean values), pinned request policy and answer isolation,
one-request stop on HTTP rejection with no authentication on public metadata, and
response cost/model/provider/truncation validation. Ten existing local evaluation
self-tests also passed; syntax compilation passed. Mock transports were used for
these tests. No application suite/build was rerun because only an isolated
evaluation script and documentation changed.

Review found that catalog presence and account-filtered model presence do not
establish compatibility with all per-request policy constraints. Keep the strict
policy and failure evidence; do not weaken it or silently select a paid route.
This blocked probe provides **no evidence of report-output quality**.

## Next action

Review OpenRouter account provider/privacy preferences and obtain a safe diagnostic
for the rejected route before another probe. If necessary, identify another fixed
free endpoint compatible with the same restrictions and seek approval for a
separately recorded trial. Do not change account billing or privacy automatically.
Only after a successful free-only probe should the remaining regression cases,
semantic review and a fresh holdout run. Production support would still require
explicit non-Claude provider consent, zero-price-compatible accounting and
full-schema/application integration tests; the existing adapter remains Claude-only.

Sources: [model endpoint metadata](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it:free/endpoints),
[provider routing and price bounds](https://openrouter.ai/docs/guides/routing/provider-selection).
