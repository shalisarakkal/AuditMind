# Data Model – AI Cyber Resilience Auditor

## Reviewed imported-finding disposition (0050)

`finding_suppressions` owns a versioned identity-scoped registry and minimal
current source context/label. `finding_suppression_decisions` is an attributed,
append-only application ledger with organization/request idempotency and a
composite tenant ownership foreign key. Historical finding/observation UUIDs
have no source-row cascading ownership. Actor deletion nulls only actor links;
organization deletion removes its registry/history.

`findings.suppression_id` independently controls active visibility;
`suppression_history_id` preserves prior review/restore protection after clearing.
Both reference the registry with deferred no-action constraints: a retained
source prevents accidental registry deletion, while organization cascades can
remove the entire graph without intermediate visibility updates. Active Findings
partial indexes include both archive and suppression predicates.

`finding_suppression_reappearances` retains possible source/native-material
matches without authorizing suppression or copying a trusted identity binding.
`organization_suppression_revisions` fences saved Dashboard captures. Disposition,
ledger/activity, list/evidence revision and coalesced Dashboard invalidation
commit atomically. [Contract and delivery evidence](docs/SUPPRESSION_RELEASE_REVIEW.md).


Dashboard evidence pilot (migrations 0029–0031): `organization_scoring_settings`
holds a default-false enablement flag and expected version;
`domain_evidence_qualifications` holds one source-/inventory-bound versioned review
per organization/domain. `evidence_evaluations` holds durable worker lifecycle,
progress and structured eligibility results; a partial unique index allows one
pending/running job per organization. `organization_evidence_revisions` stores a
transactionally incremented bigint per organization, maintained by statement-level
triggers over material inputs. Cached eligibility is valid only at that revision,
current policy/evaluator identity and unexpired review window. Scores themselves
remain live deterministic calculations. Downgrading 0031 disables enabled scoring
settings before dropping its job/revision structures. See
[the exact contract](docs/BACKGROUND_EVIDENCE_EVALUATION.md); models/Alembic govern
actual columns rather than the conceptual entities below.

Migration 0024 adds nine search indexes, not data columns: six pg_trgm GIN indexes
(finding description/category/source, asset hostname/IP/cloud ID), an active
assignee index and two sparse active deadline-search indexes. Concurrent creation,
extension prerequisites and measured costs: [search operations](docs/FINDING_SEARCH_PERFORMANCE.md).

Opt-in evidence-aware schema3 retains explicit domain evidence status/reason and
finding references, nullable AI scores/tiers, and server-owned complete/partial
assessment status with qualification/aggregation provenance. Provider contract
cannot supply overall/provenance fields. Existing schema1/2 JSONB reports are not
rewritten. No new SQL table/column is introduced; see
[coverage workflow](docs/EVIDENCE_COVERAGE_PROFILES.md).

