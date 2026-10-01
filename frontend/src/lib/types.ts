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
};

/** A finding in the org's paged list, with its asset's name. */
export type FindingListItem = Finding & {
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
export type FindingFacets = { source: string[] };

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
  updated: number;
  skipped: number;
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
};
