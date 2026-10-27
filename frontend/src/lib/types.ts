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
export type ReportStatus = "pending" | "running" | "completed" | "generated" | "failed";

export type ReportFacets = {
  status: ReportStatus[];
  frameworks: string[];
};

export type DomainScoreAI = {
  evidence_status?: "sufficient" | "limited" | "insufficient" | "conflicting";
  evidence_reason?: string;
  evidence_finding_ids?: string[];
  citation_ids?: string[];
  domain: Domain;
  score: number | null;
  tier: RiskTier | null;
  justification: string;
  strengths: string[];
  weaknesses: string[];
};

export type RemediationActionAI = {
  citation_ids?: string[];
  title: string;
  description: string;
  priority: "Critical" | "High" | "Medium" | "Low";
  domain: Domain;
  estimated_effort: "Quick Win" | "Moderate" | "Major Project" | string;
  expected_impact: string;
  related_controls: string[];
  affected_asset_types: string[];
  // Optional for retained reports generated before the v2 assessment contract.
  confidence?: number | null;
  affected_finding_ids?: string[];
  affected_asset_ids?: string[];
};

export type ComplianceCitation = {
  citation_id?: string;
  version_id?: string;
  source?: string;
  content_kind?: string;
  content_hash?: string;
  control_id: string;
  framework: string;
  version?: string;
  title: string;
  content: string;
  content_ref?: string;
  distance?: number;
};

export type AuditReportSnapshot = {
  assessment_status?: "complete" | "partial";
  provenance?: {
    schema_version?: number;
    model?: string; prompt_version?: string; prompt_hash?: string; captured_at?: string;
    period_semantics?: string; evidence_limitation?: string | null; sample_limit?: number;
    assessment_type?: "rule_based_test" | string;
    method?: string; version?: string; external_processing?: boolean;
    framework_evaluation?: string;
    rule_based?: { overall_score: number; overall_tier: string };
    sampled_findings?: { finding_id: string; description: string; severity: string }[];
  };
  title: string;
  executive_summary: string;
  overall_score: number | null;
  overall_tier: RiskTier | null;
  resilience_summary: string;
  domains: DomainScoreAI[];
  remediations: RemediationActionAI[];
  compliance_citations: ComplianceCitation[];
  total_assets: number;
  total_findings: number;
  findings_by_severity: Record<string, number>;
  frameworks_evaluated: string[];
};

export type AuditReport = {
  assessment_status?: "complete" | "partial" | null;
  id: string;
  org_id: string;
  title: string;
  assessment_type?: string | null;
  period_start: string | null;
  period_end: string | null;
  frameworks: string | null;
  status: ReportStatus;
  generated_at: string | null;
  format: string | null;
  location: string | null;
  error_message: string | null;
  started_by: string | null;
  created_at: string;
  overall_score?: number | null;
  data?: AuditReportSnapshot | null;
};


export type Token = {
  access_token: string;
  token_type: string;
  /** Seconds the access token lasts. */
  expires_in: number;
  /** Every page but Change password is refused until it's changed. */
  must_change_password: boolean;
};

/** The signed-in user (GET /auth/me). */
export type Me = {
  id: string;
  email: string;
  name: string | null;
  is_sysadmin: boolean;
  must_change_password: boolean;
  password_expires_at: string | null;
};

/** What a new password must meet (GET /auth/password-rules). */
export type PasswordRules = {
  rule: "simple" | "complex";
  min_length: number;
  max_length: number;
  require_upper: boolean;
  require_lower: boolean;
  require_digit: boolean;
  require_symbol: boolean;
  history_count: number;
  /** 0: never expires. */
  expiry_days: number;
  /** Setting -> the org that asks for its stricter value. */
  required_by: Record<string, string>;
};

export type Organization = {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  created_at: string;
};

