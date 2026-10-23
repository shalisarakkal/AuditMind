# MASTER PROMPT FOR CLAUDE (Copy & Paste)

Review synchronization (2026-10-22): Historical/design record: original dates, results and proposals are preserved. This is not fresh test evidence or current release sign-off.
See [current code review and release gates](docs/RELEASE_READINESS.md).
Project: AuditMind AI — an intelligent auditing, risk‑scoring, and compliance automation platform.

## Brand Assets:  
We have 5 completed logos: Neural Shield, Audit Eye, Mind Grid, Hex Sentinel, Infinity Audit Loop.
We also have a brand presentation sheet with color palette, typography, and usage guidelines.

## Your Tasks (Claude): Produce all development artifacts
### 1. System Architecture
Create a complete system architecture for AuditMind AI including:

Frontend (web app)

Backend (API + services)

AI reasoning engine

Data ingestion pipeline

Database

Authentication & RBAC

Logging & monitoring

Deployment (AWS or Azure)

### 2. Database Schema
Generate a full relational schema with tables for:

Users

Roles & permissions

Audits

Audit items

Risk scores

Evidence uploads

Activity logs

AI reasoning outputs
Include keys, relationships, and field definitions.

### 3. REST API Endpoints
List all endpoints with:

Method

Path

Request body

Response body

Auth requirements

Error codes
Include endpoints for audits, scoring, reporting, user management, and data ingestion.

### 4. AI Reasoning Workflow
Define the full AI pipeline:

Input format

Preprocessing

Model reasoning steps

Scoring logic

Feedback loop

Output structure

Error handling

Human‑in‑the‑loop review

### 5. Data Ingestion Pipeline
Design ingestion for:

Structured data (CSV, JSON, DB exports)

Unstructured data (PDF, text, logs)

Real‑time streams
Include validation, normalization, and storage flow.

### 6. Risk Scoring Model
Define:

Parameters

Weights

Thresholds

Scoring formula

Confidence metrics

Output JSON schema

### 7. UI/UX Wireframes
Create wireframes for:

Dashboard

Audit detail page

Risk visualization

Evidence upload

Settings & user management

IMPORTANT — UI COLOR SCHEME REQUIREMENT
Use our brand colors in all UI recommendations:

Deep Navy (#0A1A2F) — backgrounds, panels

Electric Cyan (#00C8FF) — highlights, buttons, accents

White (#FFFFFF) — text, contrast

Navy→Cyan gradient — charts, hero elements
All UI components must visually match the AuditMind AI logos.

### 8. Development Roadmap
Create a 4‑week sprint plan with milestones for:

Backend

Frontend

AI engine

Database

Deployment

Testing

### 9. MVP Feature List
List core features required for the first release.

### 10. Integration Diagram
Show how all modules connect:
API ↔ AI Engine ↔ UI ↔ Database ↔ Ingestion Pipeline.

Output Format
Provide each section clearly labeled and structured.
Use diagrams (ASCII or structured text), tables, and bullet lists.
