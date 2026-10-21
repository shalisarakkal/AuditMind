# Phase 3 — Completion Checklist

**Status:** Implementation committed; acceptance/sign-off pending.

**Status reviewed:** 2026-10-20.

Current operational status supersedes older implementation-gap notes below:
PostgreSQL-backed quota/cost reservations, report idempotency, terminal-report
retention and offline embedding deployment files are implemented. See
[operational contracts and deployment gates](docs/PHASE3_OPERATIONS.md) and
[validation results](docs/BACKEND_VALIDATION.md). Container startup/cache validation
requires a Docker-capable staging host. This is not full Phase 3 sign-off.
**Prerequisites:** All Phase 2d prerequisites complete (imports at scale, archive/restore/purge, background worker).

## Feature-development record — 2026-10-08

### Requested work and current stage

The user requested: **complete document ingestion, retrieval, and evidence provenance**. Other Phase 3 requirements remain separate unless directly needed by this feature.

**Current stage:** architecture approved; entering implementation, beginning with runtime and source verification. No implementation changes, dependency installations, model downloads, migrations, or test runs have been performed for this feature yet. Existing uncommitted Phase 3 implementation must be preserved and built upon.

### Agreed development workflow

The user requested that all steps of `feature:dev` always be followed. That named workflow could not be loaded in this session. The user approved this seven-stage equivalent:

1. Discovery.
2. Code exploration.
3. Clarifying questions.
4. Architecture design.
5. Implementation.
6. Quality review.
7. Summary.

Clarifying questions and design approval must precede implementation. Maintain this document as decisions are made, distinguishing confirmed choices, recommendations, unresolved questions, implemented behavior, and verified results. Do not mark proposed work as complete.

### Confirmed decisions

| ID | Topic | Decision |
|---|---|---|
| D1 | Feature scope | Complete document ingestion, retrieval with citations, and evidence provenance. |
| D2 | User interface and API | Provide a Documents UI and API, not a backend-only implementation. |
| D3 | Initial upload formats | Support UTF-8 text and Markdown uploads. PDF upload support was not selected for this feature. PDF report export is a separate Phase 3 requirement. |
| D4 | Shared standards | Load shared standards through queued worker jobs alongside organization-document ingestion. |
| D14 | Initial standards baseline | Target NIST CSF 2.0, CIS Controls v8.1, ISO/IEC 27001:2022, and ISO/IEC 27002:2022 guidance. Import official content only where usage rights permit; clearly label references or original summaries otherwise. Expose availability/licensing status and verify exact source availability and rights before inclusion. Confirmed 2026-10-08. This is a selected baseline, not a claim that these are the latest editions or that full text has been acquired. |
| D5 | Embedding capability | Support a pluggable embedding system with local semantic models and configurable OpenAI and Voyage providers. The user selected this after requesting maximum support. |
| D6 | Default processing | Use local processing by default. Local semantic embeddings are the intended retrieval approach, rather than the existing deterministic lexical approximation. |
| D7 | External transmission | Require explicit approval/enabling before sending document text to external embedding providers. Implementation and tests must not transmit document text externally. Provider support is not permission to make live external calls. |
| D8 | Embedding identity | Track embedding model/version and prevent incompatible embeddings from being mixed. |
| D12 | Provider administration and consent | Platform sysadmins select the platform embedding provider/model; local processing is the default. Each organization must explicitly consent before its documents use an external embedding provider. If the platform selects an external model, non-consenting organizations remain on a local model/index while consenting organizations use the selected external model. Maintain separately compatible shared-standard indexes for each active embedding space. This refines the initial single-model selection: administrators control the default, but local and external indexes may coexist. Confirmed 2026-10-08. |
| D9 | Model changes | Support safe reindexing when the embedding model changes. Exact migration and reindexing mechanics await architecture approval. |
| D10 | Document permissions | Organization admins upload and manage their organization's documents; platform sysadmins manage shared standards; all organization members can read permitted documents. Confirmed 2026-10-08. |
| D11 | Document versions and removal | Published versions are immutable; updates create new versions; retirement excludes documents from future retrieval while preserving existing report evidence. Authorized admins may permanently remove retired, non-current versions after confirmation, deleting their source text and embeddings. Block removal while a running report uses the version. Completed reports retain their captured excerpts and provenance, so source removal does not erase those report snapshots. Confirmed 2026-10-08; transactional safeguards will be specified in the architecture. |

**D13 — Separate AI report consent (confirmed 2026-10-08):** organization admins must separately approve sending finding summaries and retrieved document excerpts to Claude before external AI report generation is enabled. Local document ingestion and retrieval remain available without that approval. Embedding consent does not imply report-generation consent, or vice versa. Enforce the report consent gate both when queuing a report and before external execution; existing organizations must not be assumed to have consented. Exact consent storage, revocation, and queued-job handling will be specified in the architecture.

### Options considered and rationale

