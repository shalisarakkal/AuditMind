# Evidence-aware AI assessment — proposed contract

## Implementation follow-up — 23 October 2026

Opt-in implementation now exists under `REPORT_EVIDENCE_V3_ENABLED` (default false).
Default remains schema2/prompt-v3; new mode uses provider-only `EvidenceAssessment`
and server-owned `EvidenceSnapshot` schema3/prompt-v4. See the seven
[coverage profiles and privileged operator workflow](EVIDENCE_COVERAGE_PROFILES.md).
No qualification file is configured and no inference enabled by these changes.
Unqualified reports can complete as partial/unscored; new scores need reviewed
coverage. Legacy reads and rule-based reports keep their semantics. The first
qualification workflow is a single-organization operator pilot, not a self-service
approval UI. Binding/recency checks do not establish the truth of an attestation.
Broader rollout needs explicit policy adoption and file access controls. The
following design/approval history is retained; implementation verification follows
in the operational/testing records after the current run.

Final implementation verification is now complete:
[1,115 backend /312 frontend tests and both Chrome modes](EVIDENCE_ASSESSMENT_VALIDATION.md).
No new overall coverage measurement or real-provider acceptance is claimed.

Date: 23 October 2026. **Proposed contract approved by the user on 23 October 2026.**
Approval covers sufficient-only domain scoring, all-seven overall eligibility,
server-weighted aggregation, 0–10 remediation actions and the stated compatibility/
versioning strategy. Seven coverage profiles and the operator qualification workflow
are now defined; their adoption remains an explicit controlled-rollout decision.
This approval does not assert that implementation or verification is complete.
Default generation remains schema2 / prompt `audit-evidence-v3`; the new contract
is opt-in. No existing report, deterministic score, credential or consent is changed.

## 1. Decision proposed

Keep the deterministic finding-based baseline unchanged. For new AI assessments,
separate **evidence sufficiency** from **resilience/risk score**. Unknown controls
are neither passing controls nor failed controls. A reported weakness can warrant
remediation without supporting a numeric score for the whole domain.

Recommended first version: **only sufficient domains receive scores**. Limited,
insufficient and materially conflicting domains have explicit null score/tier.
This deliberately tightens the earlier possibility of scoring limited evidence:
there is not yet a defensible minimum-evidence rule for doing so.

All seven required domains must be sufficient and scored before an overall AI
score is available. Otherwise publish a completed **partial assessment**, not a
failed job, with no overall AI score/tier. Continue showing the separate captured
deterministic baseline; do not silently substitute it for missing AI scores.

## 2. Scope and evidence rules

Sufficiency is relative to a declared, versioned assessment scope, not a guarantee
of organizational completeness, real-standard conformity or certification.
Each domain needs a reviewed coverage profile defining assessed objectives,
required evidence types, applicability, evidence recency expectations and scope
boundaries. Reference guidance describes expectations; findings/observations and
verified operational evidence describe the organization. One cannot replace the other.

**Before implementation acceptance**, approve those seven coverage profiles and
their synthetic test fixtures. Current finding/document records alone do not
establish reliable provenance, full objective coverage, test success or evidence
freshness. Do not label evidence sufficient solely because a file was uploaded,
has a recent upload timestamp, matches a standard, or has a high model confidence.
If qualifying coverage cannot be established, remain unscored. Do not invent a
"two documents" or "three findings" threshold.

The AI proposes a status and reason using captured evidence; backend validation
enforces admissible references and contract invariants, not truth of every claim.
Server-owned scope/coverage metadata must not be supplied or approved by the model.
A sufficient proposal is score-eligible only under the approved coverage policy;
without that policy/qualification it must not publish as sufficient. Exact policy
qualification workflow is a design prerequisite, not an implemented capability.
Human review remains necessary; machine validation cannot prove semantic support.

## 3. Domain states

| Status | Definition | AI score / tier | Display |
| --- | --- | --- | --- |
| sufficient | Approved scoped objectives have qualifying supporting observations, required context and no unresolved material conflict. Can include verified weaknesses. | Required integer0–100 / matching tier | Advisory AI score, scope and coverage explanation |
| limited | Relevant observations support some conclusions, but coverage/context is incomplete. | Both null | Limited evidence — domain not scored |
| insufficient | No usable organizational evidence for the domain's defined assessment, or no support beyond generic guidance. | Both null | Not assessed — insufficient evidence |
| conflicting | Admissible observations materially disagree on the same objective, scope and relevant period, preventing a defensible domain score. | Both null | Assessment unresolved — conflicting evidence |

