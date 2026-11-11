import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { json, mockApi } from "@/test/helpers";
import ScanSnapshotDialog, { ScanSnapshotComparisonDialog, ScanSnapshotQueueDialog } from "./ScanSnapshotDialog";
import type { AbsenceReviewQueueItem, SnapshotView } from "@/lib/scanSnapshots";

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
  it("requires a deliberate review and explicitly saves eligible candidates to the queue", async () => {
    const current = { ...view, scan: { ...view.scan, id: "s2", filename: "current.csv" } };
    let compareBody: unknown, queueBody: unknown;
    const comparisonResult = {
      reviewed_at: "2026-11-05T14:00:00Z", baseline: view, current, declared_metadata_matches: true, absence_eligible: true,
      blocking_reasons: [], absence_blockers: [],
      scope_differences: { baseline_exclusions: ["10.0.0.20"], current_exclusions: ["10.0.0.20"] },
      review_candidates: [{ finding_id: "finding-1", baseline_observation_id: "observation-1",
        reviewable_baseline_observation_count: 2, asset_id: "asset-1", description: "Synthetic finding",
        category: "TEST-1", domain: "network_config", severity: "high", workflow_status: "open", workflow_version: 0,
        baseline_recorded_at: "2026-11-05T12:00:00Z" }],
      candidate_count: 1, candidate_offset: 0, candidate_limit: 50,
      baseline_reviewable_observations: 2, current_reviewable_observations: 1,
      baseline_unreviewable_observations: 0, current_unreviewable_observations: 0,
      ambiguous_baseline_identity_count: 0, review_token: "a".repeat(64), review_queue_batch_id: null, review_queue_item_count: 0,
    };
    const calls = mockApi({ "GET /orgs/o1/scans/s1/snapshot": () => view, "GET /orgs/o1/scans/s2/snapshot": () => current,
      "POST /orgs/o1/scans/snapshot-comparison": init => { compareBody = JSON.parse(String(init.body)); return comparisonResult; },
      "POST /orgs/o1/scans/snapshot-comparison/queue": init => {
        queueBody = JSON.parse(String(init.body));
        return { ...comparisonResult, review_queue_batch_id: "batch-1", review_queue_item_count: 1 };
      } });
    render(<ScanSnapshotComparisonDialog orgId="o1" orgName="Synthetic org" baselineId="s1" currentId="s2" writer onClose={vi.fn()} />);
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
    expect(compareBody).toEqual({ baseline_scan_id: "s1", current_scan_id: "s2", baseline_version: 2, current_version: 2,
      candidate_offset: 0, candidate_limit: 50 });
    expect(calls.mock.calls.filter(([, init]) => init?.method && init.method !== "GET")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Save candidates to review queue" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved 1 candidate to the durable review queue");
    expect(queueBody).toEqual({ baseline_scan_id: "s1", current_scan_id: "s2", baseline_version: 2, current_version: 2,
      candidate_offset: 0, candidate_limit: 50, review_token: "a".repeat(64) });
    expect(calls.mock.calls.filter(([, init]) => init?.method && init.method !== "GET")).toHaveLength(2);
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

describe("Absence review queue", () => {
  it("records a keep-active decision with the displayed version and rationale", async () => {
    const candidate = { finding_id: "finding-1", baseline_observation_id: "observation-1",
      reviewable_baseline_observation_count: 1, asset_id: "asset-1", description: "Synthetic finding",
      category: "TEST-1", domain: "network_config", severity: "high", workflow_status: "open", workflow_version: 3,
      baseline_recorded_at: "2026-11-05T12:00:00Z" };
    const comparison = { reviewed_at: "2026-11-05T14:00:00Z", baseline: view,
      current: { ...view, scan: { ...view.scan, id: "s2", filename: "current.csv" } },
      identity_review_fingerprint: "fingerprint" };
    const pending = { id: "item-1", batch_id: "batch-1", candidate, comparison, state: "pending" as const,
      decision_version: 0, rationale: null, actor_label: null, decided_at: null, created_at: "2026-11-05T14:00:00Z" };
    let latest: AbsenceReviewQueueItem = pending, decisionBody: unknown;
    const calls = mockApi({
      "GET /orgs/o1/scans/absence-review-queue": () => ({ items: [latest], total: 1, limit: 50, offset: 0 }),
      "POST /orgs/o1/scans/absence-review-queue/item-1/decision": init => {
        decisionBody = JSON.parse(String(init.body));
        latest = { ...pending, state: "kept_active", decision_version: 1, rationale: "Still valid in inventory",
          actor_label: "Reviewer", decided_at: "2026-11-05T15:00:00Z" };
        return latest;
      },
    });
    render(<ScanSnapshotQueueDialog orgId="o1" orgName="Synthetic org" writer onClose={vi.fn()} />);
    expect(await screen.findByText("Synthetic finding · high")).toBeVisible();
    expect(screen.getByText(/neither action changes finding workflow/)).toBeVisible();
    await userEvent.type(screen.getByLabelText("Review rationale"), "Still valid in inventory");
    await userEvent.click(screen.getByRole("button", { name: "Keep finding active" }));
    expect(await screen.findByText(/Kept active by Reviewer/)).toBeVisible();
    expect(decisionBody).toEqual({ expected_version: 0, action: "keep_active", rationale: "Still valid in inventory" });
    expect(calls.mock.calls.filter(([, init]) => init?.method && init.method !== "GET")).toHaveLength(1);
  });

  it("keeps viewer queue access read-only", async () => {
    mockApi({ "GET /orgs/o1/scans/absence-review-queue": () => ({ items: [], total: 0, limit: 50, offset: 0 }) });
    render(<ScanSnapshotQueueDialog orgId="o1" orgName="Synthetic org" writer={false} onClose={vi.fn()} />);
    expect(await screen.findByText("No candidates in this queue view.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Keep finding active" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Review rationale")).not.toBeInTheDocument();
  });

  it("surfaces queue load errors and supports retry", async () => {
    let attempts = 0;
    mockApi({ "GET /orgs/o1/scans/absence-review-queue": () => {
      attempts += 1;
      return attempts === 1 ? json({ detail: "Queue temporarily unavailable" }, 503)
        : { items: [], total: 0, limit: 50, offset: 0 };
    } });
    render(<ScanSnapshotQueueDialog orgId="o1" orgName="Synthetic org" writer={false} onClose={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Queue temporarily unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Retry queue" }));
    expect(await screen.findByText("No candidates in this queue view.")).toBeVisible();
    expect(attempts).toBe(2);
  });
});


it("blocks queue dismissal and navigation while a decision is saving", async () => {
  let release!: (value: unknown) => void;
  const held = new Promise(resolve => { release = resolve; });
  const item = { id: "held-item", batch_id: "b", state: "pending", decision_version: 0,
    candidate: { finding_id: "f", description: "Held finding", severity: "high", domain: "network_config", workflow_status: "open", baseline_recorded_at: "2026-11-05T12:00:00Z" },
    comparison: { baseline: view, current: view }, created_at: "2026-11-05T12:00:00Z" };
  const onClose = vi.fn();
  mockApi({ "GET /orgs/o1/scans/absence-review-queue": () => ({items: [item], total: 100, limit: 50, offset: 0}),
    "POST /orgs/o1/scans/absence-review-queue/held-item/decision": () => held });
  render(<ScanSnapshotQueueDialog orgId="o1" orgName="Synthetic org" writer onClose={onClose} />);
  await userEvent.type(await screen.findByLabelText("Review rationale"), "Reviewed snapshot");
  await userEvent.click(screen.getByRole("button", {name: "Keep finding active"}));
  try {
    expect(screen.getByRole("button", {name: "Close"})).toBeDisabled();
    expect(screen.getByRole("combobox", {name: "Show"})).toBeDisabled();
    expect(screen.getByRole("button", {name: "Next"})).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  } finally { release(item); }
});


it("retains a conflicting queue rationale and requires an explicit reload before retry", async () => {
  let version = 0, attempts = 0, lastBody: { expected_version: number } | undefined;
  const item = { id: "conflict-item", batch_id: "b", state: "pending", decision_version: 0,
    candidate: { finding_id: "f", description: "Conflicting finding", severity: "high", domain: "network_config", workflow_status: "open", baseline_recorded_at: "2026-11-05T12:00:00Z" },
    comparison: { baseline: view, current: view }, created_at: "2026-11-05T12:00:00Z" };
  const calls = mockApi({
    "GET /orgs/o1/scans/absence-review-queue": () => ({items: [{...item, decision_version: version}], total: 1, limit: 50, offset: 0}),
    "POST /orgs/o1/scans/absence-review-queue/conflict-item/decision": init => {
      lastBody = JSON.parse(String(init.body)); attempts++;
      if (attempts === 1) { version = 2; return json({detail: "Another reviewer changed this item"}, 409); }
      return {...item, state: "kept_active", decision_version: 3};
    },
  });
  render(<ScanSnapshotQueueDialog orgId="o1" orgName="Synthetic org" writer onClose={vi.fn()} />);
  await userEvent.type(await screen.findByLabelText("Review rationale"), "Preserve my rationale");
  await userEvent.click(screen.getByRole("button", {name: "Keep finding active"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Another reviewer");
  expect(screen.getByLabelText("Review rationale")).toHaveValue("Preserve my rationale");
  expect(screen.getByRole("button", {name: "Keep finding active"})).toBeDisabled();
  expect(calls.mock.calls.filter(([url, init]) => url.includes("absence-review-queue") && (init?.method ?? "GET") === "GET")).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", {name: "Reload queue"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Keep finding active"})).toBeEnabled());
  await userEvent.click(screen.getByRole("button", {name: "Keep finding active"}));
  await waitFor(() => expect(attempts).toBe(2));
  expect(lastBody?.expected_version).toBe(2);
});

it("never appends candidates from a changed comparison snapshot", async () => {
  let requests = 0;
  const candidate = { finding_id: "old", description: "Old candidate", severity: "high", domain: "network_config", workflow_status: "open", baseline_recorded_at: "2026-11-05T12:00:00Z" };
  mockApi({"GET /orgs/o1/scans/s1/snapshot": () => view, "GET /orgs/o1/scans/s2/snapshot": () => view,
    "POST /orgs/o1/scans/snapshot-comparison": () => {
      requests++;
      return {reviewed_at: "2026-11-05T14:00:00Z", baseline: view, current: view,
        declared_metadata_matches: true, absence_eligible: true, blocking_reasons: [], absence_blockers: [], scope_differences: {},
        baseline_reviewable_observations: 2, baseline_unreviewable_observations: 0, current_reviewable_observations: 1,
        current_unreviewable_observations: 0, ambiguous_baseline_identity_count: 0,
        review_token: (requests === 1 ? "a" : "b").repeat(64), candidate_count: 2, candidate_offset: requests === 2 ? 1 : 0, candidate_limit: 1,
        review_candidates: [requests === 1 ? candidate : {...candidate, finding_id: "new", description: "New candidate"}]};
    }});
  render(<ScanSnapshotComparisonDialog orgId="o1" orgName="Synthetic org" baselineId="s1" currentId="s2" onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Compare scans and build review list"})).toBeEnabled());
  await userEvent.click(screen.getByRole("button", {name: "Compare scans and build review list"}));
  await userEvent.click(await screen.findByRole("button", {name: "Load more candidates"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("changed while loading candidates");
  expect(screen.queryByRole("region", {name: "Comparison result"})).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", {name: "Compare scans and build review list"}));
  expect(await screen.findByText(/^New candidate/)).toBeVisible();
  expect(screen.queryByText(/^Old candidate/)).not.toBeInTheDocument();
});