export type MyOrganization = Organization & {
  /** What the user may do here. Viewer for the Sysadmin (reading an org it
   * doesn't belong to) and, in the app, in an archived org (AppContext). */
  role: UserRole;
  /** "sysadmin": the Sysadmin reading an org it doesn't belong to. */
  access?: "member" | "sysadmin";
  /** Read-only for everyone until the Sysadmin restores it. */
  archived?: boolean;
  /** Their role as a member, when `role` was lowered (an archived org). */
  member_role?: UserRole;
};

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
  /** In the assets list: its archive hasn't finished, and that archive. */
  archiving?: ArchiveProgress | null;
  archiving_batch_id?: string | null;
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
  /** An event log's finding: how many events it sums up, and when. */
  event_count?: number | null;
  first_seen?: string | null;
  last_seen?: string | null;
  details?: EventDetails | null;
};

/** What an event log's finding keeps about its events (backend event_sources.py). */
export type EventDetails = {
  rule?: string;
  actors?: { distinct: string; top: { value: string; events: number }[] };
  scopes?: { name: string; distinct: string; top: { value: string; events: number }[] };
  examples?: Record<string, unknown>[];
};

/** A finding in the org's paged list, with its asset's name. */
export type FindingListItem = Finding & {
  due_timezone?: string | null;
  due_expires_at?: string | null;
  risk_review_timezone?: string | null;
  risk_review_expires_at?: string | null;
  workflow_status?: import("./findingWorkflow").WorkflowStatus;
  workflow_version?: number;
  assignee_id?: string | null;
  assignee_label?: string | null;
  due_date?: string | null;
  risk_review_date?: string | null;
  asset_hostname: string | null;
  asset_ip: string | null;
  /** A cloud resource may be known only by this. */
  asset_cloud_id: string | null;
  /** A manual finding whose archive hasn't finished, and that archive. */
  archiving?: ArchiveProgress | null;
  archiving_batch_id?: string | null;
};

/** One page of a list, and how many items match across all pages. */
export type Page<T> = { items: T[]; total: number };

/** The values each pick-list filter can offer; "" stands for "no value". */
export type AssetFacets = { type: string[]; subtype: string[]; environment: string[]; criticality: string[] };
export type FindingFacets = { source: string[]; has_manual_findings?: boolean; workflow_status?: import("./findingWorkflow").WorkflowStatus[]; assignee?: { value: string; label: string }[] };

export type FindingPage = Page<FindingListItem> & {
  /** Findings per domain for the same search, whatever the domain filter. */
  domain_counts: Partial<Record<Domain, number>>;
};

export type RowError = { row: number; message: string };
/** Imported, but worth checking (same shape as RowError). */
export type RowWarning = RowError;
/** A row left out on purpose (skipped, or a duplicate): what it was and why. */
export type RowNote = { row: number; item: string; message: string };

/** For profile imports, created/updated/skipped count assets and
 * findings_created/duplicates count findings. */
export type ImportReport = {
  created: number;
  /** Assets already in the inventory, updated (each once). */
  updated: number;
  skipped: number;
  /** Rows naming an asset an earlier row of the file named (absent before
   * 2026-10-01, when these were counted as updated). */
  repeated?: number;
  duplicates: number;
  failed: number;
  findings_created: number;
  errors: RowError[];
  warnings: RowWarning[];
  /** All warnings; the list holds at most the first 1,000. */
  warnings_total?: number;
  /** The first 1,000 rows counted in skipped and duplicates, with why
   * (uploads before 2026-09-30 have none). */
  skipped_rows?: RowNote[];
  duplicate_rows?: RowNote[];
};

export type ImportResponse = {
  scan_id: string;
  status: ScanStatus;
  report: ImportReport | null;
  skipped?: boolean;
  skip_reason?: string | null;
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
  /** The uploader: only they see the import's report, until they dismiss it. */
  started_by: string | null;
  dismissed_at: string | null;
  progress: ImportProgress | null;
  /** Set while the background worker runs it (it checks in every ~15 s). */
  heartbeat_at?: string | null;
  /** Failed, but can run again from its kept file (Retry). */
  retryable?: boolean;
};