- **Local deterministic embeddings:** the existing implementation provides reproducible lexical matching, useful for tests, but does not offer the meaning-based matching expected from semantic models.
- **Local semantic embeddings:** recommended as the default to improve meaning-based retrieval while keeping embedding processing local. Requires a model download, runtime resources, and model maintenance.
- **External embedding providers:** supported as configurable alternatives for model choice and managed operation. They introduce external data transmission, credentials, cost, and network dependencies. Quality depends on the selected model; no provider has been benchmarked for this project.
- **Combined support:** selected by the user to retain local privacy by default while allowing explicitly enabled external providers.
- Keeping deterministic embeddings for tests only was recommended; the exact test strategy remains part of the architecture proposal.

### Findings from targeted code exploration

These findings describe inspected code, not runtime-verified outcomes:

- [standards_service.py](backend/app/services/standards_service.py) seeds the bundled standards synchronously. A queued document-ingestion path still needs to be designed. No dedicated document-upload API was identified in the exploration so far.
- [document.py](backend/app/models/document.py) stores document content and standards metadata with a fixed **1,536-dimensional** vector column. It does not currently model the full ingestion-job, chunk, and embedding-identity lifecycle needed by this feature.
- [embedding_service.py](backend/app/services/embedding_service.py) supports deterministic vectors and conditional external calls. Provider failures silently fall back to deterministic vectors. This can mix incompatible embedding spaces and must be replaced with explicit failure handling rather than silent substitution.
- [rag_service.py](backend/app/services/rag_service.py) retrieves shared and organization-scoped documents and supports framework filtering. Returned citations lack stable document/chunk identifiers. Deduplication by control ID can collapse distinct sources, including policies without a control ID.
- [report_ai_service.py](backend/app/services/report_ai_service.py) gathers finding summaries and copies retrieved citations into the report snapshot. The sampled evidence does not include finding IDs, and generation does not yet capture a complete provenance record containing separate rule-based scores, model identity, and prompt version.
- [report_ai.py](backend/app/schemas/report_ai.py) validates AI score/tier consistency and domain completeness, but citation data remains a list of generic dictionaries rather than a complete typed provenance contract.
- [report_service.py](backend/app/services/report_service.py) persists the generated snapshot. The new provenance must survive that persistence and be available through report responses and presentation.
- [runner.py](backend/app/worker/runner.py) already claims import, report, and archive jobs. Document jobs must integrate with the existing queue, worker lifecycle, and recovery conventions.
- Pylance symbol inspection confirmed existing count-based rule-scoring helpers in [scoring_service.py](backend/app/services/scoring_service.py); their reuse and period semantics still need detailed verification.

### Open questions and design decisions still required

1. **Document permissions — resolved (D10).** Organization admins manage organization documents; platform sysadmins manage shared standards; organization members read permitted documents. Enforce these permissions on the API as well as in the UI.
2. **Local model and runtime — direction approved (D15, 2026-10-08):** prioritize multilingual coverage and retrieval capability over download size and CPU speed, using BGE-M3 as the proposed default candidate. The user accepts greater resource requirements. The official model configuration inspected in this session has a hidden size of 1,024. Verify embedding output behavior, license, runtime requirements, and a pinned revision before implementation. Exact dependencies, cache location, and setup/download procedure still require architecture approval; no packages or models have been installed.
3. **Vector compatibility:** decide how to support the selected models with the current 1,536-dimensional column. Do not silently pad vectors or mix embedding spaces. Migration, legacy data handling, and reindexing need an explicit design.
4. **Provider configuration and approval:** define who selects providers/models, whether settings are platform- or organization-scoped, and how external transmission is explicitly enabled and disclosed.
5. **Ingestion lifecycle:** define upload limits, metadata requirements, chunking, duplicate/version behavior, visibility while processing, failure/recovery handling, and document replacement/removal semantics.
6. **Shared standards content:** define the source and version of the initial corpus and permitted loading mechanism. Queued ingestion does not imply acquiring or reproducing full licensed standards.
7. **Provenance contract:** define stable document/chunk and finding references, captured excerpts/hashes, model and prompt versions, rule-based score snapshots, reporting period, and how this evidence appears in the report UI/API.
8. **Retrieval behavior:** settle framework filtering for organization policies, citation validation, ranking and coverage, and behavior when no relevant evidence is available.
9. **Report-generation disclosure:** distinguish local embeddings from the existing external Claude assessment path and document what evidence that path receives.
10. **Acceptance tests:** define targeted tests for isolation, worker recovery, provider errors, embedding compatibility, citation integrity, immutable provenance, and existing behavior preservation.

These are pending decisions or design details, not approved implementation specifications.

### Standards-loading scope clarification — 2026-10-08

The user asked whether the implementation will work out the CIS/NIST/ISO loading details and make the documents available. The intended deliverable is an operational, versioned knowledge library for retrieval and citations, not merely upload scaffolding. Exact editions, rights, and acquisition methods remain subject to verification and architecture approval.

