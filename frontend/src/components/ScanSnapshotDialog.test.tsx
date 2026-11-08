import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { json, mockApi } from "@/test/helpers";
import ScanSnapshotDialog, { ScanSnapshotComparisonDialog } from "./ScanSnapshotDialog";
import type { SnapshotView } from "@/lib/scanSnapshots";

const fields = { snapshot_kind: "complete", tool_name: "Scanner", tool_instance_id: "scanner-1", tool_configuration_id: "policy-v1",
  targets: ["10.0.0.0/24"], exclusions: ["10.0.0.20"], unreachable_targets: [], coverage_confirmed: true, source_snapshot_at: "2026-11-05T10:00:00Z" };
const view: SnapshotView = { scan: { id: "s1", filename: "baseline.csv", scan_type: "findings_csv", profile: null, status: "completed", completed_at: "2026-11-05T12:00:00Z", ingestion_config_fingerprint: "config-1" },
  declaration: { id: "d1", version: 2, state: "declared", declaration: fields, rationale: "Reviewed source coverage", actor_label: "Reviewer", created_at: "2026-11-05T13:00:00Z" },
  declaration_blockers: [], complete_blockers: [] };
const props = { orgId: "o1", orgName: "Synthetic org", scanId: "s1", writer: true,
  onClose: vi.fn(), onBaseline: vi.fn(), onCompare: vi.fn() };

