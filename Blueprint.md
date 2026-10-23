# System architecture diagram (text blueprint)

Review synchronization (2026-10-22): The diagram includes proposed OAuth/SSO, connector and standalone AI routes. These are not a runtime API inventory. Use asynchronous report jobs for AI; dashboard scoring stays deterministic.
See [current code review and release gates](docs/RELEASE_READINESS.md).

Current release decision (2026-10-21): this document's original Claude-backed
`/risk/score` examples are superseded. That endpoint and dashboard scoring remain
deterministic; Claude/RAG assessments run as report jobs and retain a separate
rule-based baseline. Phase 3a local report generation ships separately. Shared
80/60/40 tier boundaries are implemented for new assessments; remediation
confidence and captured-evidence finding/asset UUIDs use the v2 report contract.
Old reports retain their saved values.
See [Phase3.md](Phase3.md) for release gates and implementation status.
## Layers:

### Client (UI):

        Web app (Next.js/React)

        Auth via OAuth2/SSO

### Backend API (Service Layer):

        FastAPI/Node.js

        Services: asset-service, scan-service, risk-service, report-service, auth-service

### AI Layer (Claude):

        Prompt orchestration service

        RAG pipeline (vector DB + standards docs)

        Risk scoring + report generation

### Data Layer:

        PostgreSQL (assets, findings, users, orgs)

        Vector DB (Qdrant/Pinecone) for CIS/NIST/ISO docs + configs

        Object storage (S3) for logs, configs, exports

### Integrations:

        Connectors to AD/Azure AD, AWS/Azure/GCP, Nessus/Qualys, SIEM, EDR/XDR, firewalls

# Database schema (high level)
## Tables:

### organizations

        id, name, industry, created_at

### users

        id, org_id, email, role, auth_provider

### assets

        id, org_id, type, hostname, ip, cloud_id, criticality

### scans

        id, org_id, scan_type, status, started_at, completed_at

### findings

        id, scan_id, asset_id, category, severity, description, source (Nessus, config, IAM, etc.)

### risk_scores

        id, org_id, asset_id, score, dimension (identity, network, backup, IR, compliance)

### reports

        id, org_id, title, period_start, period_end, status, generated_at

### documents (for RAG)

        id, org_id (nullable for global standards), type, source, vector_id

# API endpoints (examples)
## Auth & org:

### POST /auth/login

### GET /orgs/:orgId

### GET /orgs/:orgId/users

## Assets & scans:

### GET /orgs/:orgId/assets

### POST /orgs/:orgId/assets/discover

### GET /orgs/:orgId/scans

### POST /orgs/:orgId/scans (body: scan_type, scope)

## Findings & risk:

### GET /orgs/:orgId/findings

### GET /orgs/:orgId/assets/:assetId/findings

### POST /orgs/:orgId/risk/score (deterministic; no Claude call)

## Reports:

### POST /orgs/:orgId/reports/generate

### GET /orgs/:orgId/reports/:reportId

## AI/RAG:

### Proposed only: POST /ai/claude/analyze-config (not implemented)

### Proposed only: POST /ai/claude/generate-report (use organization report jobs instead)

### Proposed only: POST /ai/claude/risk-score (not implemented)

# AI reasoning workflow (Claude)
## Inputs:

### Asset inventory

### Findings (vulns, misconfigs, IAM issues, backup status, logging coverage)

### Standards snippets (CIS/NIST/ISO) via RAG

## Steps:

1.   Normalize: Claude receives structured JSON of assets + findings.

2.   Context build: System prompt defines role: “Cyber resilience auditor following NIST CSF, CIS, ISO 27001.”

3.  RAG: Retrieve relevant standards sections and attach to prompt.

4.  Reason:

    Evaluate each domain (asset mgmt, IAM, vuln mgmt, backup, IR, monitoring, compliance).

    Assign risk scores (e.g., 0–100) per domain + overall.

## Output:

    Risk scores

    Explanations

    Remediation steps

    Executive summary + technical appendix

#   Data ingestion pipeline
##  Stages:

### Connectors:

    AD/Azure AD → users, groups, roles

    Cloud APIs → instances, security groups, IAM policies

    Scanners → vulnerabilities

    SIEM → logging sources, alert stats

    Backup systems → job status, RPO/RTO

### ETL:

    Normalize to common asset + finding schema

### Deduplicate assets

    Tag criticality (e.g., based on labels, environment)

### Storage:

    Write to PostgreSQL (assets, findings, scans)

    Index configs/docs into vector DB for RAG

# Risk scoring model (simple first version)
## Dimensions:

### Identity & Access

### Network & Config Hardening

### Vulnerability Management

### Backup & Recovery

### Monitoring & Detection

### Incident Response Readiness

### Compliance Alignment

## Inputs:

### Counts of high/critical findings per dimension

### Presence/absence of key controls (MFA, EDR, immutable backups, IR plan, etc.)

### Claude’s qualitative assessment

## Output:

### Per‑dimension score:[0,100]

### Overall score: weighted average

### Risk tier: Low, Medium, High, Critical

Claude’s prompt can include a scoring rubric and ask it to justify each score.

# UI wireframes (conceptual)
## Screens:

### Dashboard:

    Overall resilience score

    Per‑domain scores (radar chart)

    Top 5 critical issues

### Assets view:

Table of assets with risk score, type, environment

Filters by severity, domain

### Findings view:

Grouped by domain (IAM, network, backup, etc.)

Each finding with “AI explanation” and “AI remediation”

### Reports:

List of generated reports

Download PDF/HTML

“Generate new audit” button

###  Settings / Integrations:

Connectors configuration (cloud, SIEM, scanners)

Claude API key & RAG settings

# 4‑week development roadmap (MVP)
## Week 1 – Foundations

Setup: repo, CI/CD, basic Next.js + backend (FastAPI/Node)

DB: create core tables (orgs, users, assets, findings, reports)

Auth: basic login, org selection

Claude integration: simple endpoint to call Claude with a test prompt

## Week 2 – Ingestion & basic risk

Connectors (MVP):

Import assets via CSV/JSON upload

Manual findings upload (e.g., Nessus export)

Risk scoring v0:

Simple rule‑based scoring from counts of findings

UI: dashboard with assets + basic scores

## Week 3 – AI audit & reporting

RAG setup:

Load CIS/NIST/ISO docs into vector DB

AI workflows:

Endpoint: /orgs/:orgId/risk/score using Claude + RAG

Endpoint: /orgs/:orgId/reports/generate for full audit report

UI: report view with executive summary + findings

## Week 4 – Polish & resilience focus

Domains: finalize per‑domain scoring (IAM, backup, IR, etc.)

Remediation suggestions: Claude generates step‑by‑step fixes per finding

Export: PDF/HTML report export

Hardening: auth, roles, basic logging

# MVP feature list
## Must‑have:

### Org + user management

### Asset + findings ingestion (manual + at least one connector)

### Claude‑powered risk scoring per domain

### Claude‑generated audit report (exec + technical)

### Dashboard with scores + top issues

### Basic RAG with standards docs

## Nice‑to‑have (post‑MVP):

### Multiple connectors (cloud, SIEM, scanners)

### Tabletop IR scenario generator

### Compliance mapping (ISO 27001, SOC 2, NIST CSF)

### Multi‑tenant SaaS with billing
