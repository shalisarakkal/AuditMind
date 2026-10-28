import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReportDetailPage from "@/app/(app)/reports/[id]/page";
import { apiClient } from "@/lib/apiClient";
import { downloadReport } from "@/lib/report";
import type { AuditReport } from "@/lib/types";

const state = vi.hoisted(() => ({ org: { id: "org-1" } as { id: string } | null, id: "rep-1" }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: state.id }) }));
vi.mock("@/context/AppContext", () => ({ useApp: () => ({ selectedOrg: state.org }) }));
vi.mock("@/lib/report", () => ({ downloadReport: vi.fn() }));
vi.mock("@/components/ReportViewer", () => ({
  ReportViewer: ({ report, onDownloadHtml, onDownloadPdf }: {
    report: AuditReport; onDownloadHtml(): void; onDownloadPdf(): void;
  }) => <section><h1>{report.title}</h1><p>{report.status}</p>
    <button onClick={onDownloadHtml}>Download HTML</button><button onClick={onDownloadPdf}>Download PDF</button></section>,
}));

const report: AuditReport = {
  id: "rep-1", org_id: "org-1", title: "Captured audit", status: "completed",
  period_start: null, period_end: null, frameworks: "NIST", generated_at: null,
  format: "json", location: null, error_message: null, started_by: null,
  created_at: "2026-10-22T12:00:00Z", data: null,
};

beforeEach(() => { state.org = { id: "org-1" }; state.id = "rep-1"; vi.mocked(downloadReport).mockReset(); });

describe("report detail lifecycle", () => {
  it.each(["organization", "report id"])("does not fetch without %s", async missing => {
    if (missing === "organization") state.org = null; else state.id = "";
    const get = vi.spyOn(apiClient, "get");
    render(<ReportDetailPage />);
    expect(await screen.findByRole("heading", { name: "Report not found" })).toBeVisible();
    expect(get).not.toHaveBeenCalled();
  });

  it("shows loading, then fetches the current organization's report", async () => {
    let resolve!: (value: AuditReport) => void;
    const get = vi.spyOn(apiClient, "get").mockReturnValue(new Promise<AuditReport>(done => { resolve = done; }));
    render(<ReportDetailPage />);
    expect(screen.getByText("Loading audit report...")).toBeVisible();
    await act(async () => { resolve(report); });
    expect(screen.getByRole("heading", { name: report.title })).toBeVisible();
    expect(get).toHaveBeenCalledWith("/orgs/org-1/reports/rep-1");
  });

  it.each([new Error("Access denied"), "opaque failure"])("shows a safe load failure", async error => {
    vi.spyOn(apiClient, "get").mockRejectedValue(error);
    render(<ReportDetailPage />);
    expect(await screen.findByRole("heading", { name: "Report not found" })).toBeVisible();
    expect(screen.getByText(error instanceof Error ? error.message : "Failed to load report")).toBeVisible();
  });

  it.each(["pending", "running"] as const)("polls %s jobs and stops polling terminal snapshots", async status => {
    vi.useFakeTimers();
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ ...report, status }).mockResolvedValue(report);
    render(<ReportDetailPage />);
    await act(async () => {});
    expect(screen.getByText(status)).toBeVisible();
    await act(async () => { vi.advanceTimersByTime(3000); });
    expect(screen.getByText("completed")).toBeVisible();
    await act(async () => { vi.advanceTimersByTime(9000); });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("ignores a delayed response after unmount and clears the polling timer", async () => {
    vi.useFakeTimers();
    let resolve!: (value: AuditReport) => void;
    const get = vi.spyOn(apiClient, "get").mockReturnValue(new Promise<AuditReport>(done => { resolve = done; }));
    const view = render(<ReportDetailPage />); view.unmount();
    await act(async () => { resolve(report); vi.advanceTimersByTime(9000); });
    expect(get).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("heading", { name: report.title })).not.toBeInTheDocument();
  });

  it.each(["html", "pdf"] as const)("downloads %s for the current organization", async format => {
    vi.spyOn(apiClient, "get").mockResolvedValue(report);
    vi.mocked(downloadReport).mockResolvedValue();
    render(<ReportDetailPage />); await screen.findByRole("heading", { name: report.title });
    fireEvent.click(screen.getByRole("button", { name: `Download ${format.toUpperCase()}` }));
    expect(downloadReport).toHaveBeenCalledWith("org-1", "rep-1", report.title, format);
  });

  it.each([new Error("Download denied"), "opaque failure"])("shows download errors and clears them on retry", async error => {
    vi.spyOn(apiClient, "get").mockResolvedValue(report);
    vi.mocked(downloadReport).mockRejectedValueOnce(error).mockResolvedValue();
    render(<ReportDetailPage />); await screen.findByRole("heading", { name: report.title });
    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(error instanceof Error ? error.message : "Failed to download report");
    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    await act(async () => {});
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
