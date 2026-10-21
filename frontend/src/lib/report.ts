import { apiClient } from "@/lib/apiClient";

const ANTHROPIC_CREDIT_ERROR =
  "Anthropic rejected report generation because the API account has insufficient credits. Add credits or update the Anthropic billing plan, then generate a new report.";

export type ReportDownloadFormat = "html" | "pdf";

function safeFilename(title: string): string {
  return title.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[_\.]+|[_\.]+$/g, "").slice(0, 100).toLowerCase() || "report";
}

async function saveDownload(response: Response, filename: string): Promise<void> {
  if (!response.ok) {
    let message = `Download failed (${response.status})`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      if (response.statusText) message = response.statusText;
    }
    throw new Error(message);
  }

  const url = window.URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

export async function downloadReport(
  orgId: string,
  reportId: string,
  title: string,
  format: ReportDownloadFormat,
): Promise<void> {
  const response = await fetch(
    `/api/v1/orgs/${orgId}/reports/${reportId}/download?format=${format}`,
    { headers: apiClient.authHeaders() },
  );
  await saveDownload(response, `audit_report_${safeFilename(title)}_${reportId}.${format}`);
}

export async function downloadReportsZip(orgId: string, reportIds: string[]): Promise<void> {
  const response = await fetch(`/api/v1/orgs/${orgId}/reports/bulk-download`, {
    method: "POST",
    headers: { ...apiClient.authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ ids: reportIds }),
  });
  await saveDownload(response, "audit_reports.zip");
}

export function reportErrorMessage(message: string | null | undefined): string | null {
  if (!message) return null;
  const normalized = message.toLowerCase();
  if (normalized.includes("credit balance is too low") || normalized.includes("insufficient credits")) {
    return ANTHROPIC_CREDIT_ERROR;
  }
  return message;
}