Do not infer conflict merely from two documents having different wording or
timestamps. Require references to at least two disagreeing captured observations,
the affected objective and an explanation. Irrelevant conflicts do not invalidate
an entire domain; materiality and scope must be explained. A material unresolved
conflict takes precedence over sufficient/limited for that domain.

Distinguish clipped text, sampled-out findings, missing tests, stale evidence,
unknown applicability and conflicting observations. Omission metadata signals a
limitation, not automatically insufficiency for every domain. A cited standard
alone does not demonstrate operation. No findings does not prove good controls.
Low confidence alone does not determine evidence status. Insufficient evidence
does not suppress legitimate supported remediation or investigation guidance.

## 4. Proposed new snapshot contract

Reserve **assessment schema3**, prompt **`audit-evidence-v4`**, and evidence policy
**`domain-evidence-v1`** for implementation; names are proposals, not active targets.
Keep all seven domain entries exactly once and retain existing report text fields.

Each domain would add:

- `evidence_status`: required enum from the table.
- `evidence_reason`: required nonempty explanation, including scope/coverage gaps.
- `evidence_finding_ids`: unique captured included finding UUIDs (may be empty).
- `citation_ids`: existing unique allowed included source references.
- `score`, `tier`: explicitly present; required number/tier only for sufficient,
  both null otherwise. Missing fields are invalid in new schema, not default zero.

Sufficient/limited must cite relevant organizational observations in at least one
allowlisted reference field. Conflicting needs at least two distinct supporting
observations plus a material-conflict explanation. Insufficient can reference
limited context without claiming it proves an assessed control. An excluded source
or a foreign tenant UUID is never admissible. Retain original evidence/hash/spans;
do not ask the model to fabricate provenance or rewrite source records.

Server-owned provenance would record the policy/coverage-profile versions, fixed
seven-domain scope, status counts, evidence limits, overall eligibility and scoring
method. Require the assessed scope to remain all seven domains in this first
version; no "not applicable" shortcut to a favorable overall score.

Remediation confidence retains its current semantics and non-calibration label;
it is not domain evidence coverage or probability of remediation success.
Recommend allowing **0–10 distinct remediation actions**, removing the artificial
five-action minimum in the prompt. Zero is allowed when nothing specific is
supported; evidence collection recommendations remain possible, clearly labeled
as guidance with no invented finding/asset references. Validate the explicit limit.

### Illustrative fragment only — not a complete report or current valid schema

```json
{
  "domain": "backup_recovery",
  "evidence_status": "limited",
  "evidence_reason": "Backup jobs report success; restore-test evidence is missing.",
  "evidence_finding_ids": ["20000000-0000-4000-8000-000000000003"],
  "citation_ids": ["SYN-RESTORE"],
  "score": null,
  "tier": null
}
```

## 5. Overall eligibility and aggregation

For new schema, backend derives `assessment_status`:

- `complete`: seven sufficient domains with valid scores; overall eligible.
- `partial`: at least one limited/insufficient/conflicting domain; overall score
  and tier explicitly null. Expose the seven-state coverage breakdown.

When eligible, backend computes the overall score, rather than accepting a second
independent model judgment. Proposed fixed weights match existing domain weights:
identity20%, network15%, vulnerability15%, backup15%, monitoring15%, incident10%,
compliance10%. Compute integer weighted sum divided by100; round half up to an
integer (e.g.59.5 becomes60), then apply80/60/40 tier boundaries to that rounded
score. Record an explicit aggregation version. Never average only scored domains,
reweight the remaining domains, turn null into zero, or silently impute a score.

The model response and server snapshot must use separate contracts: model returns
domain judgments; server derives overall fields/status and owns provenance. Do not
silently "repair" invalid model domain scores or contradictory evidence states.
Invalid responses follow current failure handling; a valid partial assessment is
successful. Queued job status and assessment completeness are independent concepts.

This makes aggregation reproducible **given the same domain scores**; it does
not make model-generated scores or evidence judgments reproducible. Repeatability
remains an evaluation concern; deterministic baseline stays the stable measurement.

## 6. Retained reports, APIs and presentation

- Dispatch by persisted schema version; missing version uses explicit legacy path.
  Never revalidate schema1/2 snapshots using new required fields or reinterpret their
  saved scores/tiers. Display "Evidence status not recorded (legacy assessment)".
  Do not infer status from narrative keywords, confidence or a historical score.
- Do not rewrite historical snapshots or backfill a sufficiency label. Rule-based
  test reports keep their separate deterministic contract and no-AI labels.
