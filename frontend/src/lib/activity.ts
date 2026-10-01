import type { ActivityEvent, Criticality } from "@/lib/types";

/** Event types as Activity names them (backend app/services/events.py). */
export const EVENT_LABELS: Record<string, string> = {
  import: "Upload",
  repeat_upload: "Same file uploaded again",
  archive: "Archive",
  restore: "Restore",
  purge: "Purge",
  asset_added: "Asset added",
  finding_added: "Finding added",
  settings_changed: "Settings changed",
  profile_created: "File format created",
  profile_updated: "File format changed",
  profile_deleted: "File format deleted",
  member_added: "Member added",
  member_removed: "Member removed",
  role_changed: "Role changed",
  name_changed: "Name changed",
  password_reset: "Password reset",
  account_unlocked: "Account unlocked",
  registered: "Signed up",
  login: "Signed in",
  login_failed: "Failed sign-in",
  logout: "Signed out",
  password_changed: "Password changed",
  account_locked: "Account locked",
  event_cleanup: "Old activity deleted",
  worker_started: "Background worker started",
  worker_stopped: "Background worker stopped",
};

export const CRITICALITY_ORDER: Criticality[] = ["critical", "warning", "info"];

export function eventLabel(event: ActivityEvent): string {
  if (event.type === "restore" && event.details?.undo) return "Undo archive";
  return EVENT_LABELS[event.type] ?? event.type;
}

/** "3 min 12 s" (under a second: null). */
export function formatSeconds(seconds: number): string | null {
  seconds = Math.round(seconds);
  if (seconds < 1) return null;
  const minutes = Math.floor(seconds / 60);
  if (minutes === 0) return `${seconds} s`;
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min ${seconds % 60} s`;
}

/** How long it ran, and first how long it waited its turn (a large upload
 * waits for the background worker): "waited 15 min 2 s, took 1 min 24 s". */
export function timing(event: ActivityEvent): string | null {
  const took = formatSeconds((Date.parse(event.ended_at) - Date.parse(event.started_at)) / 1000);
  const waitedSeconds = Number(event.details?.waited_seconds ?? 0);
  const waited = waitedSeconds ? formatSeconds(waitedSeconds) : null;
  if (waited) return took ? `waited ${waited}, took ${took}` : `waited ${waited}`;
  return took ? `took ${took}` : null;
}

const COUNT_LABELS: Record<string, string> = {
  // Imports (backend ingestion_service.event_counts).
  assets_created: "assets created",
  assets_updated: "assets updated",
  assets_skipped: "assets left unchanged",
  findings_created: "findings created",
  duplicate_findings: "duplicate findings skipped",
  items_skipped: "items skipped",
  rows_failed: "rows failed",
  // Archive jobs, clean-ups.
  uploads: "uploads",
  assets: "assets",
  findings: "findings",
  duplicates_purged: "duplicates purged",
  findings_kept_with_asset: "kept with their asset",
  expired: "past retention",
  trimmed: "trimmed early",
};

/** The event's numbers and notes in a line, e.g. "500,000 created, 1,229,150
 * findings created". */
export function eventSummary(event: ActivityEvent): string {
  const parts = Object.entries(event.counts ?? {})
    .filter(([key, n]) => n && key !== "warnings_total")
    .map(([key, n]) => `${n.toLocaleString("en-US")} ${COUNT_LABELS[key] ?? key.replace(/_/g, " ")}`);
  const details = event.details ?? {};
  if (typeof details.error === "string") parts.push(details.error);
  if (typeof details.retried === "string") parts.push(details.retried);
  if (event.type === "settings_changed") {
    for (const [key, change] of Object.entries(details)) {
      const { from, to } = change as { from: unknown; to: unknown };
      parts.push(`${key.replace(/_/g, " ")}: ${show(from)} → ${show(to)}`);
    }
  }
  if (event.type === "member_added" && details.role) {
    parts.push(`as ${details.role}${details.new_account ? ", new account" : ""}`);
  }
  if (event.type === "member_removed" && details.role) parts.push(`was ${details.role}`);
  if (event.type === "role_changed" || event.type === "name_changed") {
    parts.push(`${show(details.from, "no name")} → ${show(details.to, "no name")}`);
  }
  if (event.type === "repeat_upload" && details.previously_by) parts.push(`first uploaded by ${details.previously_by}`);
  if (event.type === "profile_updated" && Array.isArray(details.changed)) parts.push(`changed: ${details.changed.join(", ")}`);
  return parts.join(", ");
}

function show(value: unknown, missing = "default"): string {
  if (value === null || value === undefined) return missing;
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
