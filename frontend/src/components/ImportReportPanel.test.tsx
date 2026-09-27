import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ImportReportPanel from "@/components/ImportReportPanel";

const report = { created: 4, updated: 1, skipped: 0, duplicates: 2, failed: 3, errors: [
  { row: 0, message: "whole-file problem" },
  { row: 5, message: "ip '999.1.1.1' is not a valid IP address" },
] };

describe("ImportReportPanel", () => {
  it("shows the non-zero counts and each row problem", () => {
    render(<ImportReportPanel result={{ status: "completed", report, filename: "assets.csv" }} />);

    const panel = screen.getByRole("region", { name: "Import result" });
    expect(panel).toHaveTextContent("assets.csv — imported");
    expect(panel).toHaveTextContent("Created 4");
    expect(panel).toHaveTextContent("Updated 1");
    expect(panel).toHaveTextContent("Duplicates 2");
    expect(panel).not.toHaveTextContent("Skipped");

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
});