Proposed source strategy:

- **NIST:** use official publications and machine-readable source material where available. CSF 2.0 is an initial candidate; SP 800-53 Rev. 5 is a separate control catalog, not interchangeable with CSF. Verify publication-specific notices, identifiers, and versions before inclusion.
- **CIS:** distinguish CIS Controls/Safeguards from product-specific CIS Benchmarks. Verify applicable licensing and redistribution/automated-use terms before bundling content; free download alone does not establish redistribution permission. Use an authorized import path where bundling is not permitted.
- **ISO:** select the applicable ISO/IEC 27001 and 27002 editions during design. Do not bundle or reproduce full copyrighted standards without appropriate permission. Support authorized organization-provided material only where its license permits the intended processing, and keep it organization-scoped unless broader sharing is authorized. Otherwise provide source references and clearly labeled original summaries, not substitute official text.

The planned library should identify framework, edition/version, source, control reference, document/chunk identity, and ingestion status; only successfully indexed, permitted material should be available to retrieval. Do not represent the current bundled summaries as complete official standards or a report as certification.

Source checks in this session: the official [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework) page references CSF 2.0; the official [CIS Controls](https://www.cisecurity.org/controls) page describes Controls and Safeguards. The [ISO 27001](https://www.iso.org/standard/27001) page returned HTTP 403 to the fetch tool. These checks do not establish licensing clearance, complete editions, or corpus completeness. No standards files have been acquired or indexed by this feature work.

### Deferred backlog — additional standards and evidence sources

**Decision, 2026-10-08:** the user requested that these additional capabilities be documented for a later phase. They are deferred beyond Phase 3, not Phase 3 completion blockers. Scheduling and implementation design remain unapproved; no new phase number is assigned. See also the deferred backlog in [PLAN.md](PLAN.md#deferred-backlog--standards-and-evidence-expansion-after-phase-3).

Keep CIS/NIST/ISO as the Phase 3 baseline and introduce additional sources in layers rather than enabling every framework for every organization. The following table inventories the deferred candidates; exact editions, licensing, acquisition, and applicability still require verification. Additional NIST catalogs mean expansion beyond whichever NIST baseline is approved for Phase 3, not deferral of NIST support itself. Basic organization-policy text/Markdown ingestion and report provenance remain in Phase 3; structured operational-evidence collection and evaluation are deferred.

| Source | Purpose | Suggested priority |
|---|---|---|
| NIST SP 800-53 and SP 800-53A | Detailed security/privacy controls and assessment procedures, complementing CSF outcomes | Core expansion |
| NIST SP 800-34 and SP 800-61 | Contingency planning/recovery and incident-response guidance; select applicable current revisions during design | Core expansion for resilience |
| CISA Cross-Sector Cybersecurity Performance Goals | Prioritized baseline practices to complement broad frameworks | Core expansion |
| CISA Known Exploited Vulnerabilities catalog | Evidence that a CVE has been exploited in the wild; this is a threat feed, not a compliance standard | Operational enrichment |
| FIRST EPSS and NVD/CVE records | Exploitation-probability estimates and vulnerability metadata/severity; distinct from observed exploitation | Operational enrichment |
| MITRE ATT&CK | Threat tactics/techniques and detection context; not proof of compromise or compliance | Optional threat/detection enrichment |
| OWASP ASVS and API Security Top 10 | Application-security verification requirements and API risk guidance; Top 10 alone is not a complete assessment standard | Enable for web/API workloads |
| Vendor security guidance and product-specific CIS Benchmarks | Actionable configuration guidance for the products actually present, such as cloud services, operating systems, Kubernetes, and databases | Enable based on inventory |
| PCI DSS, SOC 2 Trust Services Criteria, and applicable laws/regulations such as HIPAA, GDPR, NIS2, or DORA | Organization-specific obligations or assurance criteria; applicability depends on business, jurisdiction, and scope | Optional organization-selected packs with licensing/applicability review |
| ISO 22301 and ISO/IEC 27701 | Business continuity and privacy management, subject to applicable licensing | Optional resilience/privacy packs |
| Organization policies, asset criticality, recovery objectives, recovery-test results, and incident-response exercises | Organization-specific requirements and actual operational evidence | First-class evidence alongside external guidance |

Architecture implications to consider in the design:

- Distinguish normative requirements, implementation guidance, threat/vulnerability feeds, and organization evidence in metadata and report language.
- Keep versioned standards ingestion separate from timestamped, refreshable feeds; preserve the exact feed facts used in a report snapshot.
- Allow organizations to choose applicable frameworks and guidance; avoid claiming compliance against material they did not select or that is not licensed/available.
- Record authority, source URL, edition/version, retrieval time, licensing restrictions, and document/chunk identity as appropriate.
- Label control mappings as sourced or inferred; mappings do not establish equivalence or justify double-counting the same finding across frameworks.
- Treat regulatory/assurance outputs as assessment support, not legal advice, certification, or an auditor's attestation.

#### Later-phase work packages and acceptance criteria

All items below are deferred and unimplemented. Dependencies describe prerequisites, not an approved schedule.

- [ ] **Expanded control and resilience catalogs:** add the selected NIST catalogs, CISA goals, and licensed continuity/privacy sources. Verify editions and usage rights, ingest through the Phase 3 document pipeline, and expose source/version/control citations. Acceptance: an organization can select each available catalog and retrieve traceable controls without presenting summaries as official full text.
- [ ] **Vulnerability intelligence:** integrate CISA KEV, FIRST EPSS, and NVD/CVE data with scheduled refreshes, CVE matching, deduplication, source timestamps, stale-data indicators, and failure handling. Acceptance: findings show the matched facts and their dates; reports retain the exact facts used even after feed updates. Keep observed exploitation, predicted likelihood, and severity distinct. Depends on the Phase 3 provenance foundation and reliable CVE identifiers.
- [ ] **Technology-specific guidance:** add selected vendor guidance, product-specific CIS Benchmarks, OWASP ASVS, and API guidance. Match applicability to inventory/product versions and permit organization selection. Acceptance: irrelevant checks are not treated as applicable requirements, and recommendations cite the correct source edition. Licensing must be verified before content is distributed.
- [ ] **Threat and detection mapping:** add MITRE ATT&CK mappings with technique/version references and mapping rationale. Acceptance: inferred and authoritative mappings are distinguishable; a mapping alone is never treated as proof of compromise or effective detection.
- [ ] **Regulatory and assurance packs:** add selected PCI DSS, SOC 2 criteria, and jurisdiction/sector-specific requirements after licensing and applicability review. Acceptance: users explicitly scope applicable packs and reports distinguish assessment support from certification, legal advice, or attestation.
- [ ] **Operational resilience evidence:** add structured recovery objectives, restore-test results, incident-exercise outcomes, and criticality-driven evaluation. Acceptance: reports distinguish a documented policy from tested operational capability and preserve evidence dates and references. Existing text/Markdown policy ingestion remains Phase 3 scope.
- [ ] **Cross-source governance:** implement applicability settings, sourced/inferred control mappings, and rules preventing duplicate risk deductions for the same finding across frameworks. Test tenant isolation, licensing restrictions, version changes, feed outages, and snapshot stability. This extends rather than postpones Phase 3's source identity, access controls, and immutable provenance requirements.

Suggested sequence once scheduled: expanded baseline guidance and KEV enrichment, then workload-specific guidance, followed by threat mappings, optional assurance packs, and structured operational evidence. Actual ordering should follow customer needs and source availability. Recording this backlog does not authorize immediate implementation or external data transmission.

### Approved architecture — 2026-10-08

After initially selecting revision, the user clarified: “Ok. NO change.” Proceed with the architecture below without revisions. Runtime/source verification must precede model installation or bundling standards; bring material design changes back for approval.

The following design implements D1–D15. Approval is not completion: numerical defaults and internal structure below describe the intended implementation, not verified behavior.

1. **Separate document identity, versions, chunks, and indexes.** Keep stable document identities with immutable published versions. Each version records source, framework, edition, content kind (official text/original summary/reference), rights metadata, hash, and ingestion status. Chunks record stable IDs, ordinal, section/reference, exact text, and hash. Embeddings belong to a model profile and chunk, rather than overloading the existing fixed-size document vector. Preserve existing records and report snapshots during migration; legacy vectors are not implicitly treated as semantic embeddings.
2. **Embedding profiles.** Use local BGE-M3 dense embeddings (1,024 dimensions) as the proposed default, with a pinned revision and explicit setup/download step. The official model card declares MIT licensing, more than 100 languages, and an 8,192-token maximum; it states query instructions are unnecessary. Use bounded tokenizer-aware chunks and batches rather than maximum-length documents. Support OpenAI and Voyage adapters with configured model identity, appropriate query/document input modes, finite/nonzero vector validation, and dimension checks. No silent provider substitution. Keep embeddings isolated by profile; use compatible-dimension pgvector storage and profile-filtered queries, with dimension-specific indexes where needed. Exact runtime/package versions remain to be verified before installation.
3. **Consent and index activation.** Store separate embedding and Claude consent records with actor, timestamp, and disclosure/provider identity. Recheck consent before external work and before publishing a report. Non-consenting organizations use local retrieval, including a local copy of shared-standard embeddings. Build replacement indexes separately and activate them only when complete. Provider/model changes invalidate affected external consent unless explicitly covered by the approved disclosure. Revocation prevents new calls; it cannot undo data already sent or cancel an already-issued provider request.
4. **Queued ingestion.** Add a document job kind to the existing database worker, including heartbeat, bounded interrupted-job recovery, failure details, and activity events. Propose a configurable 10 MiB UTF-8 text/Markdown upload limit. Preserve paragraph/heading boundaries where possible, with tokenizer-safe splitting and overlap; never silently truncate text to fit a model. Stage chunks/embeddings and publish atomically. A failed replacement leaves the previous published version active. An identical upload within the same document returns the existing matching version instead of creating another copy.
5. **Publication and removal.** Only ready/current, non-retired versions participate in new retrieval. Publish a new version and supersede the previous one atomically. Confirmed purge is limited to retired, non-current versions and is serialized against report evidence capture. Track report/version usage explicitly; do not rely on scanning JSON snapshots. Remove source text, chunks, and vectors while retaining minimal provenance identifiers/tombstones and evidence already captured by reports. Account for abandoned report jobs so references do not block removal forever.
6. **Scoped retrieval.** Filter by permitted organization/shared scope, active version, embedding profile, and content availability before ranking. Framework selection applies to standards; eligible organization policies without a framework remain available. Deduplicate by chunk/version identity rather than control ID. Return stable citation identifiers, excerpts, section references, source/version, hashes, and retrieval/model metadata. Reference-only entries are catalog links, not authoritative full-text evidence. Surface unavailable or insufficient evidence explicitly.
7. **Evidence snapshots.** Capture finding IDs and sampled finding values, reporting-period semantics, deterministic counts and rule-based scores, retrieval citations, model identity, prompt version/hash, and generation time. Clearly label sampling limits; do not imply the model saw every finding. Build a consistent database evidence snapshot before the external request and release database transactions during provider execution. Keep AI scores separate from rule scores. Validate structured citation references against the retrieved set before saving; instructions must treat source content as evidence, not executable instructions. Persist provenance independently of later source removal and display it in report detail/API/HTML output. Existing reports remain readable and are labeled as legacy when provenance was not captured.
8. **Screens and permissions.** Add organization Documents browsing, upload/version history, status, preview, retirement, and confirmed old-version removal. All members read permitted sources; organization admins manage their own sources and consents. Add platform management for shared standards and embedding configuration/setup status, restricted to sysadmins. Respect existing archived-organization read-only rules and sysadmin read-only organization access. Show actual corpus coverage and rights/availability status rather than implying complete CIS/ISO official text is bundled.
9. **Baseline content.** Use the approved NIST CSF 2.0 / CIS Controls v8.1 / ISO 27001:2022 and 27002:2022 targets. Verify acquisition and usage rights, preserve source versions, and queue permitted initial content. Keep original summaries explicitly labeled; do not fabricate official control text or claim licensed full-text coverage. Provide authorized import mechanisms for restricted material. Source acquisition remains a prerequisite to claiming corpus completeness.
10. **Validation.** Add targeted tests for permissions and isolation, version publication/purge races, worker recovery, malformed uploads, model dimension/profile mismatches, provider failure without fallback, consent queue/execution/revocation behavior, policy retrieval with framework filters, stable citations, rule-score preservation, date/sample semantics, legacy reports, and retained report evidence after source removal. Use mocked external providers only. Run a local semantic smoke test after explicit model setup; evaluate retrieval on a small known-answer evidence set. Update this document and directly related operational/configuration documentation with actual results.

#### Public-source verification notes

- [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3): verified declared MIT license, 1,024-dimensional dense embeddings, multilingual support, 8,192-token limit, and no query instruction requirement. Runtime choice, immutable model revision, and resource measurements are not yet finalized.
- [CIS Controls v8.1](https://www.cisecurity.org/controls/v8-1): verified edition page and advertised PDF/Excel download formats. These facts do not establish permission to redistribute or externally process full content.
- NIST machine-readable acquisition and publication notices still need verification. ISO acquisition/licensing remains unresolved; the earlier official-page fetch was blocked.
- A research subagent failed to start because its configured model was unavailable. Public-source verification continued directly; no agent findings are being claimed.

### Runtime dependencies and acquired-source archive — 2026-10-08

The user asked whether AI tools/models/agents remain necessary after development and requested retained copies of acquired documents.

- Development assistants (Copilot, coding agents, and development-time MCP tools) are not required to operate the deployed application.
- Runtime semantic ingestion and retrieval require an embedding model: local BGE-M3 is the default; configured external embedding APIs are optional and subject to organization consent.
- Generating new AI audit reports currently requires the configured Claude model/API and separate organization consent. There is no implemented local report-generation LLM replacement. Without Claude availability/consent, local ingestion/retrieval, deterministic scoring, and existing saved reports remain separate capabilities; new AI assessments cannot be generated.
- The database worker is an ordinary application process, not an autonomous AI agent. Keep it running for queued ingestion and reports. No separate agent platform is required by this architecture.
- The model cache must remain accessible to the deployed worker/API processes that perform local embeddings. A developer-machine download does not automatically make the model available on another deployment host.

**Acquired documents:** retained an original NIST CSF 2.0 OSCAL JSON catalog copy and upstream license under [docs/standards](docs/standards/README.md), with source commit, acquisition date, edition, and SHA-256 recorded. Verified the archive and application copies have identical hashes. This is a machine-readable catalog, not a publication PDF. No CIS/ISO official full text has been acquired. Future restricted material must remain in authorized, access-controlled storage rather than being committed to this archive without permission.

### Validation and change log

- **2026-10-08:** Created the original Phase 3 completion checklist from the plan.
- **2026-10-08:** Inspected the working tree and existing ingestion-related, embedding, retrieval, report, and worker code; confirmed substantial pre-existing uncommitted Phase 3 work.
- **2026-10-08:** Agreed on the seven-stage development workflow, Documents UI/API with text/Markdown uploads, queued shared standards, and local-plus-external embedding support with local processing by default.
- **2026-10-08:** Updated this document with decisions, rationale, exploration findings, and unresolved questions at the user's request.
- **Validation status:** no feature implementation or runtime test results yet. Documentation-only updates require no build or test run.

## Goal

Complete the AI audit and reporting pipeline: load standards and organization documents, retrieve supporting evidence with citations, generate validated Claude assessments, and deliver reliable reports.

## Recorded implementation progress

The plan records the following behavior as implemented:

- Report generation fails explicitly for missing Claude credentials, provider failures, and invalid output rather than returning a canned assessment. Failed generation must not be treated as an audit result.
- Structured-output validation requires scores and tiers to agree and all seven domains to appear exactly once.
- Reporting dates select currently active findings created within an inclusive UTC date range. Reversed ranges are rejected. Inventory counts reflect current inventory, not reconstructed historical inventory.
- Interrupted report jobs resume up to three times, then fail.
- Cancellation prevents a result from being saved, but does not abort an already-issued provider request.
- Report lists expose `overall_score` without including the full snapshot. An open running report refreshes until it reaches a terminal state.
- The October 6 fixes include regression coverage for report recovery/cancellation, severity ordering, structured output, reporting dates, and report-list/viewer behavior. The existing organization-change state reset also passed its regression test.

The Phase 3 checklist in the plan remains unchecked. Those checkboxes need reconciliation with implemented and verified behavior; they do not mean that every listed feature is unbuilt.

## Remaining completion requirements

### 1. Claude operational controls

- [x] Verify explicit timeouts and bounded retries for temporary provider errors.
- [x] Verify provider errors map to clear user-facing failure messages.
- [x] Complete per-organization limits and quotas (durable rolling-hour admission).
- [x] Record token usage and estimated cost per provider attempt in PostgreSQL.
- [x] Verify model output is validated before any AI score or report is saved.
- [x] Cover timeouts, rate limits, malformed output, and provider outages with mocked-provider tests.

Keep Claude calls centralized in [claude_service.py](backend/app/services/claude_service.py). Local development uses `ANTHROPIC_API_KEY` in the backend environment file; deployed authentication changes belong to Phase 4.

### 2. Standards and organization-document ingestion

- [ ] Load CIS, NIST, ISO, and organization documents through worker jobs.
- [ ] Chunk and embed document content.
- [ ] Preserve document source and version metadata.
- [ ] Ensure each organization can access only its own documents and shared standards.
- [ ] Verify ingestion job completion and failure behavior.

### 3. Retrieval and citations

- [ ] Verify retrieval uses only documents the organization is permitted to access.
- [ ] Preserve citations through assessment generation.
- [ ] Include citations in the API response and finished report.
- [ ] Verify citations identify the supporting source material.

### 4. Scoring and evidence provenance

- [ ] Retain rule-based scores separately from AI scores; AI scoring must not replace the rule-based result.
- [ ] Preserve the supporting evidence for the assessment.
- [ ] Record model identity, prompt version, and reporting period with the assessment.
- [ ] Verify saved scores and provenance remain consistent with the finished report.

### 5. Remediation recommendations

- [ ] Include recommendation priority.
- [ ] Identify affected assets and findings.
- [ ] Explain why the recommendation is needed.
- [ ] Include confidence.

### 6. Report snapshots, downloads, and retention

- [ ] Verify a finished report is an immutable snapshot.
- [ ] Provide HTML and PDF downloads.
- [ ] Restrict report access and downloads to authorized organization members.
- [x] Apply a configurable report-retention setting.
- [x] Verify retention and download behavior with automated tests.

### 7. Report job and API guarantees

- [x] Add organization-scoped idempotency for keyed generation requests, including concurrency tests.
- [ ] Verify worker queue integration, status transitions, failure details, and retries.
- [ ] Verify report lists are paginated and ordered newest first.
- [ ] Return full report content only through the report-by-ID endpoint, not list responses.
- [ ] Preserve and verify the recorded recovery and cancellation behavior.

## Historical gaps after the October 6 defect-fix pass

The October 6 notes explicitly exclude these unfinished requirements from that pass:

- Report-generation idempotency.
- Per-organization quotas and cost accounting.
- Document-ingestion jobs.
- Evidence provenance.
- Report retention and PDF export.

These describe the October 6 checkpoint, not current missing features. The later
document/evidence/report implementation and October 20 operational work supersede
this list. Remaining checklist entries require acceptance verification before
being classified as missing or signed off.

## Scope decision before sign-off

Remediation and HTML/PDF export appear in both the detailed Phase 3 checklist and the Phase 4 scope in [PLAN.md](PLAN.md).

Under the current detailed Phase 3 checklist, these are required for Phase 3 completion. If they are intended for Phase 4 instead, explicitly agree on that deferral and update both phase descriptions before sign-off. Do not silently treat them as completed or out of scope.

## Recommended implementation order

1. **Document ingestion, retrieval, and provenance:** complete the evidence pipeline and citation flow.
2. **Provider controls and job guarantees:** finish limits, usage/cost accounting, and report idempotency.
3. **Report deliverables:** complete remediation output, snapshot guarantees, exports, and retention, subject to the scope decision above.
4. **Acceptance and sign-off:** run targeted regression and end-to-end validation, reconcile the plan, and obtain sign-off.

## Phase 3a — Local and Claude report generation

**Decision (2026-10-08):** the user approved adding Phase 3a to support both local and Claude report providers with identical validation and evidence requirements. Start with one local runtime and one evaluated instruction-following model. This approves the scope, not a runtime/model, hardware purchase, implementation design, or live external evaluation calls.

**Status:** planned; not implemented. The existing local BGE-M3 embedding model does not generate reports. Phase 3a requires a separate generative model. The current Claude report consent gate remains unchanged until the provider-aware implementation is approved and tested.

### What to do now

1. Finish and verify the Phase 3 ingestion, retrieval, evidence-provenance, and consent foundation. It is still in progress; passing targeted tests does not establish full feature completion.
2. Assess the intended deployment host: operating system, CPU, available RAM, GPU/VRAM, free disk, expected concurrent users/jobs, languages, and acceptable report latency. A development workstation may differ from the production host.
3. Evaluate one practical runtime candidate (for example Ollama) and a compatible instruction-following model. Verify license, context window, structured-output support, quantization, installation size, and actual resource use. Do not assume CPU-only performance or model quality is adequate before measuring.
4. Follow the agreed seven-stage development workflow for Phase 3a: discovery, exploration, clarification, architecture approval, implementation, quality review, and summary. Set quality/performance acceptance thresholds before implementation/evaluation is signed off.

### Design requirements

- **Provider boundary:** introduce a report-generation interface with Claude and local implementations. Keep the existing centralized Claude adapter; do not scatter provider calls throughout the worker or API. Embedding-provider configuration remains independent.
- **Configuration and routing:** define who selects the report provider and default, and whether organizations can override it. Pin the chosen provider/model configuration on each queued job so a settings change cannot silently route queued evidence elsewhere. Version changes and retries must have explicit semantics.
- **Privacy and consent:** external Claude calls still require organization approval. Local mode must not depend on external-provider approval, send evidence externally, or silently fall back to Claude. Define administrator authority for local processing and disclose where it runs. A custom endpoint is not automatically local or trusted: restrict configured endpoints to approved infrastructure, prevent arbitrary outbound access, and protect network-accessible inference with authentication/network controls. Model download is a separate setup operation.
- **Common validation:** use the same output schema, score/tier checks, citation allowlist, evidence requirements, and rule-score separation for both providers. Reject invalid or fabricated output; do not substitute a canned report. Treat retrieved documents as untrusted evidence rather than instructions.
- **Context budget:** account for model token limits and output budget. Apply explicit, deterministic evidence selection and record omissions/sampling; do not silently truncate important evidence. If a multi-stage summarization design is needed, preserve its intermediate provenance and obtain design approval.
- **Provenance:** record provider, model identifier and immutable artifact/revision where available, quantization, runtime version, prompt/schema version, generation parameters, reporting period, captured evidence, and validation outcome. Keep finished snapshots readable if providers/models are later removed.
- **Worker behavior:** bound concurrency and output length; support timeout, cancellation, recovery, unavailable-runtime errors, and resource exhaustion. Distinguish stopping result publication from actually aborting generation. Retry against the job's approved configuration without switching providers.
- **Deployment:** document model provisioning, persistent model storage, service startup/health, CPU/GPU requirements, network restrictions, upgrade/reindex independence, and rollback. Loading a model on the developer machine does not provision production.

### Implementation checklist

- [ ] Approve hardware/workload requirements and acceptance thresholds.
- [ ] Approve one local runtime and one model artifact/quantization after license review.
- [ ] Refactor report generation behind a provider interface without weakening existing Claude checks.
- [ ] Add the local provider adapter and explicit configuration/readiness checks.
- [ ] Add provider-aware job configuration, consent/routing, and administration UI.
- [ ] Enforce common evidence/schema validation and provider-specific context budgets.
- [ ] Extend snapshots with provider/model/runtime provenance while preserving legacy reports.
- [ ] Add worker resource limits and provider-specific timeout/cancellation/recovery tests.
- [ ] Evaluate on a fixed, non-sensitive or synthetic evidence set; external comparisons require explicit approval.
- [ ] Publish installation/operations documentation and obtain sign-off.

### Acceptance criteria

- A local report can be generated from local evidence without outbound AI calls once model setup is complete.
- Claude remains functional under its approved consent and configuration; embedding and report-provider choices are independent.
- Both providers pass schema, domain completeness, score consistency, unsupported-citation rejection, and evidence-preservation tests.
- Rule-based scores remain deterministic and separate from AI assessments.
- Local unavailability, invalid output, resource exhaustion, timeout, and cancellation produce clear job outcomes, never external fallback or fabricated success.
- Provider/model changes cannot reroute an already queued job without explicit handling; revoked external consent prevents subsequent transmission.
- The evaluated model meets agreed quality, latency, memory, and concurrency thresholds on the intended host. Citation correctness alone is not proof of assessment quality; include human review of factual support and recommendations.
- Saved reports retain provider and evidence provenance and remain accessible after source/model changes.

### Open decisions

Target deployment hardware; runtime/model/quantization; provider default and selection permissions; local service topology; languages and context requirements; concurrency/latency goals; quality thresholds; and the approved evidence set for comparison. These require clarification/design approval, not assumptions.

## Phase 3b — OpenAI hosted report generation (future proposal)

**Request recorded (2026-10-08):** support customers who have an OpenAI API key but no Anthropic key. This is a future-stage documentation item only; it does not approve implementation, select a model, or change the current provider.

**Current behavior:** AI report generation is wired to Anthropic and requires `ANTHROPIC_API_KEY`. `OPENAI_API_KEY` is used by the embedding provider and does not route report generation to OpenAI. A customer with only an OpenAI key cannot currently generate AI reports; the rule-based test report is a separate, non-AI option.

### Proposed implementation requirements

- Add an OpenAI report-generation adapter behind the report-provider boundary planned for Phase 3a. Customers selecting OpenAI must not need an Anthropic key, and the OpenAI path must not invoke Anthropic.
- Keep report-provider settings (provider, report model, credentials) distinct from embedding-provider settings, even if they use the same `OPENAI_API_KEY` credential.
- Request structured output compatible with the existing audit snapshot schema. Apply the same domain-completeness, score/tier, citation-allowlist, evidence, and prompt-injection protections used by other report providers; validate before saving.
- Generalize report consent to identify the selected provider and model. OpenAI processing requires explicit organization approval, separate from embedding consent. A change of provider or model must not reuse consent for another target; queued reports must remain pinned to their approved provider/model.
- Store provider, model, prompt/schema version, captured evidence, and validation provenance in the report snapshot. Preserve readability of existing Anthropic and rule-based reports.
- Add tests for OpenAI-only configuration, missing OpenAI key, provider/API failures, invalid structured output, consent scoping and revocation, queued-job routing, provenance, and absence of Anthropic calls on the OpenAI path. Tests must mock provider requests and must not send real organization evidence to an external service.
- Document required OpenAI account/API access, model selection, cost implications, local secret configuration, and restart behavior. Never ask customers to disclose API keys in chat or commit them to source control.

### Scope and sequencing

1. Complete and verify the Phase 3 evidence, consent, and report-job foundation.
2. Design the shared report-provider boundary and provider-specific consent before implementation; coordinate with Phase 3a rather than creating a separate routing mechanism.
3. Confirm an OpenAI model and structured-output approach, API availability, quality criteria, and cost limits before selecting defaults.
4. Implement and test the adapter; keep Anthropic and local providers independently selectable and avoid silent cross-provider fallback.
5. Document the configuration and obtain review/sign-off before calling the feature complete.

**Status:** documented for a later stage; not implemented, model choice unresolved, and no external OpenAI requests approved.

## Final acceptance checklist

- [ ] Demonstrate the full flow: document ingestion and findings selection → retrieval → validated assessment → saved report → authorized download.
- [ ] Verify report citations and scoring provenance against the source evidence.
- [ ] Verify organization isolation for documents, retrieval, reports, and downloads.
- [ ] Verify provider failure, invalid output, cancellation, interrupted-job recovery, and duplicate-request behavior.
- [ ] Verify reporting-date semantics and preservation of existing rule-based scores.
- [ ] Run the smallest relevant existing test suites covering each change, followed by end-to-end acceptance validation.
- [ ] Reconcile implemented and verified work with the Phase 3 checkboxes in [PLAN.md](PLAN.md).
- [ ] Update directly related API, configuration, and user-facing documentation.
- [ ] Record any agreed Phase 4 deferrals explicitly.
- [ ] Obtain Phase 3 sign-off.
