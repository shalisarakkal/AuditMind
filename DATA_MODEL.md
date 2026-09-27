# Data Model – AI Cyber Resilience Auditor

## 1. Overview
This document defines the core data entities and relationships for the cyber resilience auditing platform.

---

## 2. Entities

### 2.1 organizations
- **Fields:** `id`, `name`, `industry`, `size`, `ingestion_overrides`, `created_at`
- **Purpose:** Represents a customer/company.
- **`ingestion_overrides`** (JSONB, default `{}`): the org's overrides of the global ingestion defaults in `.env` (`import_partial_success`, `asset_existing_strategy`, `nessus_info_severity`, `nessus_domain_map`, `nessus_default_domain`). Only overridden keys are stored, so a changed `.env` default still applies to orgs that haven't overridden it. Read/changed via `GET`/`PATCH /orgs/{org_id}/settings`.

### 2.2 users
- **Fields:** `id`, `email`, `name`, `auth_provider`, `created_at`
- **Relations:** many-to-many with `organizations` via `org_memberships` (2.9)
- **Purpose:** Application users (admins, auditors, viewers). Role is per org, on the membership.

### 2.3 assets
- **Fields:** `id`, `org_id`, `type`, `hostname`, `ip`, `cloud_id`, `environment`, `criticality`, `tags`, `created_at`
- **Purpose:** Any infrastructure component (server, VM, DB, device, SaaS).
- **Import matching:** imported assets and findings' hosts match an existing asset by hostname (case-insensitive), else by IP (only against assets with no hostname). Indexed on `(org_id, lower(hostname))` and `(org_id, ip)`. No uniqueness constraint: the `duplicate` import strategy may create repeats.

### 2.4 scans
- **Fields:** `id`, `org_id`, `scan_type`, `scope`, `status`, `started_at`, `completed_at`, `source`, `filename`, `summary`
- **Purpose:** Logical scan/ingestion events (vuln scan, config import, IAM review). Every file import is recorded as a scan: `scan_type` `asset_import` / `findings_csv` / `findings_json` / `nessus`, `source` `upload`, `filename` the uploaded file, and `summary` (JSONB) the import report (created/updated/skipped/duplicates/failed + row errors). `status` goes `pending` → `running` → `completed`/`failed`; large imports run in the background and are polled through it.

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

### 2.8 documents
- **Fields:** `id`, `org_id` (nullable), `type`, `source`, `title`, `content_ref`, `vector_id`, `created_at`
- **Purpose:** Standards (CIS/NIST/ISO), policies, configs for RAG.

### 2.9 org_memberships
- **Fields:** `user_id`, `org_id` (composite primary key), `role` (`admin` | `auditor` | `viewer`), `created_at`
- **Relations:** `user_id → users.id`, `org_id → organizations.id`
- **Purpose:** Which orgs a user can access, and their role in each. Drives org selection: the client lists the user's orgs and scopes every call to the one picked (`/orgs/{org_id}/...`).

---

## 3. Domains (for findings & risk_scores)
- **identity_access**
- **network_config**
- **vulnerability_management**
- **backup_recovery**
- **monitoring_detection**
- **incident_response**
- **compliance_alignment**
