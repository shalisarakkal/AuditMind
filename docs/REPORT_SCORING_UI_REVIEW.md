# Report scoring and confidence: review before changes

23 October 2026. Initial scope: document saved manual evaluation and review current source
and existing component tests. At that initial review no behavior was changed or
new Chrome session run. See the subsequently approved implementation below.

## Evidence

The user supplied NORMAL, NORMAL2, SPARSE, CONFLICT and INJECTION JSON responses
in `temp/chatgpt-evaluation`. Same displayed GPT-6 model is user-reported for all
five; fresh-chat/search settings and timestamps remain unknown. All five passed
the offline actual-schema/reference checks on this review date. The two validator
self-tests also passed. Full response hashes and case notes are recorded in
`temp/chatgpt-evaluation/RESULTS.md` (temporary evidence, not guaranteed retained
by Git). No real Claude or API calls, billing or provider identity were verified.

NORMAL vs NORMAL2: overall 51/high vs 49/high; identity45/high, vulnerability30/critical
and incident50/high unchanged; network, backup, monitoring and compliance each
changed from60/medium to55/high. Both preserved core facts and valid references.
SPARSE respected reference exclusions but repeated contact-review tasks; CONFLICT
retained contradictory observations; INJECTION did not obey the embedded attack.
This is preliminary, small-sample manual quality evidence, not live acceptance.

## Source review findings

| Priority | Existing behavior and source | Assessment |
| --- | --- | --- |
| P2 | `frontend/src/components/ReportViewer.tsx`: provenance compares rule-based and AI scores; prominent card says "Overall Resilience Index"; list in `frontend/src/app/(app)/reports/page.tsx` says "Score". | Separation exists, but primary score surfaces do not explicitly say advisory AI assessment. Numeric tier changes may look like measured posture changes. |
| P2 | ReportViewer domain cards require a numeric score, clamp justification to three lines and show only first strength/weakness, truncated. `backend/app/schemas/report_ai.py` requires numeric scores and all seven domains. | Uncertainty can be hidden while a precise score stays prominent. There is no structured insufficient-evidence state; not a frontend-only change. |
| P2 | ReportViewer says counts were "evaluated against standards" and "The model did not receive every finding" unconditionally for modeled provenance. | Counts describe whole inventory, not complete sampled control assessment. Latter statement is inaccurate if all findings were included. Actual selection metadata must drive wording. |
| P2 | Domain/action citation_ids are validated by backend; frontend domain/action types omit them and ReportViewer shows related_controls as "Standards" plus a separate citation collection. | Per-claim citation support is difficult to inspect. Free-text related_controls can look authoritative without being validated official control identifiers. |
| P3 | ReportViewer and `backend/app/services/report_service.py` display "Model-estimated confidence: N% (not calibrated)"; absent confidence says not recorded. | Already implemented; do not call this missing. Percentage can still imply precision. More plain-language explanation would help; confidence is not evidence completeness or probability of success. |
| P2 | HTML/PDF exporters prominently show overall/domain scores; baseline and limits reside in raw provenance content. | Any approved label/uncertainty revision must include exports/printing, not only browser cards. |

The frontend already distinguishes rule-based test snapshots as no-AI and no
framework evaluation. AI provenance already exposes model/prompt, capture time,
baseline, evidence limitations and expandable captured metadata. Retain these.
Legacy reports correctly identify missing full provenance; do not fabricate it.

## Recommended order — proposals only

1. **Presentation first:** explicitly label AI scores as advisory wherever shown;
   keep the captured deterministic baseline separately labeled and easy to see.
   State higher scores mean greater resilience and AI variation is not measured
   posture change. Keep unknown legacy baseline as unknown, never default to zero.
   Use actual sampling/omission metadata; show full justifications on demand.
2. **Explain confidence:** preserve the existing non-calibration label and add
   that this is model-estimated support, not probability of compliance, successful
   remediation or complete evidence. Apply consistently to UI/HTML/PDF.
3. **Evidence links:** expose allowed citation IDs on domains/actions and link to
   captured source entries; distinguish descriptive related-controls text from
   verified source references. No new standards/license claims.
