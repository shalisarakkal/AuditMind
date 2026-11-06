export type Declaration = {
  snapshot_kind: string; tool_name: string; tool_instance_id: string; tool_configuration_id: string;
  targets: string[]; exclusions: string[]; unreachable_targets: string[]; coverage_confirmed: boolean;
  source_snapshot_at: string | null;
};
export type SnapshotView = {
  scan: { id: string; filename: string | null; scan_type: string; profile: string | null; status: string;
    completed_at: string | null; ingestion_config_fingerprint: string | null };
  declaration: { id: string; version: number; state: string; declaration: Declaration;
    rationale: string; actor_label: string; created_at: string } | null;
  declaration_blockers: string[]; complete_blockers: string[];
};
export type Comparison = {
  reviewed_at: string; baseline: SnapshotView; current: SnapshotView; declared_metadata_matches: boolean;
  absence_eligible: false; blocking_reasons: string[]; absence_blockers: string[];
  scope_differences: Record<string, string[]>; not_observed_finding_ids: null;
};
const labels: Record<string, string> = {
  scan_not_successfully_completed: "Import has not completed successfully",
  captured_import_configuration_unavailable: "Captured import configuration is unavailable; reimport to capture it",
  verified_import_report_unavailable: "Verified import report is unavailable",
  organization_archive_operation_in_progress: "An archive, restore or purge operation is pending, running or incomplete",
  import_has_errors_skips_or_warnings: "Import contains errors, skipped items or warnings",
  declaration_revoked: "Declaration was revoked",
  source_snapshot_not_complete: "Source snapshot is not confirmed complete",
  unreachable_targets: "Some targets were unreachable",
  scan_context_changed: "Scan metadata changed after declaration",
  tool_name_changed: "Tool names differ", tool_instance_id_changed: "Tool instances differ",
  tool_configuration_id_changed: "Declared tool configurations differ",
  scan_type_changed: "Import types differ", profile_changed: "Import profiles differ", source_changed: "Import sources differ",
  ingestion_config_fingerprint_changed: "Captured parser or import configurations differ",
  target_scope_changed: "Target scopes differ", scope_exclusions_changed: "Scope exclusions differ",
  source_snapshot_time_unavailable: "Source snapshot time is not provided",
  current_source_snapshot_is_not_newer: "Current source snapshot must be newer than the baseline",
  stable_finding_identity_and_reconciliation_not_enabled: "Stable finding identity verification and reconciliation are not enabled",
};
export function snapshotReason(value: string): string {
  const [side, reason] = value.includes(":") ? value.split(":") : ["", value];
  return `${side ? `${side === "baseline" ? "Baseline" : "Current"}: ` : ""}${labels[reason] || reason.replaceAll("_", " ")}`;
}
export const snapshotKinds = ["complete", "partial", "incremental", "failed", "cancelled"];
export const snapshotKindLabel = (kind: string) => kind.charAt(0).toUpperCase() + kind.slice(1);

export function sourceTimeInput(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${String(date.getFullYear()).padStart(4, "0")}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
