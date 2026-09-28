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
  it("shows the non-zero counts and each row problem", () => {
    render(<ImportReportPanel result={{ status: "completed", report, filename: "assets.csv" }} />);

    const panel = screen.getByRole("region", { name: "Import result" });
    expect(panel).toHaveTextContent("assets.csv — imported");
    expect(panel).toHaveTextContent("Created 4");
    expect(panel).toHaveTextContent("Updated 1");
    expect(panel).toHaveTextContent("Duplicates 2");
    expect(panel).not.toHaveTextContent("Skipped");
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

    expect(screen.getByText(/import failed/)).toBeInTheDocument();
    expect(screen.getByText("Upload limit exceeded")).toBeInTheDocument();
    screen.getByRole("button", { name: "Dismiss" }).click();
    expect(onDismiss).toHaveBeenCalled();
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
    render(<ImportReportPanel result={{ status: "completed", report: profileReport, filename: "scan.csv" }} />);

    const panel = screen.getByRole("region", { name: "Import result" });
    expect(panel).toHaveTextContent("scan.csv — imported");
    expect(panel).toHaveTextContent("Assets created 4");
    expect(panel).toHaveTextContent("Assets updated 1");
    expect(panel).toHaveTextContent("Findings created 8");
    expect(panel).toHaveTextContent("Duplicate findings 1");
    expect(panel).toHaveTextContent("Warnings 2");

    const problems = within(panel).getByRole("region", { name: "Problems" });
    expect(within(problems).getAllByRole("row")).toHaveLength(2);
    const warnings = within(panel).getByRole("region", { name: "Warnings — imported, but worth checking" });
    expect(within(warnings).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual([
      "2ip 251.88.70.177 is a reserved address; imported anyway",
      "9RiskScore is 'eleven', not a score from 0 to 10; recorded as medium",
    ]);
  });

  it("reads a report saved before warnings existed", () => {
    const old = { created: 1, updated: 0, skipped: 0, duplicates: 0, failed: 0, errors: [] } as unknown as typeof report;
    render(<ImportReportPanel result={{ status: "completed", report: old, filename: "old.csv" }} />);
    expect(screen.getByRole("region", { name: "Import result" })).toHaveTextContent("Created 1");
  });

  it("counts all warnings when the list is cut short", () => {
    const many = { ...report, errors: [], failed: 0, warnings: [{ row: 2, message: "odd" }], warnings_total: 1500 };
    render(<ImportReportPanel result={{ status: "completed", report: many, filename: "big.csv" }} />);

    const panel = screen.getByRole("region", { name: "Import result" });
    expect(panel).toHaveTextContent("Warnings 1500");
    expect(panel).toHaveTextContent("Showing the first 1 of 1500 warnings.");
  });
});
