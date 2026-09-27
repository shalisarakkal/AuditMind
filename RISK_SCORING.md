# Risk Scoring Model – AI Cyber Resilience Auditor

## 1. Overview
Defines how the platform calculates cyber resilience scores per domain and overall.

---

## 2. Scoring Dimensions
- **Identity & Access**
- **Network & Configuration**
- **Vulnerability Management**
- **Backup & Recovery**
- **Monitoring & Detection**
- **Incident Response**
- **Compliance Alignment**

Each dimension gets a score in 

\[0, 100].

---

## 3. Inputs

### 3.1 Quantitative
- Count of findings by severity (Critical/High/Medium/Low).
- Presence/absence of key controls (MFA, EDR, immutable backups, IR plan, SIEM coverage).
- Asset criticality and exposure.

### 3.2 Qualitative (Claude)
- Narrative assessment of control maturity.
- Contextual risk (e.g., exposed internet-facing assets).
- Alignment with standards (CIS/NIST/ISO).

---

## 4. Scoring Logic (v1)

### 4.1 Base Score
Start each dimension at 100.

### 4.2 Deductions
- Critical findings: subtract 10–20 each (capped).
- High findings: subtract 5–10 each (capped).
- Missing key control: subtract 10–25 depending on importance.
- Poor maturity (Claude judgment): subtract 10–30.

### 4.3 Floor
Minimum dimension score: 0.

---

## 5. Overall Score
- Weighted average of dimension scores.
- Example weights:
  - Identity & Access: 20%
  - Network & Config: 15%
  - Vulnerability Mgmt: 15%
  - Backup & Recovery: 15%
  - Monitoring & Detection: 15%
  - Incident Response: 10%
  - Compliance Alignment: 10%

---

## 6. Risk Tiers
- **Low:** 80–100
- **Medium:** 60–79
- **High:** 40–59
- **Critical:** 0–39

---

## 7. Claude Prompt Guidance
Claude receives:
- Structured JSON of findings and controls.
- Scoring rubric.
- Asked to:
  - Propose dimension scores.
  - Justify deductions.
  - Suggest remediation to move to next tier.
