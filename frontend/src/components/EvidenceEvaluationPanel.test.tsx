import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EvidenceEvaluationPanel, { type EvidenceEvaluationJob } from "./EvidenceEvaluationPanel";
import { mockApi } from "@/test/helpers";

const running: EvidenceEvaluationJob = { id: "job-1", status: "running", created_at: "2026-10-28T10:00:00Z", run_started_at: "2026-10-28T10:00:01Z", cancel_requested_at: null,
  can_cancel: true, is_current: false, error_message: null, progress: { phase: "assets", processed: 5000, total: 20000 }, result: null };

describe("background evidence evaluation", () => {
  it("hides completed progress after five seconds while retaining results", async () => {
    mockApi({ "GET /orgs/org-1/scoring/evaluations/current": () => ({ ...running, status: "completed", can_cancel: false, is_current: true,
      result: { evaluated_at: "2026-10-29T18:12:04Z", assessment_status: "not_assessed", qualified_domain_count: 0, domains: [] } }) });
    vi.useFakeTimers();
    const view = render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getByText("Evaluation completed.")).toBeVisible();
      // Reloading the same job must not restart its completion timeout.
      view.rerender(<EvidenceEvaluationPanel orgId="org-1" disabled={false} refreshSignal={1} />);
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(screen.queryByRole("status", { name: "Organization evaluation progress" })).not.toBeInTheDocument();
      expect(screen.getByText(/Coverage assessment:/)).toBeVisible();
      expect(screen.getByText(/Last evaluated:/)).toBeVisible();
    } finally { view.unmount(); vi.useRealTimers(); }
  });
  it("reopens the durable running job without submitting another scan", async () => {
    const api = mockApi({ "GET /orgs/org-1/scoring/evaluations/current": () => running });
    const view = render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    expect(await screen.findByRole("status", { name: "Organization evaluation progress" })).toHaveTextContent("5,000 / 20,000 records");
    expect(screen.getByRole("button", { name: "Evaluate evidence across all domains" })).toBeDisabled();
    view.unmount();
    render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    await screen.findByRole("button", { name: "Cancel operation" });
    expect(api.mock.calls.every(([, init]) => init?.method === "GET")).toBe(true);
  });
  it("does not offer cancellation of a colleague's shared job", async () => {
    mockApi({ "GET /orgs/org-1/scoring/evaluations/current": () => ({ ...running, can_cancel: false }) });
    render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    await screen.findByRole("status", { name: "Organization evaluation progress" });
    expect(screen.queryByRole("button", { name: "Cancel operation" })).not.toBeInTheDocument();
  });
  it("shows cancellation requested while the current batch drains", async () => {
    let job = running;
    mockApi({ "GET /orgs/org-1/scoring/evaluations/current": () => job,
      "POST /orgs/org-1/scoring/evaluations/job-1/cancel": () => { job = { ...running, cancel_requested_at: new Date().toISOString() }; return job; } });
    render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel operation" }));
    await screen.findByText(/Cancellation requested/);
    expect(screen.getByRole("button", { name: "Cancel operation" })).toBeDisabled();
    expect(screen.queryByText(/Coverage assessment:/)).not.toBeInTheDocument();
  });
  it("ignores a late initial read after submitting a new evaluation", async () => {
    let resolve: (value: null) => void;
    let reads = 0;
    const late = new Promise<null>(done => { resolve = done; });
    mockApi({ "GET /orgs/org-1/scoring/evaluations/current": () => ++reads === 1 ? null : reads === 2 ? late : running,
      "POST /orgs/org-1/scoring/evaluations": () => running });
    const view = render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    const button = screen.getByRole("button", { name: "Evaluate evidence across all domains" });
    await waitFor(() => expect(button).toBeEnabled());
    view.rerender(<EvidenceEvaluationPanel orgId="org-1" disabled={false} refreshSignal={1} />);
    await waitFor(() => expect(reads).toBe(2));
    fireEvent.click(button);
    await screen.findByRole("button", { name: "Cancel operation" });
    await act(async () => resolve!(null));
    expect(screen.getByRole("button", { name: "Cancel operation" })).toBeVisible();
  });
  it("does not imply a cancelled retry revoked an independently current earlier result", async () => {
    mockApi({ "GET /orgs/org-1/scoring/evaluations/current": () => ({ ...running, status: "cancelled", can_cancel: false }) });
    render(<EvidenceEvaluationPanel orgId="org-1" disabled={false} />);
    await screen.findByText(/An earlier completed evaluation may still be usable/);
    expect(screen.queryByText(/Coverage assessment:/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Evaluate evidence across all domains" })).toBeEnabled();
  });
});