Prompt-v3 snapshots retain `provenance.input_budget` (policy/limits, actual input
bytes, sampling and omitted IDs) and per-finding `text_limits` (original/included
byte counts and original SHA-256). Source rows are unchanged; schema version 2
remains compatible. See [budget contract](docs/PHASE3_CLOSURE.md#budget-contract).

Review synchronization (2026-10-22): This is a conceptual summary, not a complete schema dump. SQLAlchemy models and Alembic 0021 govern exact columns. Reports retain JSONB evidence/provenance and queued processing-target pins; keyed organization idempotency and the separate ai_usage ledger are implemented. Versioned knowledge documents/chunks/index jobs supersede legacy vector_id sketches.
See [current code review and release gates](docs/RELEASE_READINESS.md).

## 1. Overview
This document defines the core data entities and relationships for the cyber resilience auditing platform.

---

## 2. Entities

### 2.1 organizations
- **Fields:** `id`, `name`, `industry`, `size`, `ingestion_overrides`, `created_at`
- **Purpose:** Represents a customer/company.
- **`ingestion_overrides`** (JSONB, default `{}`): the org's overrides of the global ingestion defaults in `.env` (`import_partial_success`, `asset_existing_strategy`, `nessus_info_severity`, `nessus_domain_map`, `nessus_default_domain`, `asset_type_aliases`). Only overridden keys are stored, so a changed `.env` default still applies to orgs that haven't overridden it. Read/changed via `GET`/`PATCH /orgs/{org_id}/settings`.

### 2.2 users
- **Fields:** `id`, `email`, `name`, `auth_provider`, `created_at`
- **Relations:** many-to-many with `organizations` via `org_memberships` (2.9)
- **Purpose:** Application users (admins, auditors, viewers). Role is per org, on the membership.

### 2.3 assets
- **Fields:** `id`, `org_id`, `type`, `subtype`, `type_known`, `hostname`, `ip`, `cloud_id`, `environment`, `criticality`, `tags`, `details`, `created_at`
- **Purpose:** Any infrastructure component (server, VM, DB, device, SaaS).
- **`type`** is one of `server`, `workstation`, `network_device`, `database`, `cloud_resource`, `application`. Imports and `POST /assets` also accept a known name for one (e.g. laptop → workstation, VM → server, Lambda/bucket → cloud_resource); the name list is built in, extended by `.env` `ASSET_TYPE_ALIASES` and the org's `asset_type_aliases` setting (and a profile's own names). **`subtype`** keeps the source's name (`laptop`, `Lambda`, an OS such as `Windows Server 2022`).
- **`details`** (JSONB, default `{}`): extra facts from profile imports (endpoint ID, agent version, last heartbeat, OS, open ports, region). Merged, not replaced, on re-import, so facts from different tools accumulate.
- **Identity:** every asset needs a hostname, an IP or a `cloud_id` (cloud resources are often known only by their ID).
- **Import matching:** imported assets and findings' hosts match an existing asset by `cloud_id` (exact), else hostname (case-insensitive) and category, else IP (only against assets with no hostname). A row with a cloud ID matches by name or IP only an asset with no cloud ID of its own. By name or IP, a row whose category is known matches only an asset of that category or one whose type is a guess, so a server and a router sharing a name stay two assets (the import report warns). A row with no known category (a finding, an endpoint agent's default type) matches any; with several candidates it goes to the oldest and the report warns.
- **`type_known`** is false when the type is a guess: a profile's default type (endpoint agents default to workstation), a type worked out from an unrecognised or blank OS (recorded as server), or the placeholder for a finding's unknown host. A known type from a later import replaces a guess; a guess never replaces a known type. Indexed on `(org_id, cloud_id)`, `(org_id, lower(hostname))` and `(org_id, ip)`. No uniqueness constraint: the `duplicate` import strategy may create repeats.

