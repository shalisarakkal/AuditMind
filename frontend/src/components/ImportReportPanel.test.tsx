import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ImportReportPanel from "@/components/ImportReportPanel";

const report = {
  created: 4,
  updated: 1,
  skipped: 0,
  duplicates: 2,
  failed: 3,
  findings_created: 0,
  errors: [
    { row: 0, message: "whole-file problem" },
    { row: 5, message: "ip '999.1.1.1' is not a valid IP address" },
  ],
  warnings: [],
};

describe("ImportReportPanel", () => {
  it("counts each asset once and its other rows as repeats", () => {
    const repeats = { ...report, created: 10800, updated: 0, repeated: 489200, errors: [], failed: 0, duplicates: 0 };
    render(<ImportReportPanel result={{ status: "completed", report: repeats, filename: "ad.csv", scanType: "directory_import" }} />);

    const panel = screen.getByRole("region", { name: "Upload result" });
    expect(panel).toHaveTextContent("Assets created 10,800");
    expect(panel).toHaveTextContent("Rows repeated an asset listed earlier in the file 489,200");
    expect(panel).not.toHaveTextContent("Existing assets updated");
  });

  it("shows the non-zero counts and each row problem", () => {
    render(<ImportReportPanel result={{ status: "completed", report, filename: "scan.csv", scanType: "network_scan_import" }} />);

    const panel = screen.getByRole("region", { name: "Upload result" });
    expect(panel).toHaveTextContent("scan.csv — processed");
    // Each count says what it counts: a tool export makes assets and findings.
    expect(panel).toHaveTextContent("Assets created 4");
    expect(panel).toHaveTextContent("Existing assets updated 1");
    expect(panel).toHaveTextContent("Duplicate findings skipped 2");
    expect(panel).not.toHaveTextContent("left unchanged");
    expect(panel).not.toHaveTextContent("Warnings");
    expect(panel).not.toHaveTextContent("Findings created");

    const rows = within(panel).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      "Filewhole-file problem",
      "5ip '999.1.1.1' is not a valid IP address",
    ]);
    expect(panel).toHaveTextContent("Showing the first 2 of 3 problems.");
  });

  it("shows a failure with its error and can be dismissed", () => {
    const onDismiss = vi.fn();
    render(
      <ImportReportPanel result={{ status: "failed", report: null, error: "Upload limit exceeded", filename: "big.csv" }} onDismiss={onDismiss} />,
    );

    expect(screen.getByText(/processing failed/)).toBeInTheDocument();
    expect(screen.getByText("Upload limit exceeded")).toBeInTheDocument();
    screen.getByRole("button", { name: "Dismiss" }).click();
    expect(onDismiss).toHaveBeenCalled();
  });

  it("offers Retry on a failure only when asked to", () => {
    const onRetry = vi.fn();
    const failed = { status: "failed" as const, report: null, error: "Cut off twice", filename: "big.csv" };
    const { rerender } = render(<ImportReportPanel result={failed} onRetry={onRetry} />);
    screen.getByRole("button", { name: "Retry" }).click();
    expect(onRetry).toHaveBeenCalled();
    rerender(<ImportReportPanel result={failed} />);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("labels asset and finding counts for a profile import and lists warnings apart", () => {
    const profileReport = {
      ...report,
      findings_created: 8,
      duplicates: 1,
      failed: 1,
      errors: [{ row: 7, message: "hostname or ip is required" }],
      warnings: [
        { row: 2, message: "ip 251.88.70.177 is a reserved address; imported anyway" },
        { row: 9, message: "RiskScore is 'eleven', not a score from 0 to 10; recorded as medium" },
      ],
    };
    render(
      <ImportReportPanel result={{ status: "completed", report: profileReport, filename: "scan.csv", scanType: "endpoint_agent_import" }} />,
    );

    const panel = screen.getByRole("region", { name: "Upload result" });
    expect(panel).toHaveTextContent("scan.csv — processed");
    expect(panel).toHaveTextContent("Assets created 4");
    expect(panel).toHaveTextContent("Existing assets updated 1");
    expect(panel).toHaveTextContent("Findings created 8");
    expect(panel).toHaveTextContent("Duplicate findings skipped 1");
    expect(panel).toHaveTextContent("Warnings 2");

    const problems = within(panel).getByRole("region", { name: "Problems" });
    expect(within(problems).getAllByRole("row")).toHaveLength(2);
    const warnings = within(panel).getByRole("region", { name: "Warnings — recorded, but worth checking" });
    expect(within(warnings).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual([
      "2ip 251.88.70.177 is a reserved address; imported anyway",
      "9RiskScore is 'eleven', not a score from 0 to 10; recorded as medium",
    ]);
  });

  it("reads a report saved before warnings existed", () => {
    const old = { created: 1, updated: 0, skipped: 0, duplicates: 0, failed: 0, errors: [] } as unknown as typeof report;
    render(<ImportReportPanel result={{ status: "completed", report: old, filename: "old.csv", scanType: "asset_import" }} />);
    expect(screen.getByRole("region", { name: "Upload result" })).toHaveTextContent("Assets created 1");
  });

  it("counts all warnings when the list is cut short", () => {
    const many = { ...report, errors: [], failed: 0, warnings: [{ row: 2, message: "odd" }], warnings_total: 1500 };
    render(<ImportReportPanel result={{ status: "completed", report: many, filename: "big.csv" }} />);

    const panel = screen.getByRole("region", { name: "Upload result" });
    expect(panel).toHaveTextContent("Warnings 1500");
    expect(panel).toHaveTextContent("Showing the first 1 of 1500 warnings.");
  });

  it("lists the rows skipped and the duplicates, with why, folded away", () => {
    const withNotes = {
      ...report,
      errors: [],
      failed: 0,
      skipped: 487,
      skipped_rows: [{ row: 3, item: "web-01: Nessus 19506 Scan Information", message: "Info severity: skipped, as Settings say" }],
      duplicate_rows: [
        { row: 7, item: "web-01: CVE-1", message: "Same as a finding from scan_0915.nessus" },
        { row: 9, item: "db-01: MFA", message: "Same as row 4 of this file" },
      ],
    };
    render(<ImportReportPanel result={{ status: "completed", report: withNotes, filename: "s.nessus", scanType: "nessus" }} />);

    expect(screen.getByText("Skipped — 487 (the first 1 listed)")).toBeInTheDocument();
    expect(screen.getByText("Duplicates — 2")).toBeInTheDocument();
    const duplicates = within(screen.getByRole("region", { name: "Duplicates", hidden: true })).getAllByRole("row", { hidden: true });
    expect(duplicates.slice(1).map((r) => r.textContent)).toEqual([
      "7web-01: CVE-1Same as a finding from scan_0915.nessus",
      "9db-01: MFASame as row 4 of this file",
    ]);
  });

  it("shows no lists for an upload from before they were kept", () => {
    render(<ImportReportPanel result={{ status: "completed", report: { ...report, skipped: 5 }, filename: "old.csv" }} />);
    expect(screen.queryByText(/^Skipped —/)).not.toBeInTheDocument();
  });
});
