# Data Model – AI Cyber Resilience Auditor

## 1. Overview
This document defines the core data entities and relationships for the cyber resilience auditing platform.

---

## 2. Entities

### 2.1 organizations
- **Fields:** `id`, `name`, `industry`, `size`, `created_at`
- **Purpose:** Represents a customer/company.

### 2.2 users
- **Fields:** `id`, `email`, `name`, `auth_provider`, `created_at`
- **Relations:** many-to-many with `organizations` via `org_memberships` (2.9)
- **Purpose:** Application users (admins, auditors, viewers). Role is per org, on the membership.

### 2.3 assets
- **Fields:** `id`, `org_id`, `type`, `hostname`, `ip`, `cloud_id`, `environment`, `criticality`, `tags`, `created_at`
- **Purpose:** Any infrastructure component (server, VM, DB, device, SaaS).

### 2.4 scans
- **Fields:** `id`, `org_id`, `scan_type`, `scope`, `status`, `started_at`, `completed_at`, `source`
- **Purpose:** Logical scan/ingestion events (vuln scan, config import, IAM review).

### 2.5 findings
- **Fields:** `id`, `scan_id`, `org_id`, `asset_id`, `category`, `domain`, `severity`, `description`, `raw_data`, `source`, `created_at`
- **Relations:** `scan_id → scans.id`, `asset_id → assets.id`
- **Purpose:** Individual issues (vulns, misconfigs, IAM risks, backup gaps).

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
