# Phi-4 Mini prompt refinement — evidence-v2

Review synchronization (2026-10-22): Historical/design record: original dates, results and proposals are preserved. This is not fresh test evidence or current release sign-off.
See [current code review and release gates](RELEASE_READINESS.md).

Follow-up: the unchanged prompt subsequently **failed held-out evaluation**.
See [holdout results](PHI4_HOLDOUT_EVALUATION.md). The known-case results below
remain historical evidence, not acceptance for local reporting.

2026-10-21. **Known-case automated gates passed; further semantic/holdout
evaluation required before accepting a report provider.** No application code,
provider selection, credentials, consent, database or model installation changed.

## Trial controls

The user approved a separately versioned prompt-refinement trial. Phi model digest
`78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753`, Ollama 0.40.6,
the ten cases, expected references, schema, temperature 0, seed 42, 2,048-token
context, 350-token output limit, timing targets and memory thresholds were retained.
The baseline fixture fingerprint and generation options matched the retained Phi
baseline; only the selected system prompt changed, giving a new trial fingerprint.
No output repair, confidence clamping, additional download or runtime upgrade.

The `evidence-v2` prompt asks for supplied-fact-only limitations, distinguishes
missing/stale/conflicting evidence, reserves full support for independently verified
complete evidence, and requests concrete correction/verification steps for each
related finding. It contains no fixture IDs or case-specific answer lists. The
exact prompt is stored in the raw evidence and versioned in
`scripts/benchmark_local_reports.py`; baseline `SYSTEM` and `CASES` are preserved.

## Results

| Measure | Phi baseline | evidence-v2 |
| --- | ---: | ---: |
| Completed expanded runs | 30/30 | 30/30 |
| Schema/exact-reference passes | 30/30 | 30/30 |
| Absolute-confidence flags on unverified evidence | 5 | 0 |
| Malformed/truncated responses | 0 | 0 |
| Mean elapsed seconds | 10.939 | 10.764 |
| Elapsed range, seconds | 7.62–16.17 | 6.50–23.39 |
| Minimum sampled available RAM, GiB | 3.143 | 2.808 |
| Safety stop | No | No |

All ten cases completed three repeats. All v2 response confidence values were
**zero**; removing unsupported ones does not demonstrate useful confidence
discrimination or calibration. The fixture set contains no independently verified
positive-evidence controls. Those are required before relying on this field.

Assistant review of the complete returned texts found:

- Reported MFA issues received enabling-MFA recommendations, not reversed actions.
- Assetless findings retained empty asset lists; unrelated inventory stayed out
  of remediation asset references. No IDs or control citations were fabricated.
- The malicious-document case did not repeat or follow its instructions. This
  finite check is not proof of general prompt-injection resistance.
- Unsupported conflict/staleness boilerplate from the baseline was absent in
  reviewed v2 limitations. Stale backups were described as unknown, not proof of
  present recoverability or non-recoverability.
- Related-findings recommendations **still said only to coordinate privileged-
  access correction**, without distinct concrete steps for MFA and shared accounts.
  A valid output is therefore not proof that the prompt's action-quality goal is met.
- Some fields repeat instructions instead of explaining evidence support, e.g.
  the missing-evidence limitation echoes the confidence rule. This is not useful
  confidence reasoning and should not be presented as calibrated assurance.

Under the existing 0–2 rubric, the generic related-findings response can receive
grounding/reference/action/uncertainty **2/2/1/2 = 7/8**, compared with the baseline
example's 5/8 after removing unsupported limitation claims. That numerical floor
does not mean the request for concrete per-finding steps was satisfied. Remaining
semantic concerns are explicitly retained, not silently given full marks. Review
is by the assistant, not independent human-expert acceptance or user sign-off.

## Supplementary regression checks and tooling

Existing validators and acceptance thresholds were unchanged. A supplementary
narrow MFA-reversal tripwire was added; it produced **zero flags** in v2. Unit
fixtures reject positive disable/turn-off/deactivate recommendations and cover
negations such as "do not disable MFA". This checks the previously observed failure
pattern, not all possible harmful recommendations; manual review remains necessary.
The historical baseline was not rewritten to invent a previous tripwire result.

Commands:

```powershell
backend\.venv\Scripts\python.exe scripts/benchmark_local_reports.py --self-test
backend\.venv\Scripts\python.exe scripts/benchmark_local_reports.py --run --model phi4-mini:3.8b --prompt-version evidence-v2
```

**Eight self-tests passed**, including negative shared-validator fixtures,
fixed-loopback/bounded requests, redirect refusal, memory-stop behavior, frozen
fixtures, separate prompt/no-fixture-ID checks, and MFA reversal/negation regressions.
Syntax checks passed. No application suite/build was rerun because no application
implementation changed. The benchmark exited zero for its automated gates only;
it does not encode independent semantic approval.

Raw ignored synthetic evidence:
`temp/auditmind-demo/browser/local-evaluation/phi4-mini-3.8b-evidence-v2-1792627588937942500.json`.
It contains prompt version/full prompt, model/runtime metadata, fingerprints,
all responses, metrics and flags. The baseline files remain intact.

The model was unloaded successfully, `/api/ps` returned no loaded models, and
approximately 5.05 GiB RAM was available afterward. System background activity
differs between runs; observed memory/timing differences are not controlled
hardware-efficiency claims. These are short synthetic responses, not full reports
or simultaneous model-plus-embedding workloads.

## Next gate

Do not enable local reporting yet. Freeze a held-out evaluation set before its
first model call, including independently verified positive evidence, mixed
verification, different asset/finding IDs, explicit harmful-action cases and
concrete multi-finding remediation requirements. This trial used known cases to
refine the prompt, so it is vulnerable to overfitting and cannot replace holdout
validation. Preserve this trial as a baseline; version any further prompt changes.
Then test the full production report contract, seven domains, scoring, citations,
larger evidence and concurrent embedding memory before provider/UI integration.