### 2.4 scans
- **Fields:** `id`, `org_id`, `scan_type`, `scope`, `status`, `started_at`, `completed_at`, `source`, `filename`, `summary`
- **Purpose:** Logical scan/ingestion events (vuln scan, config import, IAM review). Every file import is recorded as a scan: `scan_type` `asset_import` / `findings_csv` / `findings_json` / `nessus`, or `<family>_import` for a profile import (e.g. `endpoint_agent_import`), `source` `upload`, `filename` the uploaded file, `profile` the import profile used (built-in key or the org's profile id), and `summary` (JSONB) the import report (created/updated/skipped/duplicates/failed/findings_created + row errors and warnings; for profile imports the first three count assets). `status` goes `pending` → `running` → `completed`/`failed`; large imports run in the background and are polled through it.

Migration `0041` adds a nullable importer-owned configuration fingerprint on
**scans** and **scan_snapshot_declarations**, an append-only versioned record of
operator-declared source scope/completeness, tool instance/configuration, server
scan context, attribution and rationale. The latest version can be revoked or
superseded. Scan purge removes its declarations. Metadata comparisons return no
absence facts and do not affect finding observations/workflow/scores.
[Contract](docs/SCAN_SNAPSHOTS.md).

Migrations `0043`/`0044` add durable abort intent and internal publication
connection/transaction identity on **scans**. Cancellation matches PID, backend
start, transaction start and transaction ID before interrupting SQL; terminal
publication clears these fields. Aborted imports use failed status plus an
explicit aborted summary, retain the uploaded file under the failed-file policy,
and never resume automatically. Abort attribution is recorded in Activity.

### 2.5 findings

Migration `0042` adds **organization_workflow_revisions**. Findings list cache
and cursor stamps combine source/inventory and workflow revisions, allowing
workflow-only edits to invalidate lists without waiting for an import's counter
row. Selected findings use non-key row locks compatible with observation foreign
keys; archive admission, permissions and optimistic versions remain fenced.

Migration `0040` adds **finding_observations**, an append-only application history
of accepted finding occurrences, including duplicates. Each row links org/finding,
retains an immutable import UUID plus nullable live scan link, records parser,
source row/occurrence, filename, recording/source time, asset/source identifiers
and imported payload. No historical backfill or stable identity is inferred;
current reconciliation eligibility is false with reasons. Purging the finding
cascades to observations; deleting a duplicate-only scan nulls its live link and
retains the import UUID. [Full contract](docs/FINDING_OBSERVATIONS.md).
- **Fields:** `id`, `scan_id`, `org_id`, `asset_id`, `category`, `domain`, `severity`, `description`, `raw_data`, `source`, `created_at`
- **Relations:** `scan_id → scans.id`, `asset_id → assets.id`
- **Purpose:** Individual issues (vulns, misconfigs, IAM risks, backup gaps).
- **Imports:** `raw_data` keeps the original row (or Nessus ReportItem). A finding is a duplicate, and skipped on import, if one already exists for the same asset, `source` and `category` (Nessus: plugin ID + port); without a category, the description stands in.

### 2.6 risk_scores
- **Fields:** `id`, `org_id`, `asset_id` (nullable), `dimension`, `score`, `tier`, `justification`, `created_at`
- **Purpose:** Per-domain and overall resilience scores.

### 2.7 reports
- **Fields:** `id`, `org_id`, `title`, `period_start`, `period_end`, `status`, `generated_at`, `format`, `location`
- **Purpose:** Generated audit reports.
- **Snapshots:** `data` is a retained JSON snapshot, not regenerated on read.
  Assessment schema v2 records the AI score separately from the captured rule
  baseline in provenance, prompt/rubric versions, and remediation confidence plus
  `affected_finding_ids` / `affected_asset_ids`. References are validated against
  captured finding/asset evidence before persistence. Confidence is model-estimated
  support, not a calibrated probability. Older reports may omit these fields;
  their saved scores and tiers are preserved. See [operations](docs/PHASE3_OPERATIONS.md).
  `provenance.evidence_capture` records capture isolation, attempt count and
  database-clock timestamps; `provenance.inventory` preserves the captured total
  and asset-category counts. These describe one repeatable-read evidence view,
  not the inventory at the reporting period's historical endpoint.

### 2.8 documents
- **Legacy fields:** `id`, `org_id` (nullable), `type`, `source`, `title`, `content`, `content_ref`, `framework`, `control_id`, `version`, `embedding` (1536-dimensional vector), `created_at`.
- **Purpose:** Legacy document storage, not the complete versioned knowledge schema. Current ingestion/retrieval uses knowledge documents, versions, chunks, index jobs, embedding profiles and usage records. Migration/model definitions govern those entities; local BGE-M3 profiles use 1024 dimensions independently of the legacy vector column.

### 2.9 org_memberships
- **Fields:** `user_id`, `org_id` (composite primary key), `role` (`admin` | `auditor` | `viewer`), `created_at`
- **Relations:** `user_id → users.id`, `org_id → organizations.id`
- **Purpose:** Which orgs a user can access, and their role in each. Drives org selection: the client lists the user's orgs and scopes every call to the one picked (`/orgs/{org_id}/...`).

### 2.10 import_profiles
- **Fields:** `id`, `org_id`, `name` (unique per org), `family`, `column_map` (JSONB), `params` (JSONB), `created_at`, `updated_at`
- **Relations:** `org_id → organizations.id` (deleted with the org)
- **Purpose:** An org's own copy of a built-in import profile. `family` picks the code that reads the file (`generic_assets`, `generic_findings`, `endpoint_agent`, `network_scan`, `cloud_inventory`, `directory`); `column_map` gives the file's column for each field, with alternative names separated by `|` (the first one the file has is read); `params` holds that family's rule settings (thresholds, maps, default values, type names), validated on save. The built-in profiles themselves live in code (`app/services/import_profiles.py`), not in this table. Findings from a profile import have `source` = the family, so an org's copy and the built-in dedup against each other.

---

## 3. Domains (for findings & risk_scores)
- **identity_access**
- **network_config**
- **vulnerability_management**
- **backup_recovery**
- **monitoring_detection**
- **incident_response**
- **compliance_alignment**

## 12 November 2026: PB-1.3 read-only foundation

Migration `0051` adds retained consolidation/decision ledgers and bounded read APIs.
An administrator-only preview validates current pair prerequisites in a read-only
snapshot. No consolidation writes, visibility changes or new UI actions are enabled.
Current membership/dependencies, proof, lifecycle and consumer integration remain
pending before publication. Validation and API details: [foundation review](docs/CONSOLIDATION_FOUNDATION_REVIEW.md).

Membership/dependency follow-up: `0052` reserves tenant/generation-scoped member
and retained source-reference tables. Read-only previews include bounded dependency
counts and a diagnostic fingerprint. No writer, visibility integration or lifecycle
guard is enabled. All 90 PostgreSQL regression tests passed; migration parity and
the high-severity security gate passed. Local activation is tracked in the foundation review.

Strong pre-commit review (12 November): full backend 1,820 passed; final affected
suite 49 passed; frontend 578 passed; Chrome workflow 103 checks passed; isolated
build/TypeScript/lint and security gates passed. Review fixed preview pool
exhaustion, malformed manifest admission and excessive-offset validation. See
the consolidation foundation review for overlapping scopes and performance limits.
The foundation remains read-only; hosted CI must pass for the pushed checkpoint.


## Migration 0053: internal consolidation visibility (not activated)

Findings gain nullable `consolidation_id` (current group),
`consolidation_alias_id` (hidden alias only) and `consolidation_history_id`
(retained history marker). Each has a deferred composite `(org_id, group_id)`
foreign key to `finding_consolidations` and a tenant-leading partial index.
The alias check requires matching non-null current/history links. Undo clears
current/alias links, preserving history. Source/observation/workflow ownership
is unchanged. `Finding.active()` also requires a null alias link; 28 matching
partial indexes are rebuilt by the migration.

`organization_consolidation_revisions` stores one monotonic bigint revision per
organization. Visibility and revision/cache invalidation share the caller's
transaction; undo increments rather than resets the revision. Positive revisions
also prevent destructive schema downgrade after source cleanup.

Production publication remains disabled. The normal application database is
still at the preceding schema for this increment; coordinated activation is
required. See [visibility contract and rollout](docs/CONSOLIDATION_VISIBILITY.md).


## Migrations 0054?0055: group proof and separate opt-in

`0054` installs `am_consolidation_hash_v1(text)` and
`am_consolidation_proof_v1(org_id, group_id)`. The bounded current-source digest
runs only for grouped approved candidates; the shared approval ledger stores
`attestation.group_context` (contract/group version/member IDs/count/digest).
No source payload or workflow is copied. The migration also adds
`ix_finding_observations_source_asset` on organization, source-asset JSON text
and finding ID, plus an organization/scan/finding index, for targeted lifecycle probes.

`0055` adds `organization_consolidation_settings`: organization UUID primary key
with organization-cascade ownership, non-null enabled flag default False and
integer version default 0. Disabling does not clear existing memberships.
These migrations are not activated on the normal application database. See
[Stage A contract](docs/CONSOLIDATION_RELEASE_REVIEW.md).