4. **Separate contract design:** consider evidence-status values such as
   sufficient/limited/insufficient/conflicting with explicit definitions and
   references. Decide when a score is permissible and how overall assessment
   handles unscored domains. Do not guess evidence status from low confidence,
   score value, missing citation alone, or narrative keyword matching. Define
   missing-evidence-not-failure semantics, retained snapshot compatibility,
   schema/prompt versioning, consent changes and output validation before coding.
5. Reduce pressure to pad sparse reports with a fixed minimum action count only
   after reviewing contract/test implications. Same-evidence priorities/effort
   remain advisory unless an explicit deterministic rubric is approved.

No proposal is an approved implementation or an automatic new Phase 3 release gate.
Deterministic baseline measures findings under its own rubric; it is not proof
of framework compliance or ground truth for an untested domain either.

## Subsequently approved presentation follow-up — 23 October

The user subsequently authorized presentation-only implementation. The initial
source findings above describe the pre-change review, not remaining unimplemented
UI defects. List/detail now label AI scores advisory; detail shows the captured
deterministic baseline separately (including zero and missing values), explains
confidence and score semantics, and derives sample coverage from captured counts.
Complete domain justification/strengths/weaknesses and citation content are visible.
Domain/action citation IDs link to matching captured sources; missing retained
sources are explicitly unavailable. Related-control text is labeled descriptive.
HTML/PDF include advisory/baseline/sampling/confidence explanations and evidence IDs.
No saved scores, tiers, snapshots, provider requests, consent targets or backend
schemas were changed. Optional TypeScript citation fields mirror existing stored
fields. Insufficient-evidence scoring/aggregation remains a **separate unimplemented
contract decision**, requiring the design and verification described above.

Implementation verification: all **307 frontend tests** passed; **43 focused backend
unit/export regressions** and **20 PostgreSQL integration regressions** passed,
warnings as errors for Python. Lint, TypeScript and production build passed.
`auditmind_test` restored to migration0021 with clean Alembic drift check after
integration tests. Native Chrome follow-up is recorded after completion below.
Existing jsdom navigation diagnostic remains nonfatal. No inference or paid calls.

Native Chrome follow-up: **17/17 checks passed**, including advisory/baseline and
confidence labels, keyboard evidence navigation, mobile viewport, print-media
visibility, real HTML/PDF downloads, permissions, failures and cancellation.
Evidence: `temp/auditmind-demo/browser/phase3/phase3_browser_c9c0c3bdc033/`.
API/worker/PostgreSQL were real; embedding/inference responses mocked with external
provider HTTP forbidden. First attempted run failed because the old mock response
did not populate citation_ids; its schema was cleaned, the fixture was updated to
use retrieved IDs, and the full checklist rerun. Eight fixture regression tests
also passed. Only the corrected complete run is counted as acceptance.

## Required verification for any later implementation

- Unit/component: AI vs rule-based labels, retained/missing provenance, confidence
  zero/null/one, expandable complete text, all/no/subset samples and omitted sources.
- Integration/regression with PostgreSQL: snapshot compatibility, original evidence
  unchanged, reference allowlists, source capture, exports and scoring boundaries.
- If contract changes: complete domain coverage, unknown/conflicting evidence,
  null-score rules, overall aggregation and old snapshots; version/consent tests.
- Native Chrome: list/detail/export/print at desktop/mobile and keyboard access;
  uncertainty remains visible and distinct from a measured failure.
- Repeat controlled manual cases with recorded model/settings/time, assess factual
  consistency and tier stability, not exact prose. Real provider tests require
  separate authorization; no paid calls inferred.

## Verification performed for this review

- Five saved JSON responses: actual-schema/reference validator passed for each;
  NORMAL2 validated as the NORMAL case. Two validator self-tests passed.
- Frontend focused regressions: `npm test -- src/test/reports.test.tsx
  src/test/report-detail.test.tsx` — **29 tests passed across two files**.
  Existing jsdom "navigation to another Document" diagnostic appeared; exit0.
  Report-detail tests mock ReportViewer; reports tests exercise the actual viewer,
  including confidence and legacy references. These tests do not establish that
  the proposed wording/uncertainty improvements already exist.
- No production code changes; no full backend rerun, build or new Chrome check
  performed in this documentation-only task. Prior acceptance remains historical.
