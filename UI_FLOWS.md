# UI Flows – AI Cyber Resilience Auditor

## 1. Overview
Describes key user journeys and screens in the web application.

---

## 2. Main Flows

### 2.1 Onboarding Flow
1. User signs up or is invited.
2. Selects or creates organization.
3. Configures basic settings (timezone, industry).
4. Guided setup to add first connectors (cloud, IAM, scanner).

### 2.2 Connector Setup Flow
1. Navigate to **Settings → Integrations**.
2. Choose connector type (AWS, Azure AD, Nessus, etc.).
3. Enter credentials and scope.
4. Test connection.
5. Save and trigger initial discovery.

### 2.3 Discovery & Scan Flow
1. Go to **Assets** page.
2. Click **Run Discovery** or **Import Scan Results**.
3. Select scope (all, environment, tags).
4. Monitor progress via **Scans** status.
5. Assets and findings populate tables.

### 2.4 Risk Assessment Flow
1. Navigate to **Dashboard**.
2. Click **Run AI Risk Assessment**.
3. Backend aggregates data and calls Claude.
4. User sees updated scores and risk tiers.
5. Drill down into each domain for details.

### 2.5 Report Generation Flow
1. Go to **Reports**.
2. Click **Generate New Report**.
3. Choose period and scope.
4. Claude generates executive + technical sections.
5. User reviews, edits if needed, and exports PDF/HTML.

### 2.6 Findings Remediation Flow
1. Open **Findings** page.
2. Filter by severity/domain.
3. Click a finding to view AI explanation and remediation.
4. Mark as accepted, in-progress, or resolved.
5. Changes reflected in future risk assessments.

---

## 3. Key Screens

### 3.1 Dashboard
- Overall resilience score.
- Domain scores (radar chart).
- Top 5 critical issues.
- Recent scans and connector status.

### 3.2 Assets
- Table: asset type, environment, criticality, risk score.
- Filters: type, environment, domain, severity.

### 3.3 Findings
- Grouped by domain.
- Columns: severity, asset, description, AI explanation, remediation.

### 3.4 Reports
- List of reports with status and date.
- View report details.
- Export options.

### 3.5 Settings / Integrations
- Connector list with status.
- Add/edit connector forms.
- AI settings (Claude API key, RAG options).

---

## 4. Roles & Permissions (UI)
- **Admin:** full access, connector management, org settings.
- **Auditor:** run scans, risk assessments, generate reports.
- **Viewer:** read-only access to dashboard, findings, reports.
