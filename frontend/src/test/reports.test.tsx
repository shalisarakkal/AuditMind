import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReportsPage from "@/app/(app)/reports/page";
import { ReportViewer } from "@/components/ReportViewer";
import { formatDateTime } from "@/lib/domain";
import type { AuditReport } from "@/lib/types";
import { org, renderSignedIn } from "./helpers";
import { useApp } from "@/context/AppContext";

function SwitchOrg() {
  const { selectOrg } = useApp();
  return <button onClick={() => selectOrg("org-2")}>Switch organization</button>;
}

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => "/reports",
  useSearchParams: () => new URLSearchParams(navigation.search),
  useParams: () => ({ id: "rep-1" }),
}));

beforeEach(() => {
  navigation.search = "";
});


const SAMPLE_REPORT: AuditReport = {
  id: "rep-1",
  org_id: "org-1",
  title: "Q3 Executive Cyber Resilience Audit",
  period_start: null,
  period_end: null,
  frameworks: "CIS, NIST, ISO",
  status: "completed",
  generated_at: "2026-10-04T10:00:00Z",
  format: "json",
  location: null,
  error_message: null,
  started_by: "user-1",
  created_at: "2026-10-04T09:30:00Z",
  data: {
    title: "Q3 Executive Cyber Resilience Audit",
    executive_summary: "Overall organizational cyber resilience score is 82/100 (Low risk tier).",
    overall_score: 82,
    overall_tier: "low",
    resilience_summary: "Identity and Network security baselines meet CIS and NIST guidance.",
    domains: [
      {
        domain: "identity_access",
        score: 85,
        tier: "low",
        justification: "MFA enforced across administrative roles.",
        strengths: ["MFA enforced on cloud consoles"],
        weaknesses: ["A few stale guest accounts older than 90 days"],
      },
      {
        domain: "vulnerability_management",
        score: 75,
        tier: "medium",
        justification: "Vulnerability scan cadence active; critical patch window 14 days.",
        strengths: ["Continuous scanning active"],
        weaknesses: ["2 unpatched CVEs on internal subnet"],
      },
    ],
    remediations: [
      {
        title: "Enforce Hardware-backed MFA for Cloud Admins",
        description: "Require FIDO2 keys for all AWS/Azure root and administrative accounts.",
        priority: "Critical",
        domain: "identity_access",
        estimated_effort: "Quick Win",
        expected_impact: "Prevents credential interception attacks.",
        related_controls: ["CIS-5.2", "NIST-PR.AC-01"],
        affected_asset_types: ["cloud_resource", "server"],
        confidence: 0.8,
        affected_finding_ids: ["11111111-1111-4111-8111-111111111111"],
        affected_asset_ids: ["22222222-2222-4222-8222-222222222222"],
      },
    ],
    compliance_citations: [
      {
        control_id: "CIS-5.2",
        framework: "CIS",
        title: "Use Unique Passwords and MFA",
        content: "Enforce MFA on all administrative access.",
      },
    ],
    total_assets: 45,
    total_findings: 10,
    findings_by_severity: { critical: 1, high: 3, medium: 6 },
    frameworks_evaluated: ["CIS", "NIST", "ISO"],
  },
};

