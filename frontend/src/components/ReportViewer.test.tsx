import { fireEvent, render, screen } from "@testing-library/react";
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
  it("localizes Captured while preserving the original provenance and authored content", () => {
    const value = report();
    const captured = "2026-10-23T16:56:58.129864+00:00";
    value.data!.provenance!.captured_at = captured;
    value.data!.provenance!.period_semantics = "currently active findings created within inclusive UTC dates; current inventory";
    const original = JSON.stringify(value);
    render(<ReportViewer report={value} />);
    expect(screen.getByText(`Captured: ${new Date(captured).toLocaleString()}`)).toBeVisible();
    expect(screen.getByText(/Date boundaries were evaluated in UTC/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Executive summary" })).toBeVisible();
    expect(JSON.stringify(value)).toBe(original);
  });
  it("retains all remediation content for report-only printing despite screen filters", () => {
    const { container } = render(<ReportViewer report={report()} />);
    fireEvent.click(screen.getByRole("button", { name: "Critical" }));
    expect(container.querySelector(".report-print")).toBeInTheDocument();
    expect(container.querySelectorAll(".report-remediation")).toHaveLength(3);
    expect(container.querySelectorAll(".report-remediation.hidden")).toHaveLength(3);
    expect(container.querySelector(".report-remediation")).toHaveClass("print:block");
  });
  it("keeps the selected priority readable using the configured cyan color", () => {
    render(<ReportViewer report={report()} />);
    const all = screen.getByRole("button", { name: "All" });
    expect(all).toHaveAttribute("aria-pressed", "true");
    expect(all).toHaveClass("bg-cyan", "text-navy");
    for (const priority of ["Critical", "High", "Medium", "All"]) {
      const target = screen.getByRole("button", { name: priority });
      fireEvent.click(target);
      expect(target).toHaveAttribute("aria-pressed", "true");
      expect(target).toHaveClass("bg-cyan", "text-navy");
      expect(screen.getAllByRole("button", { pressed: true })).toHaveLength(1);
    }
  });
  it("links domain evidence and remediation findings using the report organization", () => {
    const value = report();
    value.data!.domains[0].evidence_finding_ids = ["domain-finding"];
    value.data!.remediations[0].affected_finding_ids = ["action-finding"];
    render(<ReportViewer report={value} />);
    expect(screen.getByRole("link", { name: "Find finding domain-finding" })).toHaveAttribute("href", "/findings/lookup?org=o&finding_id=domain-finding");
    expect(screen.getByRole("link", { name: "Find finding action-finding" })).toHaveAttribute("href", "/findings/lookup?org=o&finding_id=action-finding");
  });
  it("clearly labels synthetic fixtures without implying real AI assessment", () => {
    const value = report();
    value.assessment_type = "synthetic_mock";
    render(<ReportViewer report={value} />);
    expect(screen.getByText("Synthetic mock · No AI calls")).toBeVisible();
    expect(screen.getByRole("note")).toHaveTextContent("Not a real audit or operational evidence qualification");
    expect(screen.getByText("Simulated score (not a real assessment)")).toBeVisible();
    expect(screen.queryByText("AI Audit")).not.toBeInTheDocument();
  });
  it.each(["limited", "insufficient", "conflicting"] as const)("renders partial %s evidence without a score or fabricated tier", status => {
    const value = report();
    const data = value.data!;
    data.overall_score = null; data.overall_tier = null; data.assessment_status = "partial";
    data.provenance!.schema_version = 3;
    data.domains[0] = { ...data.domains[0], score: null, tier: null, evidence_status: status,
      evidence_reason: "Specific coverage explanation" };
    render(<ReportViewer report={value} />);
    expect(screen.getByText("Partial AI assessment — overall score unavailable")).toBeVisible();
    expect(screen.getByText("Not scored")).toBeVisible();
    expect(screen.getByText("Specific coverage explanation")).toBeVisible();
    expect(screen.queryByText("High risk tier")).not.toBeInTheDocument();
    expect(screen.queryByText("0/100")).not.toBeInTheDocument();
    expect(screen.queryByText(/legacy assessment/)).not.toBeInTheDocument();
  });
  it("rejects unknown future snapshot versions without guessing scores", () => {
    const value = report(); value.data!.provenance!.schema_version = 99;
    render(<ReportViewer report={value} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unsupported assessment schema");
  });
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
