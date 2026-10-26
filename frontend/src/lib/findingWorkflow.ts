export const WORKFLOW_LABELS = { open: "Open", accepted_risk: "Accepted risk", mitigated: "Mitigated", resolved: "Resolved", false_positive: "False positive" };
export type WorkflowStatus = keyof typeof WORKFLOW_LABELS;
export type Workflow = DeadlineMetadata & { finding_id: string; status: WorkflowStatus; version: number; assignee_id: string | null; assignee_available: boolean; assignee_label?: string | null; due_date: string | null; risk_review_date: string | null; updated_at: string | null; latest_rationale?: SavedWorkflowNote | null; latest_verification?: SavedWorkflowNote | null };
export type WorkflowHistory = { id: string; actor_label: string; version: number; before: Record<string, string | null>; after: Record<string, string | null>; rationale: string; verification: string | null; created_at: string; before_assignee_label?: string | null; after_assignee_label?: string | null };
export const WORKFLOW_OPTIONS = Object.entries(WORKFLOW_LABELS).map(([value, label]) => ({ value, label }));
export type SavedWorkflowNote = { text: string; actor_label: string; created_at: string };
export type DeadlineMetadata = { due_timezone?: string | null; due_expires_at?: string | null; risk_review_timezone?: string | null; risk_review_expires_at?: string | null };
export function browserTimezone(): string | null {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch { return null; }
}
export function formatDeadline(day: string | null | undefined, expiry: string | null | undefined) {
  if (!day) return "Not set";
  return expiry ? new Date(new Date(expiry).getTime() - 1).toLocaleString(undefined, { year:"numeric", month:"short", day:"numeric", hour:"numeric", minute:"2-digit" }) : day;
}
export function changedWorkflowFields(entry: WorkflowHistory) {
  return ["status", "assignee_id", "due_date", "risk_review_date"].filter(key => {
    if (key.endsWith("_date")) return historyValue(entry,"before",key) !== historyValue(entry,"after",key);
    if ((entry.before[key] ?? null) !== (entry.after[key] ?? null)) return true;
    return false;
  });
}
export function historyValue(entry: WorkflowHistory, side: "before" | "after", key: string) {
  const value = entry[side][key];
  if (key === "assignee_id") return value ? entry[`${side}_assignee_label`] || "Former/unavailable assignee" : "Unassigned";
  if (key === "status" && value && value in WORKFLOW_LABELS) return WORKFLOW_LABELS[value as WorkflowStatus];
  if (key.endsWith("_date")) return formatDeadline(value, entry[side][`${key.slice(0,-5)}_expires_at`]);
  return value || "Not set";
}
