# Connectors Specification – AI Cyber Resilience Auditor

## 1. Overview
Defines connectors used to ingest data from external systems.

---

## 2. Connector Types

### 2.1 Identity Providers
- **Targets:** AD, Azure AD, Okta.
- **Data:** Users, groups, roles, MFA status, login policies.
- **Endpoints:** Graph APIs / LDAP / SCIM.
- **Frequency:** Daily or on-demand.

### 2.2 Cloud Platforms
- **Targets:** AWS, Azure, GCP.
- **Data:** Instances, security groups, IAM policies, storage, load balancers.
- **Mechanism:** SDKs / REST APIs with read-only roles.
- **Frequency:** Scheduled discovery + on-demand.

### 2.3 Vulnerability Scanners
- **Targets:** Nessus, Qualys, OpenVAS.
- **Data:** Scan results, CVEs, severities, affected assets.
- **Mechanism:** Export APIs (JSON/CSV) or direct integration.
- **Frequency:** After each scan.

### 2.4 SIEM / Logging
- **Targets:** Splunk, Sentinel, QRadar, Elastic.
- **Data:** Log sources, alert statistics, coverage metrics.
- **Mechanism:** REST APIs / search queries.
- **Frequency:** Daily summaries.

### 2.5 Backup Systems
- **Targets:** Veeam, Commvault, cloud-native backups.
- **Data:** Job status, schedules, RPO/RTO, immutability flags.
- **Mechanism:** Vendor APIs.
- **Frequency:** Daily.

---

## 3. Connector Design

### 3.1 Common Pattern
- **Auth:** API keys, OAuth, service principals.
- **Output:** Normalized JSON mapped to `assets`, `findings`, `scans`.
- **Error Handling:** Retries, logging, connector health status.

### 3.2 Security
- Least-privilege access.
- Secrets stored in secure vault.
- Audit logs for connector operations.

---

## 4. Configuration UI
- Per-connector setup page.
- Fields: endpoint, credentials, schedule, scope.
- Status indicators: Connected, Error, Last sync time.

---

## 5. Extensibility
- New connectors follow same interface:
  - `discover_assets()`
  - `fetch_findings()`
  - `fetch_metadata()`
