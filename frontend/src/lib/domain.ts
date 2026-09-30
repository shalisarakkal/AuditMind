import type { ArchiveCounts, AssetType, Domain, RiskTier, ScanStatus, Severity, UserRole } from "@/lib/types";

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

export const ASSET_TYPES: AssetType[] = ["server", "workstation", "network_device", "database", "cloud_resource", "application"];

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  server: "Server",
  workstation: "Workstation",
  network_device: "Network device",
  database: "Database",
  cloud_resource: "Cloud resource",
  application: "Application",
};

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
  asset_import: "Asset list",
  findings_csv: "Findings (CSV)",
  findings_json: "Findings (JSON)",
  nessus: "Nessus scan",
  generic_assets_import: "Asset list",
  generic_findings_import: "Findings list",
  endpoint_agent_import: "Endpoint agent export",
  network_scan_import: "Network scan export",
  cloud_inventory_import: "Cloud inventory export",
};

/** An upload's kind; a tool export not listed is named after its profile
 * family ("directory_import" -> "Directory export"). */
export function scanTypeLabel(scanType: string): string {
  const family = scanType.replace(/_import$/, "").replace(/_/g, " ");
  return SCAN_TYPE_LABELS[scanType] ?? `${family.charAt(0).toUpperCase()}${family.slice(1)} export`;
}

/** "1 upload, 3 assets, 1,200 findings" (or "nothing"): rows archived,
 * restored or purged together. */
export function countsText(counts: ArchiveCounts): string {
  const parts = (
    [
      ["upload", counts.uploads],
      ["asset", counts.assets],
      ["finding", counts.findings],
    ] as const
  )
    .filter(([, n]) => n)
    .map(([noun, n]) => `${n!.toLocaleString("en-US")} ${noun}${n === 1 ? "" : "s"}`);
  return parts.join(", ") || "nothing";
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Deleted in 173 days": when an archived item is purged, from now. */
export function purgeCountdown(purgeAt: string, now = Date.now()): string {
  const days = Math.ceil((new Date(purgeAt).getTime() - now) / DAY_MS);
  if (days <= 0) return "Deleted at the next daily purge";
  return days === 1 ? "Deleted tomorrow" : `Deleted in ${days.toLocaleString("en-US")} days`;
}

/** Admins and auditors can import and upload; viewers are read-only. */
export function canWrite(role: UserRole | undefined): boolean {
  return role === "admin" || role === "auditor";
}

export function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}
