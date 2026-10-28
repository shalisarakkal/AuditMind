import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, json } from "@/test/helpers";
import { useDashboardState, type DashboardState } from "./useDashboardState";

const baseline: DashboardState = { scoring_mode: "findings_based", settings_version: 0, evidence_revision: 1, evaluation_id: null };
const qualified: DashboardState = { scoring_mode: "evidence_qualified", settings_version: 1, evidence_revision: 2, evaluation_id: "new-job" };
function Probe({ orgId = "org-1" }: { orgId?: string }) {
  const { state, error } = useDashboardState(orgId);
  return <p>{error ? "error" : state ? state.scoring_mode : "no verified state"}</p>;
}
describe("Dashboard mode/revision freshness", () => {
  it("rejects an out-of-order older mode response", async () => {
    let resolve: (value: DashboardState) => void;
    const late = new Promise<DashboardState>(done => { resolve = done; });
    let requests = 0;
    mockApi({ "GET /orgs/org-1/scoring/dashboard-state": () => ++requests === 1 ? baseline : requests === 2 ? late : qualified });
    render(<Probe />);
    await screen.findByText("findings_based");
    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(requests).toBe(2));
    fireEvent(window, new Event("focus"));
    await screen.findByText("evidence_qualified");
    await act(async () => resolve!(baseline));
    expect(screen.getByText("evidence_qualified")).toBeVisible();
  });
  it("clears verification after a failed state check", async () => {
    let fail = false;
    mockApi({ "GET /orgs/org-1/scoring/dashboard-state": () => fail ? json({ detail: "Unavailable" }, 500) : qualified });
    render(<Probe />);
    await screen.findByText("evidence_qualified");
    fail = true; fireEvent(window, new Event("focus"));
    await screen.findByText("error");
    expect(screen.queryByText("evidence_qualified")).not.toBeInTheDocument();
  });
  it("never exposes a previous organization's late response", async () => {
    let resolve: (value: DashboardState) => void;
    const late = new Promise<DashboardState>(done => { resolve = done; });
    mockApi({ "GET /orgs/org-1/scoring/dashboard-state": () => late, "GET /orgs/org-2/scoring/dashboard-state": () => baseline });
    const view = render(<Probe />);
    view.rerender(<Probe orgId="org-2" />);
    await screen.findByText("findings_based");
    await act(async () => resolve!(qualified));
    expect(screen.getByText("findings_based")).toBeVisible();
  });
});
