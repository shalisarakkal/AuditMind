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
  /** The source's own name for the type, e.g. "laptop" for a workstation. */
  subtype: string | null;
  hostname: string | null;
  ip: string | null;
  cloud_id: string | null;
  environment: string | null;
  criticality: string | null;
  tags: string[] | null;
  /** Extra facts from profile imports (OS, open ports, agent version...). */
  details: Record<string, unknown>;
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
/** Imported, but worth checking (same shape as RowError). */
export type RowWarning = RowError;

/** For profile imports, created/updated/skipped count assets and
 * findings_created/duplicates count findings. */
export type ImportReport = {
  created: number;
  updated: number;
  skipped: number;
  duplicates: number;
  failed: number;
  findings_created: number;
  errors: RowError[];
  warnings: RowWarning[];
  /** All warnings; the list holds at most the first 1,000. */
  warnings_total?: number;
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
  /** The import profile a file was read with (built-in key or custom id). */
  profile: string | null;
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
  asset_type_aliases: Record<string, AssetType>;
  asset_type_aliases_override: Record<string, AssetType>;
};

export type AssetType = "server" | "workstation" | "network_device" | "database" | "cloud_resource" | "application";

export type ProfileField = { name: string; label: string; detail: boolean };

/** A built-in import profile (key = its family) or one of the org's copies
 * (key = its id). */
export type ImportProfile = {
  key: string;
  name: string;
  family: string;
  family_label: string;
  builtin: boolean;
  creates_assets: boolean;
  creates_findings: boolean;
  fields: ProfileField[];
  /** Field -> column header in the file. */
  column_map: Record<string, string>;
  params: ProfileParams;
  created_at: string | null;
  updated_at: string | null;
};

export type RiskyPort = { label: string; severity: Severity };

/** Every family's settings; the family-specific ones are only present for
 * that family. */
export type ProfileParams = {
  default_values: Record<string, string>;
  type_aliases: Record<string, AssetType>;
  keep_other_columns: boolean;
  threats_high_at?: number;
  threats_critical_at?: number;
  stale_after_days?: number;
  compliance_severity?: Record<string, Severity>;
  compliant_values?: string[];
  day_first_dates?: boolean;
  risk_critical_at?: number;
  risk_high_at?: number;
  risk_medium_at?: number;
  vulnerability_domains?: Record<string, Domain>;
  no_vulnerability_values?: string[];
  risky_ports?: Record<string, RiskyPort>;
  disabled_values?: string[];
  disabled_severity?: Severity;
  ok_values?: string[];
  stale_login_days?: number;
  stale_severity?: Severity;
};