describe("ReportsPage", () => {
  it("labels the assessment completeness filter and changes its selection", async () => {
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({ items: [], total: 0 }),
    });
    const filter = await screen.findByRole("combobox", { name: /^Assessment completeness$/ });
    expect(filter).toHaveValue("");
    fireEvent.change(filter, { target: { value: "partial" } });
    await waitFor(() => expect(filter).toHaveValue("partial"));
  });
  it("lists reports and shows generate button for admins", async () => {
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({
        items: [{ ...SAMPLE_REPORT, data: undefined, overall_score: 82 }],
        total: 1,
      }),
    });

    await waitFor(() => {
      expect(screen.getByText("Audit Reports")).toBeInTheDocument();
      expect(screen.getByText("Q3 Executive Cyber Resilience Audit")).toBeInTheDocument();
    });

    expect(screen.getByText("+ Generate report")).toBeInTheDocument();
    expect(screen.queryByText("+ Rule-based test report")).not.toBeInTheDocument();
    expect(screen.getByText("82/100")).toBeInTheDocument();
    expect(screen.getByText(formatDateTime(SAMPLE_REPORT.created_at))).toBeInTheDocument();
  });

  it("offers cancellation instead of deletion while a report is running", async () => {
    let cancelled = false;
    const queuedReport = { ...SAMPLE_REPORT, status: "running" as const, data: undefined, error_message: null };
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({
        items: [{ ...queuedReport, status: cancelled ? "failed" : "running", error_message: cancelled ? "Generation cancelled by user" : null }],
        total: 1,
      }),
      "POST /orgs/org-1/reports/rep-1/cancel": () => {
        cancelled = true;
        return { ...queuedReport, status: "failed", error_message: "Generation cancelled by user" };
      },
    });

    expect(await screen.findByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel generation" }));

    expect(await screen.findByText("Generation cancelled by user")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("uses the shared danger confirmation for deleting a finished report", async () => {
    let deleted = false;
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({ items: deleted ? [] : [SAMPLE_REPORT], total: deleted ? 0 : 1 }),
      "DELETE /orgs/org-1/reports/rep-1": () => {
        deleted = true;
        return {};
      },
    });

    expect(await screen.findByRole("button", { name: "Delete" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("group", { name: "Delete report" })).toHaveClass("border-red-400/30");
    expect(screen.getByText(/Permanently delete/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete for good" })).toHaveClass("bg-red-400/80");
    fireEvent.click(screen.getByRole("button", { name: "Delete for good" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("No reports yet.")).toBeInTheDocument();
  });

  it("lets admins select and bulk delete finished reports but not active reports", async () => {
    const secondReport = { ...SAMPLE_REPORT, id: "rep-2", title: "Q4 Cyber Audit" };
    const runningReport = { ...SAMPLE_REPORT, id: "rep-3", title: "Active Cyber Audit", status: "running" as const };
    let deleted = false;
    const { fetchMock } = await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({
        items: deleted ? [] : [SAMPLE_REPORT, secondReport, runningReport],
        total: deleted ? 0 : 3,
      }),
      "POST /orgs/org-1/reports/bulk-delete": () => {
        deleted = true;
        return { deleted: 2 };
      },
    });

    await screen.findByText("Active Cyber Audit");
    const first = screen.getByRole("checkbox", { name: `Select ${SAMPLE_REPORT.title}` });
    const second = screen.getByRole("checkbox", { name: "Select Q4 Cyber Audit" });
    const active = screen.getByRole("checkbox", { name: "Select Active Cyber Audit" });
    expect(active).toBeDisabled();
    fireEvent.click(first);
    fireEvent.click(second);

    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
    expect(screen.getByRole("group", { name: "Delete selected reports" })).toBeInTheDocument();
    expect(screen.getByText(/2 selected reports/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete reports" }));

    await waitFor(() => expect(deleted).toBe(true));
    const bulkRequest = fetchMock.mock.calls.find(
      ([url, init]) => String(url).includes("/reports/bulk-delete") && init?.method === "POST",
    );
    expect(JSON.parse(String(bulkRequest?.[1]?.body))).toEqual({ ids: ["rep-1", "rep-2"] });
    expect(await screen.findByText("No reports yet.")).toBeInTheDocument();
  });

  it("lets any member download selected completed reports as a PDF ZIP", async () => {
    const secondReport = { ...SAMPLE_REPORT, id: "rep-2", title: "Q4 Cyber Audit" };
    const { fetchMock } = await renderSignedIn(
      <ReportsPage />,
      "viewer",
      {
        "GET /orgs/org-1/reports": () => ({ items: [SAMPLE_REPORT, secondReport], total: 2 }),
        "POST /orgs/org-1/reports/bulk-download": () => new Response("pdf zip", {
          status: 200,
          headers: { "Content-Type": "application/zip" },
        }),
      },
    );

    fireEvent.click(await screen.findByRole("checkbox", { name: `Select ${SAMPLE_REPORT.title}` }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Q4 Cyber Audit" }));
    fireEvent.click(screen.getByRole("button", { name: "Download selected PDFs" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/reports/bulk-download") && init?.method === "POST",
      );
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toEqual({ ids: ["rep-1", "rep-2"] });
    });
    expect(screen.queryByRole("button", { name: "Delete selected" })).not.toBeInTheDocument();
  });

  it("offers sortable, filterable columns and sends the URL-backed list state to the API", async () => {
    const { fetchMock } = await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({ items: [SAMPLE_REPORT], total: 1 }),
      "GET /orgs/org-1/reports/facets": () => ({ status: ["completed", "failed"], frameworks: ["CIS", "NIST"] }),
    });
    const reportQueries = () =>
      fetchMock.mock.calls
        .map(([url]) => new URL(String(url), "http://localhost"))
        .filter((url) => url.pathname.endsWith("/orgs/org-1/reports"))
        .map((url) => url.searchParams);

    expect(await screen.findByText(SAMPLE_REPORT.title)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "NIST" }));
    await waitFor(() => expect(reportQueries().at(-1)?.get("frameworks")).toBe("NIST"));
    expect(screen.getByRole("button", { name: "NIST" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => expect(reportQueries().at(-1)?.has("frameworks")).toBe(false));
    expect(screen.getByRole("columnheader", { name: /Title/ })).toHaveAttribute("aria-sort", "none");
    fireEvent.click(screen.getByRole("button", { name: /Title/ }));

    await waitFor(() => {
      expect(reportQueries().some((query) => query.get("sort") === "title" && query.get("order") === "asc")).toBe(true);
    });

    fireEvent.change(screen.getByRole("searchbox", { name: "Filter title" }), { target: { value: "Q3 Executive" } });
    await waitFor(() => {
      expect(reportQueries().some((query) => query.get("title") === "Q3 Executive")).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    fireEvent.click(await screen.findByText("All ▾", { selector: "summary" }));
    const completed = screen.getByLabelText("Completed");
    fireEvent.click(completed);
    expect(completed).toBeChecked();
    await waitFor(() => {
      expect(reportQueries().some((query) => query.getAll("status").includes("completed"))).toBe(true);
    });

    fireEvent.change(screen.getByLabelText("Created from"), { target: { value: "2026-10-01" } });
    await waitFor(() => {
      expect(reportQueries().some((query) => query.get("since") === "2026-10-01")).toBe(true);
    });
  });

  it("refreshes the open running report until completed", async () => {
    let completed = false;
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({ items: [{ ...SAMPLE_REPORT, data: undefined, status: completed ? "completed" : "running" }], total: 1 }),
      "GET /orgs/org-1/reports/rep-1": () => completed ? SAMPLE_REPORT : { ...SAMPLE_REPORT, status: "running", data: null },
    });
    fireEvent.click(await screen.findByText(SAMPLE_REPORT.title));
    await screen.findByText(/currently being generated/);
    completed = true;
    expect(await screen.findByText(SAMPLE_REPORT.data!.executive_summary, {}, { timeout: 6500 })).toBeInTheDocument();
  }, 10000);

  it("clears open reports when switching organizations", async () => {
    await renderSignedIn(<><SwitchOrg /><ReportsPage /></>, "admin", {
      "GET /orgs": () => [org(), org({ id: "org-2", name: "Second" })],
      "GET /orgs/org-1/reports": () => ({ items: [SAMPLE_REPORT], total: 1 }),
      "GET /orgs/org-1/reports/rep-1": () => SAMPLE_REPORT,
      "GET /orgs/org-2/reports": () => ({ items: [], total: 0 }),
      "GET /orgs/org-2/scans": () => [],
      "GET /orgs/org-2/archive-jobs": () => [],
    });
    fireEvent.click(await screen.findByText(SAMPLE_REPORT.title));
    await screen.findByText(SAMPLE_REPORT.data!.executive_summary);
    fireEvent.click(screen.getByText("Switch organization"));
    await waitFor(() => expect(screen.queryByText(SAMPLE_REPORT.data!.executive_summary)).not.toBeInTheDocument());
  });

  it("opens generate modal and submits report job", async () => {
    let queued = false;
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({
        items: [],
        total: 0,
      }),
      "POST /orgs/org-1/reports/generate": (init) => {
        expect(new Headers(init.headers).get("Idempotency-Key")).toBeTruthy();
        queued = true;
        return SAMPLE_REPORT;
      },
    });

    await waitFor(() => {
      expect(screen.getByText("+ Generate report")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("+ Generate report"));

    expect(screen.getByRole("dialog", { name: "Generate AI audit report" })).toBeInTheDocument();

    const submitBtn = screen.getByRole("button", { name: "Generate Report" });
    await waitFor(() => expect(submitBtn).toBeEnabled());
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(queued).toBe(true);
    });
  });

  it("reuses the idempotency key after an ambiguous network failure", async () => {
    const keys: string[] = [];
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({ items: [], total: 0 }),
      "POST /orgs/org-1/reports/generate": (init) => {
        keys.push(new Headers(init.headers).get("Idempotency-Key") ?? "");
        if (keys.length === 1) throw new Error("Connection lost after server accepted request");
        return SAMPLE_REPORT;
      },
    });
    fireEvent.click(await screen.findByText("+ Generate report"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate Report" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Generate Report" }));
    await screen.findByText(/Cannot reach the AuditMind API/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate Report" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Generate Report" }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toBeTruthy();
    expect(keys[0]).toBe(keys[1]);
  });

  it("shows and submits the configured test-only report path with clear provenance", async () => {
    let generated = false;
    const testReport: AuditReport = {
      ...SAMPLE_REPORT,
      title: "Rule-based preview",
      frameworks: null,
      assessment_type: "rule_based_test",
      overall_score: 97,
      data: {
        ...SAMPLE_REPORT.data!,
        executive_summary: "TEST-ONLY RULE-BASED REPORT. No AI model or external provider was used.",
        resilience_summary: "No CIS, NIST, or ISO control evaluation was performed.",
        total_findings: 1,
        frameworks_evaluated: [],
        compliance_citations: [],
        provenance: {
          assessment_type: "rule_based_test",
          method: "AuditMind deterministic finding severity scoring",
          version: "rule-v1",
          external_processing: false,
          framework_evaluation: "not performed",
          period_semantics: "currently active findings created within inclusive UTC dates; current inventory",
          captured_at: "2026-10-04T10:00:00Z",
        },
      },
    };
    const { fetchMock } = await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports/capabilities": () => ({ rule_based_test_enabled: true }),
      "GET /orgs/org-1/reports": () => ({
        items: generated ? [{ ...testReport, data: undefined }] : [],
        total: generated ? 1 : 0,
      }),
      "POST /orgs/org-1/reports/rule-based-test": () => {
        generated = true;
        return testReport;
      },
      "GET /orgs/org-1/reports/rep-1": () => testReport,
    });

    fireEvent.click(await screen.findByRole("button", { name: "+ Rule-based test report" }));
    expect(screen.getByRole("dialog", { name: "Generate rule-based test report" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("does not evaluate CIS, NIST, or ISO controls");
    expect(screen.queryByText("Compliance Frameworks (RAG Standards)")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Report title"), { target: { value: "Rule-based preview" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Test Report" }));

    await waitFor(() => expect(generated).toBe(true));
    const request = fetchMock.mock.calls.find(
      ([url, init]) => String(url).includes("/reports/rule-based-test") && init?.method === "POST",
    );
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ title: "Rule-based preview", frameworks: [] });

    fireEvent.click(await screen.findByText("Rule-based preview"));
    expect(await screen.findByText("Rule-based test · No AI")).toBeInTheDocument();
    expect(screen.getByText("External processing: none. AI and embedding providers were not called.")).toBeInTheDocument();
    expect(screen.getByText(/framework controls were not evaluated/i)).toBeInTheDocument();
  });

  it("shows an API error instead of appearing to have no reports", async () => {
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => {
        throw new Error("offline");
      },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the AuditMind API");
  });

  it("shows the insufficient-credit error directly in the failed report row", async () => {
    await renderSignedIn(<ReportsPage />, "admin", {
      "GET /orgs/org-1/reports": () => ({
        items: [{
          ...SAMPLE_REPORT,
          status: "failed",
          data: undefined,
          error_message: "Anthropic rejected report generation because the API account has insufficient credits. Add credits or update the Anthropic billing plan, then generate a new report.",
        }],
        total: 1,
      }),
    });

    expect(await screen.findByText(/API account has insufficient credits/)).toBeInTheDocument();
    expect(screen.getByText(/Add credits or update the Anthropic billing plan/)).toBeInTheDocument();
  });

  it("renders ReportViewer with full scores, executive summary, and remediation", () => {
    render(<ReportViewer report={SAMPLE_REPORT} />);

    expect(screen.getByText("Q3 Executive Cyber Resilience Audit")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("LOW Risk Tier")).toBeInTheDocument();
    expect(screen.getByText(/Overall organizational cyber resilience score is 82\/100/)).toBeInTheDocument();
    expect(screen.getByText("IDENTITY ACCESS")).toBeInTheDocument();
    expect(screen.getByText("Enforce Hardware-backed MFA for Cloud Admins")).toBeInTheDocument();
    expect(screen.getAllByText("CIS-5.2").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Model-estimated confidence: 80% (not calibrated)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Find finding 11111111/ })).toHaveAttribute("href", expect.stringContaining("finding_id=11111111"));
    expect(screen.getByText(/Affected assets: 22222222/)).toBeInTheDocument();
  });

  it("keeps legacy reports readable without reinterpreting their saved tier", () => {
    const data = SAMPLE_REPORT.data!;
    const remediations = data.remediations.map((action) => {
      const legacy = { ...action };
      delete legacy.confidence;
      delete legacy.affected_finding_ids;
      delete legacy.affected_asset_ids;
      return legacy;
    });
    render(<ReportViewer report={{ ...SAMPLE_REPORT, data: { ...data,
      overall_score: 35, overall_tier: "high", remediations } }} />);
    expect(screen.getByText("HIGH Risk Tier")).toBeInTheDocument();
    expect(screen.getByText("Confidence: not recorded")).toBeInTheDocument();
    expect(screen.getByText(/No specific finding references recorded/)).toBeInTheDocument();
  });

  it("shows a direct PDF download action separately from browser printing", () => {
    const onDownloadPdf = vi.fn();
    render(<ReportViewer report={SAMPLE_REPORT} onDownloadPdf={onDownloadPdf} onDownloadHtml={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));

    expect(onDownloadPdf).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Print" })).toBeInTheDocument();
  });

  it("explains Anthropic credit failures in plain language for existing reports", () => {
    render(
      <ReportViewer
        report={{
          ...SAMPLE_REPORT,
          status: "failed",
          data: null,
          error_message: "Error code: 400 - Your credit balance is too low to access the Anthropic API.",
        }}
      />,
    );

    expect(screen.getByText(/Anthropic rejected report generation because the API account has insufficient credits/)).toBeInTheDocument();
    expect(screen.getByText(/generate a new report/)).toBeInTheDocument();
  });
});
