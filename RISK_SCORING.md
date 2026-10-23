# Risk scoring: implemented contract

Reviewed 22 October 2026. See [release readiness](docs/RELEASE_READINESS.md).

`POST /api/v1/orgs/{org_id}/risk/score` records deterministic score history. It
does not call Claude or depend on AI consent/RAG. Dashboard scoring is separate
from AI report assessments.

For each domain, active findings produce:

`score = max(0, 100 - 15*critical - 7*high - 3*medium - low)`

| Domain | Overall weight |
| --- | --- |
| Identity and access | 20% |
| Network and configuration | 15% |
| Vulnerability management | 15% |
| Backup and recovery | 15% |
| Monitoring and detection | 15% |
| Incident response | 10% |
| Compliance alignment | 10% |

Overall score is the weighted average. Shared tiers: Low >=80, Medium >=60,
High >=40, otherwise Critical. No findings yields 100, not proof of security.
Asset criticality, exposure, missing controls and narrative maturity are not
independent deductions in this version; they matter only through normalized findings.

AI reports assess captured evidence separately and validate seven domains,
tiers, citations and remediation UUID references. They retain the rule baseline
without overwriting it. Confidence is model-estimated, not calibrated probability.
Dates select currently active findings created within inclusive UTC dates;
inventory is current, not reconstructed historical inventory. API dates exist;
the browser dialog lacks date selection. Legacy report snapshots are not rewritten.

Sources: `backend/app/services/scoring_service.py`,
`backend/app/core/assessment_contract.py`, `backend/app/services/report_ai_service.py`.
