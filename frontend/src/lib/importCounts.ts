import type { ImportReport } from "@/lib/types";

// What an import report's counts are counts of (backend
// ingestion_service.event_counts): an asset list counts assets; a findings
// file, findings; a tool export (import profile), assets and then findings.

type ReportKey = "created" | "updated" | "skipped" | "repeated" | "findings_created" | "duplicates" | "failed";
type Kind = "assets" | "findings" | "profile";

// Each asset is counted once, by its first row (created, updated or left
// unchanged); its later rows are repeats (backend ImportReport.repeated).
const REPEATED = "rows repeated an asset listed earlier in the file";

const LABELS: Record<Kind, Partial<Record<ReportKey, string>>> = {
  assets: {
    created: "assets created",
    updated: "existing assets updated",
    skipped: "existing assets left unchanged",
    repeated: REPEATED,
    failed: "rows failed",
  },
  findings: {
    created: "findings created",
    duplicates: "duplicate findings skipped",
    skipped: "items skipped",
    failed: "rows failed",
  },
  profile: {
    created: "assets created",
    updated: "existing assets updated",
    skipped: "existing assets left unchanged",
    repeated: REPEATED,
    findings_created: "findings created",
    duplicates: "duplicate findings skipped",
    failed: "rows failed",
  },
};

// Findings files, and the import profile that records findings only
// (backend ingestion_service.FINDINGS_ONLY_SCAN_TYPES).
const FINDINGS_ONLY = [
  "findings_csv",
  "findings_json",
  "nessus",
  "generic_findings_import",
  // Event logs: findings that sum events up (Phase 2f part 2).
  "azure_activity_import",
  "aws_cloudtrail_import",
  "gcp_audit_import",
  "ossem_events_import",
];

export function importKind(scanType: string | undefined): Kind {
  if (scanType === "asset_import") return "assets";
  if (scanType && FINDINGS_ONLY.includes(scanType)) return "findings";
  return "profile";
}

/** The report's non-zero counts, each with what it counts, in report order:
 * [{key: "created", label: "assets created", count: 900}, ...]. */
export function importCounts(scanType: string | undefined, report: Partial<ImportReport>) {
  const labels = LABELS[importKind(scanType)];
  return (Object.keys(labels) as ReportKey[])
    .map((key) => ({ key, label: labels[key]!, count: Number(report[key] ?? 0) }))
    .filter((c) => c.count > 0);
}

/** "900 assets created, 9,100 existing assets updated, 2,792 findings created". */
export function importCountsText(scanType: string | undefined, report: Partial<ImportReport>): string {
  return importCounts(scanType, report)
    .map((c) => `${c.count.toLocaleString("en-US")} ${c.label}`)
    .join(", ");
}
