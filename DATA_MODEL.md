# Data Model – AI Cyber Resilience Auditor

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

### 2.5 findings
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
