import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReportViewer } from "./ReportViewer";
import type { AuditReport } from "@/lib/types";

function report(count?: number, baseline?: number): AuditReport {
  return { id: "r", org_id: "o", title: "Test", status: "completed", frameworks: null,
    period_start: null, period_end: null, generated_at: null, format: null, location: null,
    error_message: null, started_by: null, created_at: "2026-10-23", data: {
      title: "Test", executive_summary: "Summary", resilience_summary: "Limited", overall_score: 55,
      overall_tier: "high", total_assets: 1, total_findings: 2, findings_by_severity: {},
      frameworks_evaluated: [], provenance: { model: "mock",
        ...(count == null ? {} : { sampled_findings: Array.from({ length: count }, () => ({ finding_id: "f", description: "Text", severity: "high" })) }),
        ...(baseline == null ? {} : { rule_based: { overall_score: baseline, overall_tier: "critical" } }) },
      domains: [{ domain: "network_config", score: 55, tier: "high", justification: "Complete uncertainty explanation",
        strengths: ["First strength", "Second strength"], weaknesses: ["First limitation", "Second limitation"], citation_ids: ["C1", "missing"] }],
      remediations: [0, 1, null].map(confidence => ({ title: `Action ${confidence}`, description: "Verify", priority: "High",
        domain: "network_config", estimated_effort: "Quick Win", expected_impact: "Evidence", confidence,
        citation_ids: ["C1"], related_controls: ["Descriptive text"], affected_asset_types: [] })),
      compliance_citations: [{ citation_id: "C1", control_id: "Synthetic", framework: "Test", title: "Source", content: "Full source text" }],
    } };
}

describe("assessment interpretation", () => {
  it.each([undefined, 0, 1, 2, 3])("handles sample count %s without assuming omitted evidence", count => {
    render(<ReportViewer report={report(count, 0)} />);
    expect(screen.getByText("AI resilience score (advisory)")).toBeVisible();
    expect(screen.getByText(/Captured deterministic baseline: 0\/100/)).toBeVisible();
    if (count == null) expect(screen.getByText(/Sampling coverage is not recorded/)).toBeVisible();
    else if (count < 2) expect(screen.getByText(/The model did not receive every finding/)).toBeVisible();
    else if (count === 2) expect(screen.getByText(/All counted findings were included/)).toBeVisible();
    else expect(screen.getByText(/Sampling counts are inconsistent/)).toBeVisible();
  });
  it("preserves missing baseline, full explanations, confidence boundaries and source links", () => {
    render(<ReportViewer report={report()} />);
    expect(screen.getByText(/Captured deterministic baseline: not recorded/)).toBeVisible();
    expect(screen.getByText("Complete uncertainty explanation")).toBeVisible();
    expect(screen.getByText("Strength: Second strength")).toBeVisible();
    expect(screen.getByText("Limitation/weakness: Second limitation")).toBeVisible();
    expect(screen.getByText("Model-estimated confidence: 0% (not calibrated)")).toBeVisible();
    expect(screen.getByText("Model-estimated confidence: 100% (not calibrated)")).toBeVisible();
    expect(screen.getByText("Confidence: not recorded")).toBeVisible();
    expect(screen.getAllByRole("link", { name: "C1" })[0]).toHaveAttribute("href", "#report-evidence-0");
    expect(screen.getByText(/missing \(captured source unavailable\)/)).toBeVisible();
  });
  it("does not describe deterministic test scores as AI advice", () => {
    const value = report(); value.assessment_type = "rule_based_test";
    render(<ReportViewer report={value} />);
    expect(screen.getByText("Deterministic test score")).toBeVisible();
    expect(screen.queryByText("AI resilience score (advisory)")).not.toBeInTheDocument();
  });
});
