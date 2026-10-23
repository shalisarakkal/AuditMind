# Evidence coverage profiles and trusted qualification

23 October 2026. Implementation policy **domain-evidence-v1**, opt-in assessment
schema3 / prompt `audit-evidence-v4`. No standard certification or external model
approval is implied. These are application coverage criteria, not copied official
framework requirements. Existing deterministic scoring is unchanged.

## Seven profiles

Each profile has three mandatory objectives. The reviewer must establish actual
operational observations for every objective over the **same declared scope**;
weak outcomes still count as observations and can justify low resilience scores.
Coverage does not mean the controls passed. Numeric guidance is advisory.

| Domain | Required objectives | Operational evidence the reviewer must assess |
| --- | --- | --- |
| Identity/access | privileged_authentication; account_lifecycle; access_review | Scoped privileged authentication/enforcement checks; creation/removal outcomes; access-review scope/results and follow-up. One MFA finding is only partial coverage. |
| Network configuration | exposure_inventory; segmentation_test; configuration_review | Actual scoped reachability/exposure inventory, segmentation test results and configuration review outcomes. A policy or untested network diagram alone is insufficient. |
| Vulnerability management | scan_coverage; patch_validation; exception_review | Actual scan scope/coverage limitations, verified patch status, reviewed exceptions and ownership. One missing patch does not establish full-domain coverage. |
| Backup/recovery | backup_coverage; restore_test; recovery_objectives | Covered systems/data and job outcomes, actual scoped restore results, reviewed recovery objectives and observed comparison. Successful jobs do not prove restore success. |
| Monitoring/detection | log_coverage; detection_test; alert_triage | Verified log-source coverage, exercised detections/results and observed alert handling. Installed tools/configuration alone do not prove effectiveness. |
| Incident response | contact_validation; response_exercise; lessons_followup | Verified contacts/escalation, scoped response exercise outcomes and reviewed lessons/actions. A stale contact-list finding is limited evidence, not whole-domain proof. |
| Compliance alignment | applicability_mapping; control_evidence_review; gap_review | Reviewed scope/applicable requirements, actual organization evidence mapping and documented gap review. Generic standard excerpts cannot establish conformity/certification. |

## Qualification workflow

This first implementation uses a **trusted operator-maintained JSON file**, not a
model-generated attestation or organization-uploaded document. There is no new
self-service approval endpoint/UI. Treat file write access as privileged assessment
approval authority; do not put it under the uploads directory or allow untrusted
jobs/users to edit it. Deploy with appropriate OS permissions. A reviewer must
actually inspect evidence; the code verifies bindings/invariants, not semantics.

1. Review a captured evidence set and the domain profile objectives. The JSON
   source must match the complete included finding or organization-policy citation
   object, not just a human title. Official/reference-only excerpts cannot qualify
   organizational operation. An organization-policy citation may contain operational
   observations, but its type alone is not sufficient: the reviewer must verify
   those observations and set `operational_review: true` only when justified.
2. The operator supplies policy version, organization UUID, reviewer identity,
   common scope, timezone-qualified review/expiry dates and observations. For each
   domain/objective entry, record the included source ID/type, source hash, actual
   observation date, scope and operational-review attestation. One source may
   support multiple objectives only if the reviewer verifies each separately.
3. Compute each `source_sha256` with `evidence_policy.source_hash(source)`:
   SHA256 of UTF-8 JSON with sorted keys, compact separators and string handling
   for dates/UUIDs. Obtain the original source object from captured snapshot
   provenance/retrieval evidence; do not hash a browser-formatted text excerpt.
   Record actual observation time, never infer it from upload time.
4. Store the file outside Git/temporary public-serving locations. Set
   `REPORT_EVIDENCE_QUALIFICATIONS_FILE` to its local path. Max file128KiB,
   max100 observations. The first pilot supports one organization per configured
   file; another organization is refused rather than using its qualifications.
5. Set `REPORT_EVIDENCE_V3_ENABLED=true` only for a controlled rollout. This does
   not configure credentials, start inference or grant external consent. Default
   remains false for compatibility while operators review profile adoption.
6. Restart affected API/worker processes consistently. The policy/profile/aggregation
   version and exact pack-byte hash participate in processing-target identity.
   Fresh organization processing approval is required. Old pinned jobs fail closed.
7. Inspect the resulting captured qualification provenance and source references.
   No file configured means no domain is eligible to score, but a partial report
   can complete normally. With a file configured, malformed/mismatched/stale records
   fail the job instead of silently granting or repairing qualification.

The operator can attest existing evidence without running a new model call; no
real inference is authorized by these instructions. Keep any qualification pack
containing organization evidence metadata local and access controlled.

## Enforced rules

- Qualification requires all three objectives; exact organization/policy/scope;
  a named reviewer and review/expiry interval no longer than90days.
- Observations must have explicit timezones, precede the review, and be at most
  90days old at evidence capture; expiry must still be in the future.
- Only included captured references qualify. Excluded, retired/unretrieved,
  foreign-scope or hash-mismatched objects fail; marked truncated findings cannot
  qualify. Finding-domain association must match the attested domain.
- Generic guidelines are not organizational operational evidence. Missing objective
  coverage does not grant sufficiency. Pack changes invalidate consent/job targets.
- The model cannot submit provenance/overall scores/qualification metadata and
  cannot label a domain sufficient without trusted complete coverage and references
  to that coverage. Limited/insufficient/conflicting domains have null score/tier.
- Conflict reason must describe material contradiction on the same scope; at least
  two source references are required. Semantic support/materiality still need
  human review: two IDs alone do not prove independent conflicting observations.

## Limitations and follow-up

This operator workflow is intentionally conservative and not a scalable approval
UI or a verified independent security audit. Recency90days is an application policy,
not a universal compliance interval. Exact-source hashes are sensitive to source
changes and retrieval selection; stale qualifications need re-review, not automated
rehashing. Budget exclusion of a qualifying source fails closed rather than
changing the approved scope silently. Do not deploy publicly or enable real AI
without the separate outstanding approvals in [release readiness](RELEASE_READINESS.md).

See [approved design](EVIDENCE_ASSESSMENT_DESIGN.md) for null/legacy handling,
server-weighted aggregation and acceptance cases. Local milestone remains closed;
Docker and report-date UI remain Future.
