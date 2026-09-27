import type { Domain, RiskTier, ScanStatus, Severity, UserRole } from "@/lib/types";

// Display order matches the backend Domain enum.
export const DOMAIN_ORDER: Domain[] = [
  "identity_access",
  "network_config",
  "vulnerability_management",
  "backup_recovery",
  "monitoring_detection",
  "incident_response",
  "compliance_alignment",
];

export const DOMAIN_LABELS: Record<Domain, string> = {
  identity_access: "Identity & Access",
  network_config: "Network & Config",
  vulnerability_management: "Vulnerability Mgmt",
  backup_recovery: "Backup & Recovery",
  monitoring_detection: "Monitoring & Detection",
  incident_response: "Incident Response",
  compliance_alignment: "Compliance Alignment",
};

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

export const TIER_COLORS: Record<RiskTier, string> = {
  low: "text-emerald-400",
  medium: "text-yellow-400",
  high: "text-orange-400",
  critical: "text-red-400",
};

// Badge styles; a critical finding is shown like a critical-risk tier.
export const SEVERITY_BADGES: Record<Severity, string> = {
  critical: "bg-red-400/15 text-red-300",
  high: "bg-orange-400/15 text-orange-300",
  medium: "bg-yellow-400/15 text-yellow-200",
  low: "bg-emerald-400/15 text-emerald-300",
};

export const SCAN_STATUS_BADGES: Record<ScanStatus, string> = {
  pending: "bg-white/10 text-white/70",
  running: "bg-cyan/15 text-cyan",
  completed: "bg-emerald-400/15 text-emerald-300",
  failed: "bg-red-400/15 text-red-300",
};

export const SCAN_TYPE_LABELS: Record<string, string> = {
  asset_import: "Asset import",
  findings_csv: "Findings (CSV)",
  findings_json: "Findings (JSON)",
  nessus: "Nessus scan",
};

/** Admins and auditors can import and upload; viewers are read-only. */
export function canWrite(role: UserRole | undefined): boolean {
  return role === "admin" || role === "auditor";
}

export function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}
