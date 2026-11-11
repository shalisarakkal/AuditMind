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
export type ReviewCandidate = {
  finding_id: string; baseline_observation_id: string; reviewable_baseline_observation_count: number;
  asset_id: string | null; description: string | null; category: string | null; domain: string;
  severity: string; workflow_status: string; workflow_version: number; baseline_recorded_at: string;
};
export type Comparison = {
  reviewed_at: string; baseline: SnapshotView; current: SnapshotView; declared_metadata_matches: boolean;
  absence_eligible: boolean; blocking_reasons: string[]; absence_blockers: string[];
  scope_differences: Record<string, string[]>; review_candidates: ReviewCandidate[];
  candidate_count: number; candidate_offset: number; candidate_limit: number;
  baseline_reviewable_observations: number; current_reviewable_observations: number;
  baseline_unreviewable_observations: number; current_unreviewable_observations: number;
  ambiguous_baseline_identity_count: number;
  review_token: string | null; review_queue_batch_id: string | null; review_queue_item_count: number;
};
export type AbsenceReviewQueueItem = {
  id: string; batch_id: string; candidate: ReviewCandidate; comparison: {
    reviewed_at: string; baseline: { scan: Pick<SnapshotView["scan"], "id" | "filename"> };
    current: { scan: Pick<SnapshotView["scan"], "id" | "filename"> };
    identity_review_fingerprint: string;
  };
  state: "pending" | "kept_active"; decision_version: number;
  rationale: string | null; actor_label: string | null; decided_at: string | null; created_at: string;
};
export type AbsenceReviewQueuePage = {
  items: AbsenceReviewQueueItem[]; total: number; limit: number; offset: number;
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
  scan_observation_limit_exceeded: "This scan has more observations than this review can safely compare",
  unreviewable_observations_present: "Contains observations without a current supported identity review; candidate generation is withheld",
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