/** A running import's progress, stage by stage: reading (checking) the file's
 * rows, waiting for another import into the org, writing its rows, writing a
 * tool export's findings, saving. Counts are 0 (or absent) where there are none. */
export type ImportProgress = {
  phase: "reading" | "waiting" | "writing" | "findings" | "saving";
  rows_done?: number;
  rows_total?: number;
};

export type DomainScore = { domain: Domain; score: number | null; tier: RiskTier | null; assessment_status?: "not_assessed" | "findings_based"; justification: string };

export type DashboardSummary = {
  overall_score: number | null;
  overall_tier: RiskTier | null;
  assessment_status?: "not_assessed" | "findings_based";
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
  exact_duplicate_file_policy: "ask" | "skip" | "reimport";
  nessus_info_severity: NessusInfoSeverity;
  nessus_domain_map: Record<string, Domain>;
  nessus_default_domain: Domain;
  overridden: string[];
  nessus_domain_map_override: Record<string, Domain>;
  asset_type_aliases: Record<string, AssetType>;
  asset_type_aliases_override: Record<string, AssetType>;
  /** Days an archived item is kept before it's purged automatically. */
  archive_retention_days: number;
  /** Days Activity events are kept. */
  event_retention_days: number;
};

export type Criticality = "info" | "warning" | "critical";

/** One entry in Activity: what happened, to what, by whom, when. */
export type ActivityEvent = {
  id: string;
  type: string;
  item: string | null;
  /** Null: the system (or an unknown person, for a failed sign-in). */
  actor_id: string | null;
  actor_label: string;
  started_at: string;
  ended_at: string;
  outcome: "completed" | "failed" | "stopped";
  criticality: Criticality;
  counts: Record<string, number> | null;
  details: Record<string, unknown> | null;
};

/** The choices Activity's pick-lists offer. */
export type EventFacets = { type: string[]; result: string[] };

export type WorkerStatus = { running: boolean; last_seen: string | null };

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
  /** An event log: its events are summed up by rules into findings (no
   * assets, no host column needed). */
  events?: boolean;
  rules?: EventRule[];
  /** Field -> column header in the file. */
  column_map: Record<string, string>;
  params: ProfileParams;
  created_at: string | null;
  updated_at: string | null;
};

export type ArchiveItemType = "upload" | "asset" | "finding";
export type ArchiveState = "archiving" | "archived" | "restoring" | "restored" | "purging" | "purged";
export type ArchiveAction = "archive" | "restore" | "purge";
/** An archive that hasn't finished: a job runs now, or one stopped part-way. */
export type ArchiveProgress = "running" | "stopped";

/** Rows per table: archived, restored or purged. */
export type ArchiveCounts = { uploads?: number; assets?: number; findings?: number };

/** Archiving, restoring or purging one item; followed like an import. */
export type ArchiveJob = {
  id: string;
  org_id: string;
  batch_id: string;
  action: ArchiveAction;
  status: ScanStatus;
  item_type: ArchiveItemType;
  item_id: string;
  label: string;
  started_by: string | null;
  started_at: string;
  completed_at: string | null;
  dismissed_at: string | null;
  progress: { phase: string; rows_done?: number; rows_total?: number } | null;
  /** Set while the background worker runs it (it checks in every ~15 s). */
  heartbeat_at?: string | null;
  /** The rows done; on restore also duplicates_purged and
   * findings_kept_with_asset (their asset is archived separately); or {error}. */
  summary: (ArchiveCounts & { duplicates_purged?: number; findings_kept_with_asset?: number; error?: string }) | null;
};

/** One archive action on the Archived page. */
/** Several items archived, restored or purged at once: a job each (queued),
 * and those that couldn't start, with why. */
export type BulkResult = { jobs: ArchiveJob[]; refused: { id: string; detail: string }[] };

/** The Archived list, with how many of each type match the other filters. */
export type ArchivedPage = Page<ArchivedItem> & { type_counts: Partial<Record<ArchiveItemType, number>> };

