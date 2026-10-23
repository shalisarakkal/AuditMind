import { beforeEach, expect, it, vi } from "vitest";
import { downloadReport, downloadReportsZip, reportErrorMessage } from "./report";
import { setToken } from "./apiClient";

const NativeURL = URL;
const create = vi.fn(() => "blob:fixture");
const revoke = vi.fn();
beforeEach(() => {
  create.mockClear(); revoke.mockClear(); setToken("fixture-token");
  class FixtureURL extends NativeURL {
    static createObjectURL = create;
    static revokeObjectURL = revoke;
  }
  vi.stubGlobal("URL", FixtureURL);
});

it.each([
  ["html", "Quarter / Report", "quarter_report"],
  ["pdf", "...___", "report"],
  ["pdf", "A".repeat(120), "a".repeat(100)],
] as const)("downloads %s with safe filenames and releases blob URLs", async (format, title, expectedTitle) => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockResolvedValue(new Response("synthetic download"));
  vi.stubGlobal("fetch", fetch);
  const links: HTMLAnchorElement[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { links.push(this); });
  await downloadReport("org-1", "rep-1", title, format);
  expect(fetch).toHaveBeenCalledWith(`/api/v1/orgs/org-1/reports/rep-1/download?format=${format}`,
    { headers: { Authorization: "Bearer fixture-token", "X-Requested-With": "AuditMind" } });
  expect(links[0].download).toBe(`audit_report_${expectedTitle}_rep-1.${format}`);
  expect(document.body.contains(links[0])).toBe(false);
  expect(create).toHaveBeenCalledOnce(); expect(revoke).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1000);
  expect(revoke).toHaveBeenCalledWith("blob:fixture");
});

it.each([
  [{ detail: "Access denied" }, false, "Forbidden", "Access denied"],
  [{ detail: { secret: "not a user message" } }, false, "Forbidden", "Download failed (403)"],
  [{}, true, "Forbidden", "Forbidden"],
  [{}, true, "", "Download failed (403)"],
] as const)("handles download errors without creating blobs", async (body, malformed, statusText, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, statusText,
    json: malformed ? vi.fn().mockRejectedValue(new Error("Not JSON")) : vi.fn().mockResolvedValue(body) }));
  await expect(downloadReport("org-1", "rep-1", "Audit", "pdf")).rejects.toThrow(message);
  expect(create).not.toHaveBeenCalled();
});

it("posts only selected report IDs for an authorized ZIP download", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("synthetic zip"));
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe("audit_reports.zip");
  });
  await downloadReportsZip("org-1", ["rep-1", "rep-2"]);
  expect(fetch).toHaveBeenCalledWith("/api/v1/orgs/org-1/reports/bulk-download", {
    method: "POST", headers: { Authorization: "Bearer fixture-token", "X-Requested-With": "AuditMind", "Content-Type": "application/json" },
    body: JSON.stringify({ ids: ["rep-1", "rep-2"] }),
  });
});

it.each([undefined, null, ""])("does not invent an error for empty input", message => {
  expect(reportErrorMessage(message)).toBeNull();
});

it.each(["Credit balance is too low", "INSUFFICIENT CREDITS"])("explains provider credit failures", message => {
  expect(reportErrorMessage(message)).toMatch(/Anthropic.*insufficient credits/);
});

it("preserves unrelated provider failures", () => {
  expect(reportErrorMessage("Service unavailable")).toBe("Service unavailable");
});