- Review list API projections, score filters/sorting, report detail, shared types,
  worker publication, HTML/PDF/print and export readers. Null overall AI score must
  render as "Partial AI assessment — overall score unavailable", never0/100,
  a fabricated tier, pending generation or report failure. Domain label uses the
  exact state; do not color missing evidence as a critical failure.
- Score-range filters exclude unscored reports unless explicitly requested by a
  separate assessment-status filter. Numeric sorting should place unscored last
  in either direction; expose stable pagination and counts. Saved old filters must
  not acquire fabricated zeros. Verify actual queries before implementation.
- Baseline remains visible and separately labeled even for partial AI assessment;
  it can itself be unavailable historically. Show complete reasons, included source
  references and coverage limitations. No report claims certification.
- JSONB snapshots may avoid a database DDL migration, but confirm nullable API/query
  behavior and all consumers before deciding; no Alembic change is assumed here.
- New prompt/policy/coverage versions must participate in processing-target identity
  and queued-job pinning. Require fresh organization approval; block stale pinned
  jobs instead of silently rerouting. Review new schema size against byte budgets.
  None of this grants consent or authorizes a provider call by itself.

## 7. Acceptance specification — tests to implement, not tests already run

| Area | Required cases |
| --- | --- |
| State invariants | Each state; missing/unknown state/reason; omitted score vs explicit null; sufficient without score; other states with number/tier; mismatched score/tier; booleans, numeric strings, NaN/Infinity, fractions and out-of-range values rejected. |
| Domain coverage | All seven exactly once; duplicate/missing/unknown domains fail. Missing objective qualification cannot become sufficient. Guidance alone, no findings, old observation/new upload and clipped relevant evidence are not proof of sufficient coverage. |
| Evidence security | Included/omitted/foreign UUIDs, duplicate IDs, assetless observations, unknown citation IDs, prompt injection and conflicts in untrusted text; server profile/provenance cannot be overridden. |
| Conflict | Two same-scope incompatible observations -> conflicting/unscored; different scopes/dates need explanation, not automatic conflict; no single-source invented conflict. |
| Aggregation | All seven sufficient -> exact weighted result; any one of the21 domain/non-sufficient combinations -> partial/null; score0 is valid; half-up ties and39/40,59/60,79/80 boundaries; no dropping/reweighting domains. |
| Remediation | 0/1/10 supported actions accepted,11 rejected; no repeated padding; guidance vs finding-specific actions; confidence0/null/1 and reference rules remain explicit. AI null confidence remains invalid. |
| Compatibility | Actual retained schema1/2 fixtures unchanged; missing provenance; rule-based snapshots; new partial snapshots survive API list/detail/HTML/PDF; unknown future schema fails clearly instead of guessing. |
| PostgreSQL | Real snapshot persistence, immutable source capture, total/sample counts, mixed-version list sorting/filtering/pagination, tenant isolation, job idempotency/retry/cancel, pinned-target and consent invalidation. |
| Frontend/Chrome | Complete/limited/insufficient/conflicting/legacy states; zero vs null; no fake tier; keyboard source navigation; mobile, HTML/PDF and print show full explanations; partial completion not a failed/pending job. |
| Operations | Larger schema within input limits, output truncation fail-closed, versioned consent/policy change, mocked provider failures, no unapproved real HTTP. |

Repeat the current manual cases with frozen prompt/evidence and recorded model,
date/settings/fresh-chat method. Expected NORMAL: patch/MFA/contact findings
support limited domain conclusions, backup is limited, network/monitoring/compliance
insufficient; no overall score. SPARSE: incident limited, remaining domains
insufficient; do not reuse omitted data. CONFLICT: backup conflicting; INJECTION:
attack ignored, legitimate observation preserved. Add separately reviewed fully
covered synthetic cases and bounded coverage profiles for the sufficient path;
do not simply rename NORMAL sufficient to obtain a score.

Target no fabricated references, false certifications or obeyed injections in
evaluated samples, with every status traceable to evidence. Compare same-evidence
state consistency across repeats and manually review score/priority variation.
Do not claim a statistical reliability guarantee from a small test batch.

## 8. Approval and delivery gates

User approved the contract and authorized profile definition/implementation on
23 October 2026. Profiles and the operator workflow are now defined and implemented
opt-in; the full PostgreSQL suite, frontend/build and mocked Chrome acceptance pass
as recorded above. Remaining gate is operator adoption of those profiles, trusted
review/pack setup and explicit controlled rollout—not an implied grant of external
processing consent or real inference. Local-testing milestone stays closed; this
post-milestone implementation does not reopen its prior acceptance requirements.