export type ArchivedItem = {
  id: string;
  item_type: ArchiveItemType;
  item_id: string;
  label: string;
  /** restoring / purging: a job runs now (`running`) or one stopped part-way. */
  state: ArchiveState;
  /** What a job is doing to it right now. */
  running: ArchiveAction | null;
  archived_at: string;
  archived_by: string | null;
  purge_at: string;
  counts: ArchiveCounts;
};

/** An upload on the Imports page (its report without the row lists). */
export type Upload = Scan & {
  uploaded_by: string | null;
  /** Its archive hasn't finished, and that archive. */
  archiving?: ArchiveProgress | null;
  archiving_batch_id?: string | null;
};

/** The body of a 409 for a file already imported into the org. */
export type RepeatUpload = { message: string; imported_at: string | null; imported_by: string };

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
  /** An event log's rules as the profile changes them. */
  rules?: Record<string, { enabled?: boolean; severity?: Severity | null }>;
};

/** One of an event log source's rules, with its defaults. */
export type EventRule = { key: string; title: string; domain: Domain; severity: Severity; min_events: number };

/** A person's state (backend services/people.py). */
export type MemberStatus = "active" | "locked" | "must_change_password" | "deactivated";

/** A member of the org, as People lists them (GET /orgs/{id}/members). */
export type Member = {
  id: string;
  email: string;
  name: string | null;
  auth_provider: string;
  created_at: string;
  role: UserRole;
  added_at: string;
  status: MemberStatus;
  /** Locked until then; null while locked: until an admin unlocks it. */
  locked_until: string | null;
  /** Their temporary password works until then. */
  temp_password_expires_at: string | null;
  /** Also in other orgs: their name and password are the Sysadmin's to change. */
  in_other_orgs: boolean;
};

/** POST /orgs/{id}/members: the temporary password, shown once, for a new account. */
export type MemberAdded = Member & { temporary_password: string | null };

/** POST /orgs/{id}/members/{user}/reset-password, shown once. */
export type PasswordReset = { temporary_password: string; expires_at: string };

export type MemberFacets = { role: string[]; status: string[] };

/** One layer's security settings (backend services/security_policy.py). */
export type SecuritySettings = {
  idle_minutes: number;
  max_session_days: number;
  lockout_threshold: number;
  lockout_window_minutes: number;
  lock_minutes: number;
  password_rule: "simple" | "complex";
  min_length: number;
  require_upper: boolean;
  require_lower: boolean;
  require_digit: boolean;
  require_symbol: boolean;
  history_count: number;
  expiry_days: number;
};

/** GET /platform/security, GET /orgs/{id}/security. */
export type SecuritySettingsLayer = {
  values: SecuritySettings;
  /** The settings this layer changes; the rest follow `below`. */
  changed: (keyof SecuritySettings)[];
  /** Built-in values under the platform's; the platform's under an org's. */
  below: SecuritySettings;
};

export type OrgStatus = "active" | "archived" | "purging";

/** An organization in the Platform section (GET /platform/orgs). */
export type PlatformOrg = {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  created_at: string;
  status: OrgStatus;
  archived_at: string | null;
  members: number;
  admins: string[];
};

export type PlatformOrgCreated = PlatformOrg & {
  temporary_password: string | null;
  temp_password_expires_at: string | null;
};

/** An account in the Platform section (GET /platform/users). */
export type PlatformUser = {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
  status: MemberStatus;
  is_sysadmin: boolean;
  locked_until: string | null;
  temp_password_expires_at: string | null;
  orgs: { org_id: string; name: string; role: UserRole }[];
};

/** One of the user's open sign-ins (GET /auth/sessions). */
export type SignInSession = {
  id: string;
  signed_in_at: string;
  last_active_at: string;
  ip: string | null;
  /** "Chrome on Windows". */
  browser: string | null;
  /** This browser. */
  current: boolean;
};