describe("Scan snapshot declarations", () => {
  it("keeps legacy scans undeclared and allows pinning a baseline without a write", async () => {
    const calls = mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => ({ ...view, declaration: null,
      declaration_blockers: ["captured_import_configuration_unavailable"] }) });
    render(<ScanSnapshotDialog {...props} />);
    expect(await screen.findByText("No declaration saved")).toBeVisible();
    expect(screen.getByRole("button", { name: "Declare snapshot" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Use as baseline" }));
    expect(props.onBaseline).toHaveBeenCalledWith("baseline.csv");
    expect(calls.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("submits the loaded version and explicit source scope while leaving fingerprint server-owned", async () => {
    let body: Record<string, unknown> | undefined;
    mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view,
      "PUT /orgs/o1/scans/s1/snapshot": init => { body = JSON.parse(String(init.body)); return view; } });
    render(<ScanSnapshotDialog {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revise declaration" }));
    expect(screen.getByLabelText("Source snapshot type")).toHaveValue("complete");
    await userEvent.type(screen.getByLabelText("Declaration rationale"), "New source policy reviewed");
    await userEvent.click(screen.getByRole("button", { name: "Save declaration" }));
    await waitFor(() => expect(body?.expected_version).toBe(2));
    expect(body?.targets).toEqual(["10.0.0.0/24"]);
    expect(body?.coverage_confirmed).toBe(true);
    expect(body?.source_snapshot_at).toBe(fields.source_snapshot_at);
    expect(body).not.toHaveProperty("ingestion_config_fingerprint");
  });

  it("fences a stale edit and requires explicit reload before another save", async () => {
    mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view,
      "PUT /orgs/o1/scans/s1/snapshot": () => json({ detail: { code: "snapshot_version_conflict", message: "Snapshot declaration changed. Reload before saving." } }, 409) });
    render(<ScanSnapshotDialog {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revise declaration" }));
    fireEvent.change(screen.getByLabelText("Declaration rationale"), { target: { value: "Draft" } });
    await userEvent.click(screen.getByRole("button", { name: "Save declaration" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed");
    expect(screen.getByRole("button", { name: "Save declaration" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Reload saved declaration" }));
    expect(await screen.findByRole("button", { name: "Revise declaration" })).toBeEnabled();
  });

  it("keeps viewers read-only and attributes the saved declaration", async () => {
    mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view });
    render(<ScanSnapshotDialog {...props} writer={false} />);
    expect(await screen.findByText(/Reviewer/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Revise declaration" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke declaration" })).not.toBeInTheDocument();
  });

  it("keeps an incomplete-import draft editable so the user can choose Partial", async () => {
    mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view,
      "PUT /orgs/o1/scans/s1/snapshot": () => json({ detail: { code: "snapshot_declaration_blocked",
        message: "This scan cannot receive that declaration", reasons: ["import_has_errors_skips_or_warnings"] } }, 409) });
    render(<ScanSnapshotDialog {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revise declaration" }));
    fireEvent.change(screen.getByLabelText("Declaration rationale"), { target: { value: "Keep this draft" } });
    await userEvent.click(screen.getByRole("button", { name: "Save declaration" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Import contains errors, skipped items or warnings");
    expect(screen.getByLabelText("Declaration rationale")).toHaveValue("Keep this draft");
    expect(screen.getByRole("button", { name: "Save declaration" })).toBeEnabled();
    await userEvent.selectOptions(screen.getByLabelText("Source snapshot type"), "partial");
    expect(screen.getByLabelText("Source snapshot type")).toHaveValue("partial");
    expect(screen.queryByRole("button", { name: "Reload saved declaration" })).not.toBeInTheDocument();
  });

  it("preserves an unchanged stored source instant including subsecond precision", async () => {
    const original = "2026-11-05T10:00:00.123456Z";
    const precise = { ...view, declaration: { ...view.declaration!, declaration: { ...fields, source_snapshot_at: original } } };
    let body: Record<string, unknown> | undefined;
    mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => precise,
      "PUT /orgs/o1/scans/s1/snapshot": init => { body = JSON.parse(String(init.body)); return precise; } });
    render(<ScanSnapshotDialog {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revise declaration" }));
    fireEvent.change(screen.getByLabelText("Declaration rationale"), { target: { value: "Scope review only" } });
    await userEvent.click(screen.getByRole("button", { name: "Save declaration" }));
    await waitFor(() => expect(body?.source_snapshot_at).toBe(original));
  });
});

describe("Scan snapshot comparison", () => {
  it("requires a deliberate review and shows a read-only reviewed-identity candidate", async () => {
    const current = { ...view, scan: { ...view.scan, id: "s2", filename: "current.csv" } };
    let body: unknown;
    const calls = mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view, "GET /orgs/o1/scans/s2/snapshot": () => current,
      "POST /orgs/o1/scans/snapshot-comparison": init => { body = JSON.parse(String(init.body)); return {
        reviewed_at: "2026-11-05T14:00:00Z", baseline: view, current, declared_metadata_matches: true, absence_eligible: true,
        blocking_reasons: [], absence_blockers: [],
        scope_differences: { baseline_exclusions: ["10.0.0.20"], current_exclusions: ["10.0.0.20"] },
        review_candidates: [{ finding_id: "finding-1", baseline_observation_id: "observation-1",
          reviewable_baseline_observation_count: 2, asset_id: "asset-1", description: "Synthetic finding",
          category: "TEST-1", domain: "network_config", severity: "high", workflow_status: "open",
          baseline_recorded_at: "2026-11-05T12:00:00Z" }],
        candidate_count: 1, candidate_offset: 0, candidate_limit: 50,
        baseline_reviewable_observations: 2, current_reviewable_observations: 1,
        baseline_unreviewable_observations: 0, current_unreviewable_observations: 0,
        ambiguous_baseline_identity_count: 0 }; } });
    render(<ScanSnapshotComparisonDialog orgId="o1" orgName="Synthetic org" baselineId="s1" currentId="s2" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Compare scans and build review list" })).toBeEnabled());
    expect(calls.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    expect(screen.getByRole("region", { name: "Baseline" })).toHaveTextContent("baseline.csv");
    expect(screen.getByRole("region", { name: "Current" })).toHaveTextContent("current.csv");
    await userEvent.click(screen.getByRole("button", { name: "Compare scans and build review list" }));
    const result = await screen.findByRole("region", { name: "Comparison result" });
    expect(within(result).getByText("Declared scan metadata matches")).toBeVisible();
    expect(result).toHaveTextContent("Candidate review available");
    expect(result).toHaveTextContent("Synthetic finding · high");
    expect(result).toHaveTextContent("Baseline exclusions: 10.0.0.20");
    expect(within(result).getByRole("link", { name: "Open finding" })).toHaveAttribute(
      "href", "/findings?org=o1&finding_id=finding-1");
    expect(body).toEqual({ baseline_scan_id: "s1", current_scan_id: "s2", baseline_version: 2, current_version: 2,
      candidate_offset: 0, candidate_limit: 50 });
    expect(calls.mock.calls.filter(([, init]) => init?.method && init.method !== "GET")).toHaveLength(1);
  });

  it("shows current unreviewable coverage while withholding candidates", async () => {
    const current = { ...view, scan: { ...view.scan, id: "s2", filename: "current.nessus" } };
    const calls = mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view, "GET /orgs/o1/scans/s2/snapshot": () => current,
      "POST /orgs/o1/scans/snapshot-comparison": () => ({
        reviewed_at: "2026-11-05T14:00:00Z", baseline: view, current, declared_metadata_matches: true,
        absence_eligible: false, blocking_reasons: [], absence_blockers: ["current:unreviewable_observations_present"],
        scope_differences: {}, review_candidates: [], candidate_count: 0, candidate_offset: 0, candidate_limit: 50,
        baseline_reviewable_observations: 2, current_reviewable_observations: 0,
        baseline_unreviewable_observations: 1, current_unreviewable_observations: 1,
        ambiguous_baseline_identity_count: 0,
      }) });
    render(<ScanSnapshotComparisonDialog orgId="o1" orgName="Synthetic org" baselineId="s1" currentId="s2" onClose={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Compare scans and build review list" }));
    const result = await screen.findByRole("region", { name: "Comparison result" });
    expect(result).toHaveTextContent("Candidate review blocked");
    expect(result).toHaveTextContent("Current: Contains observations without a current supported identity review");
    expect(result).toHaveTextContent("baseline 2 reviewable / 1 unreviewable; current 0 reviewable / 1 unreviewable");
    expect(result).not.toHaveTextContent("Findings to review");
    expect(calls.mock.calls.filter(([, init]) => init?.method && init.method !== "GET")).toHaveLength(1);
  });
});
