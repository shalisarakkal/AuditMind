// Mirrors of the backend schemas (backend/app/schemas, backend/app/models/enums.py).

export type Domain =
  | "identity_access"
  | "network_config"
  | "vulnerability_management"
  | "backup_recovery"
  | "monitoring_detection"
  | "incident_response"
  | "compliance_alignment";

export type Severity = "critical" | "high" | "medium" | "low";
export type RiskTier = "low" | "medium" | "high" | "critical";
export type UserRole = "admin" | "auditor" | "viewer";
export type ScanStatus = "pending" | "running" | "completed" | "failed";

export type Token = { access_token: string; token_type: string };

export type Organization = {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  created_at: string;
};

export type MyOrganization = Organization & { role: UserRole };

export type Asset = {
  id: string;
  org_id: string;
  type: string;
  hostname: string | null;
  ip: string | null;
  cloud_id: string | null;
  environment: string | null;
  criticality: string | null;
  tags: string[] | null;
  created_at: string;
};

export type Finding = {
  id: string;
  org_id: string;
  asset_id: string | null;
  scan_id: string | null;
  category: string | null;
  domain: Domain;
  severity: Severity;
  description: string | null;
  source: string | null;
  created_at: string;
};

export type RowError = { row: number; message: string };

export type ImportReport = {
  created: number;
  updated: number;
  skipped: number;
  duplicates: number;
  failed: number;
  errors: RowError[];
};

export type ImportResponse = {
  scan_id: string;
  status: ScanStatus;
  report: ImportReport | null;
};

export type Scan = {
  id: string;
  org_id: string;
  scan_type: string;
  scope: string | null;
  status: ScanStatus;
  started_at: string | null;
  completed_at: string | null;
  source: string | null;
  filename: string | null;
  // An ImportReport for file imports, or {error} if the import crashed.
  summary: (Partial<ImportReport> & { error?: string }) | null;
};

export type DomainScore = { domain: Domain; score: number; tier: RiskTier; justification: string };

export type DashboardSummary = {
  overall_score: number;
  overall_tier: RiskTier;
  domains: DomainScore[];
  top_findings: Finding[];
  recent_scans: Scan[];
  asset_count: number;
  findings_by_severity: Record<Severity, number>;
};

export type AssetExistingStrategy = "update" | "skip" | "duplicate";
export type NessusInfoSeverity = "skip" | "low";

export type IngestionSettings = {
  import_partial_success: boolean;
  asset_existing_strategy: AssetExistingStrategy;
  nessus_info_severity: NessusInfoSeverity;
  nessus_domain_map: Record<string, Domain>;
  nessus_default_domain: Domain;
  overridden: string[];
  nessus_domain_map_override: Record<string, Domain>;
};
