#   AI-Powered Cyber Resilience Auditor – System Architecture

Review synchronization (2026-10-22): Runtime clarification: FastAPI/Python, PostgreSQL/pgvector and a separate worker are implemented; Node microservices, general automated discovery and standalone AI analysis routes below are design context, not current endpoints. Dashboard scoring is deterministic; AI runs through report jobs.
See [current code review and release gates](docs/RELEASE_READINESS.md).

29 October worker implementation: bounded threaded processing supports fair
admission across organizations, with one queued job per scope. Normal/demo
default remains **one slot**. SaaS scale work and parallel activation are on
hold; platform-admin configuration is required before future rollout. This is
not a distributed fleet or demonstrated SaaS capacity.
See [worker design, limitations and verification](docs/WORKER_POOL.md).

28 October 2026 local pilot: Dashboard scoring can additionally require current
reviewed evidence behind an organization-admin **default-off** setting. A durable
worker job evaluates complete inventory/source bindings; transactional database
revision triggers plus policy/expiry checks invalidate cached eligibility.
Dashboard reads do not run full inventory scans. Deterministic deductions/weights,
saved reports and independent `/risk/score` snapshots retain their contracts.
See [background evaluation and safe invalidation](docs/BACKGROUND_EVIDENCE_EVALUATION.md).

## Current release decision — 2026-10-21

Core Phase 3 keeps `/risk/score` and dashboard scores deterministic. Claude/RAG
assessments run through asynchronous reports, preserving the captured baseline
separately from AI output. Phase 3a local report generation is a separate delivery;
Phase 3b remains a future proposal. Approved shared tier boundaries are 80/60/40;
new AI assessments use the deterministic tier function. Prompt/schema v2 adds
model-estimated confidence and captured-evidence finding/asset UUID validation.
Legacy reports are not rewritten. See [Phase3.md](Phase3.md) for acceptance.

##  1. Overview

This document defines the full architecture for an AI-driven cyber resilience auditing platform. The system automates asset discovery, configuration analysis, vulnerability review, IAM assessment, backup validation, monitoring evaluation, incident readiness scoring, and report generation using Claude AI.

##  2. High-Level Architecture

### Components

Frontend (Web Application): Next.js/React interface for dashboards, reports, and configuration.

Backend API Layer: FastAPI/Python handling ingestion, scoring and orchestration, with a separate worker.

AI Layer (Claude): Reasoning engine for risk scoring, remediation guidance, and report generation.

Data Layer: PostgreSQL for structured data, vector database for RAG, object storage for logs and configs.

Integrations Layer: Connectors for cloud platforms, identity providers, scanners, SIEM, and backup systems.

### Architecture Flow

Connectors ingest infrastructure data.

Backend normalizes and stores data.

AI layer performs reasoning using structured inputs and RAG.

Risk scores and reports are generated.

Frontend displays results and insights.

##  3. Data Model

### Core Tables

organizations: Company metadata.

users: Authenticated users and roles.

assets: Servers, endpoints, cloud resources, network devices.

findings: Vulnerabilities, misconfigurations, IAM issues.

scans: Scan jobs and ingestion events.

risk_scores: Per-domain and overall resilience scores.

reports: Generated audit reports.

documents: Standards and configs stored for RAG.

##  4. API Design

### Authentication

POST /auth/login

GET /orgs/:orgId/users

### Asset & Scan Management

GET /orgs/:orgId/assets

Proposed only: POST /orgs/:orgId/assets/discover (not a current live discovery endpoint)

POST /orgs/:orgId/scans

### Findings & Risk

GET /orgs/:orgId/findings

POST /orgs/:orgId/risk/score

### Reports

POST /orgs/:orgId/reports/generate

GET /orgs/:orgId/reports/:reportId

### Proposed AI Operations (not runtime endpoints)

POST /ai/analyze-config

POST /ai/generate-report

POST /ai/risk-score

Current implementation uses organization-scoped asynchronous report jobs instead.
Runtime paths carry the `/api/v1` prefix; the separate administrator-only Claude
smoke endpoint is `/api/v1/ai/claude/test`, not a report generation workflow.

##  5. AI Reasoning Workflow

### Inputs

Asset inventory

Findings across domains

Standards retrieved via RAG

### Process

Normalize inputs into structured JSON.

Retrieve relevant CIS/NIST/ISO sections.

Claude evaluates each resilience domain.

Assigns scores and generates remediation steps.

Produces executive and technical report sections.

### Outputs

Domain-level scores

Overall resilience score

Remediation roadmap

Full audit report

##  6. Data Ingestion Pipeline

### Stages

Collection: Cloud APIs, AD/Azure AD, scanners, SIEM, backup systems.

Normalization: Unified asset and finding schema.

Storage: PostgreSQL for structured data, vector DB for documents.

Indexing: Standards and configs embedded for RAG.

##  7. Risk Scoring Model

### Dimensions

Identity & Access

Network & Configuration

Vulnerability Management

Backup & Recovery

Monitoring & Detection

Incident Response

Compliance Alignment

### Scoring

Each dimension scored 0–100.

Weighted average produces overall score.

Risk tiers: Low, Medium, High, Critical.

##  8. UI Wireframes (Conceptual)

### Dashboard

Overall resilience score

Domain radar chart

Top critical issues

### Assets View

Asset list with risk indicators

Filters by severity and domain

### Findings View

Grouped findings with AI explanations

Remediation suggestions

### Reports

List of generated reports

PDF/HTML export

### Integrations

Cloud, SIEM, scanner configuration

AI settings

##  9. Development Roadmap (4 Weeks)

### Week 1

Repo setup, CI/CD, basic frontend and backend

Database schema

Authentication

Claude API integration

### Week 2

Asset and findings ingestion

Basic risk scoring

Dashboard UI

### Week 3

RAG setup

AI-driven scoring and reporting

Report UI

### Week 4

Domain scoring refinement

Remediation generation

PDF/HTML export

Security hardening

##  10. MVP Feature Set

### Must-Have

Org and user management

Asset and findings ingestion

AI risk scoring

AI-generated audit report

Dashboard and findings views

RAG with standards

### Nice-to-Have

Multiple connectors

IR scenario generator

Compliance mapping

Multi-tenant SaaS

##  11. Claude Integration Notes

Use structured prompts for consistent scoring.

RAG enhances accuracy for standards-based evaluation.

AI outputs must be validated before report generation.

##  12. Security Considerations

OAuth2/SSO authentication

Role-based access control

Encryption in transit and at rest

Audit logging

Secure connector credentials storage

## 13. Future Enhancements

Automated red-team simulation

Continuous monitoring mode

ML-based anomaly detection

Compliance automation modules

This architecture provides a complete foundation for building an AI-powered cyber resilience auditing platform using Claude as the reasoning engine.
