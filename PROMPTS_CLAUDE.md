# Claude Prompt Design – AI Cyber Resilience Auditor

Review synchronization (2026-10-22): Examples below are design/history. Runtime audit-evidence-v3 adds explicit input budgets/omission disclosures while retaining schema version 2 domain/tier/citation/UUID validation. Optional OpenRouter changes transport, not the accepted report contract. See [budget/closure contract](docs/PHASE3_CLOSURE.md).
See [current code review and release gates](docs/RELEASE_READINESS.md).

## Current report contract — 2026-10-22

Examples below are historical design guidance, not the runtime JSON contract.
The authoritative structured schema is `backend/app/schemas/report_ai.py` and the
runtime prompt is in `backend/app/services/report_ai_service.py` (version
`audit-evidence-v3`). AI and deterministic scores are separate but share tiers:
Low 80–100, Medium 60–79, High 40–59, Critical 0–39.

New AI remediations contain bounded numeric `confidence` (model-estimated support,
not a calibrated probability), `affected_finding_ids`, and `affected_asset_ids`.
Only captured finding IDs and assets attached to the action's referenced findings
are allowed. General guidance and assetless findings may have empty lists with
limitations disclosed; never invent references. Citation IDs must also belong to
the retrieved set. The v2 target requires renewed administrator consent. Saved
legacy snapshots are not reinterpreted or rewritten.

## 1. Overview
Defines system and task prompts used with Claude for scoring, analysis, and reporting.

---

## 2. System Prompt (Global)

> You are a senior cyber resilience auditor.  
> You evaluate organizations using NIST CSF, CIS Benchmarks, and ISO 27001.  
> Your tasks:  
> - Assess identity, network, vulnerability, backup, monitoring, incident response, and compliance.  
> - Assign scores (0–100) per domain and overall.  
> - Explain risks in clear language.  
> - Provide prioritized remediation steps.

---

## 3. Risk Scoring Prompt

**Input JSON:**
- `assets`, `findings`, `controls`, `standards_snippets`

**User Prompt:**

> Using the provided data and standards, calculate resilience scores for each domain and overall.  
> 1. List assumptions.  
> 2. For each domain, give: score (0–100), tier, and justification.  
> 3. Provide top 10 remediation actions, ordered by impact.  
> 4. Output strictly in JSON with keys: `domains`, `overall`, `remediation`.

---

## 4. Config Analysis Prompt

> You are analyzing configuration files and security policies.  
> Compare them against CIS Benchmarks and NIST guidance.  
> Identify misconfigurations, missing controls, and risky defaults.  
> For each issue, provide: `description`, `impact`, `recommended_fix`, `related_standard`.

---

## 5. Report Generation Prompt

**Input:**
- Scores, findings, remediation list, org metadata.

> Generate a cyber resilience audit report with:  
> - Executive summary (non-technical).  
> - Domain-by-domain analysis.  
> - Risk tier explanation.  
> - Prioritized remediation roadmap.  
> Use headings and bullet points. Avoid jargon where possible.

---

## 6. IR Readiness Prompt

> Evaluate the incident response plan and related artifacts.  
> Score readiness from 0–100.  
> Identify gaps in detection, escalation, communication, and recovery.  
> Suggest 5–10 concrete improvements.

---

## 7. RAG Integration
- Pre-attach relevant standards snippets to the prompt.
- Claude is instructed to cite which standard section influenced each recommendation (e.g., “NIST CSF PR.AC-1”).
