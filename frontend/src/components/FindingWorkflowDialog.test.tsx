import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FindingWorkflowDialog from "./FindingWorkflowDialog";
import { json, mockApi } from "@/test/helpers";

const row = { finding_id: "f1", status: "open", version: 4, assignee_id: null, assignee_available: false, due_date: null, risk_review_date: null, updated_at: null };
const base = { orgId: "o1", orgName: "Synthetic org", role: "admin", ids: ["f1"], onClose: vi.fn(), onSaved: vi.fn() };
function routes(extra = {}) {
  return mockApi({ "GET /orgs/o1/findings/f1/workflow": () => row,
    "GET /orgs/o1/findings/f1/workflow/history": () => [],
    "GET /orgs/o1/members": () => ({ items: [{ id: "u1", name: "Owner", email: "owner@example.test", status: "active" }], total: 1 }), ...extra });
}
async function ready() { await waitFor(() => expect(screen.getByRole("button", { name: "Save workflow" })).toBeEnabled()); }

describe("Finding workflow", () => {
  it("never displays unchanged assignee IDs in a status-change history entry", async () => {
    const id = "cebff76d-e7ec-4564-87ed-2c56223cc80c";
    routes({ "GET /orgs/o1/findings/f1/workflow": () => ({ ...row, assignee_id: id, assignee_available: true, assignee_label: "Shali Arakkal" }),
      "GET /orgs/o1/findings/f1/workflow/history": () => [{ id: "h1", actor_label: "Admin", version: 4, created_at: "2026-10-23T12:00:00Z", rationale: "Reopen", verification: null,
        before: { status: "accepted_risk", assignee_id: id }, after: { status: "open", assignee_id: id }, before_assignee_label: "Shali Arakkal", after_assignee_label: "Shali Arakkal" }] });
    render(<FindingWorkflowDialog {...base} />); await ready();
    expect(screen.getByText("Shali Arakkal", { exact: true })).toBeVisible();
    await userEvent.click(await screen.findByText("Recorded changes"));
    expect(screen.getByText("Accepted risk → Open")).toBeVisible();
    expect(screen.queryByText(/Technical assignee IDs/)).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(id))).not.toBeInTheDocument();
    expect(screen.queryByText("Assignee:")).not.toBeInTheDocument();
  });
  it("uses an unavailable label rather than exposing a missing assignee name as an ID", async () => {
    routes({ "GET /orgs/o1/findings/f1/workflow": () => ({ ...row, assignee_id: "private-user-id", assignee_available: true, assignee_label: " " }) });
    render(<FindingWorkflowDialog {...base} />); await ready();
    expect(screen.getByText("Assignee unavailable")).toBeVisible();
    expect(screen.queryByText(/private-user-id/)).not.toBeInTheDocument();
  });
  it("searches and pages members without assigning, preserves a chosen email, and saves only on submit", async () => {
    const root = "GET /orgs/o1/members?limit=50&offset=";
    const suffix = "&search_scope=identity&status=active&status=locked&status=must_change_password";
    const fetch = routes({
      "GET /orgs/o1/members": () => ({ items: [{ id: "u1", name: "Owner", email: "owner@example.test", status: "active" }], total: 51 }),
      [root + "50&q=" + suffix]: () => ({ items: [{ id: "u2", name: "Second", email: "second@example.test", status: "active" }], total: 51 }),
      [root + "0&q=owner%2Btest%40example.test" + suffix]: () => ({ items: [{ id: "u3", name: " ", email: "owner+test@example.test", status: "active" }], total: 1 }),
      [root + "0&q=missing" + suffix]: () => ({ items: [], total: 0 }),
      "PATCH /orgs/o1/findings/f1/workflow": () => row,
    });
    render(<FindingWorkflowDialog {...base} />); await ready();
    await userEvent.click(screen.getByRole("button", { name: "More assignees" }));
    expect(await screen.findByRole("option", { name: "Second" })).toBeInTheDocument();
    const search = screen.getByLabelText("Find assignee");
    await userEvent.type(search, "owner+test@example.test");
    expect(await screen.findByRole("option", { name: "owner+test@example.test" })).toBeInTheDocument();
    expect(screen.getByLabelText("Assignee", { exact: true })).toHaveValue("keep");
    expect(screen.getByRole("button", { name: "Previous assignees" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Assignee", { exact: true }), "u3");
    await userEvent.clear(search); await userEvent.type(search, "missing");
    expect(await screen.findByText("No matching organization members.")).toBeVisible();
    expect(screen.getByRole("option", { name: "owner+test@example.test" })).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Rationale or note"), "Assign after search");
    await userEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    const patch = fetch.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ expected_version: 4, rationale: "Assign after search", assignee_id: "u3" });
  });
  it("sends the browser timezone only when explicitly setting a deadline", async () => {
    const original = Intl.DateTimeFormat().resolvedOptions();
    const spy = vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({ ...original, timeZone:"Asia/Kolkata" });
    try {
      let payload: Record<string, unknown> = {};
      routes({ "PATCH /orgs/o1/findings/f1/workflow": (init: RequestInit) => { payload = JSON.parse(String(init.body)); return row; } });
      render(<FindingWorkflowDialog {...base} />); await ready();
      await userEvent.selectOptions(screen.getByLabelText("Due date action"), "set");
      fireEvent.change(screen.getByLabelText("Due date", {exact:true}), {target:{value:"2026-10-25"}});
      await userEvent.type(screen.getByLabelText("Rationale or note"), "Local deadline");
      await userEvent.click(screen.getByRole("button", {name:"Save workflow"}));
      expect(payload).toMatchObject({due_date:"2026-10-25", deadline_timezone:"Asia/Kolkata"});
      expect(payload).not.toHaveProperty("risk_review_date");
    } finally { spy.mockRestore(); }
  });
  it("shows latest saved notes separately from new input and hides unchanged history fields", async () => {
    const stamp = { actor_label: "Admin", created_at: "2026-10-23T12:00:00Z" };
    routes({ "GET /orgs/o1/findings/f1/workflow": () => ({ ...row, latest_rationale: { ...stamp, text: "Latest decision" }, latest_verification: { ...stamp, text: "Earlier retest" } }),
      "GET /orgs/o1/findings/f1/workflow/history": () => [{ ...stamp, id: "h1", version: 4, rationale: "Assigned", verification: null,
        before: { assignee_id: null, due_date: "2026-10-30" }, after: { assignee_id: "u1", due_date: "2026-10-30" }, after_assignee_label: "Owner Name" }] });
    render(<FindingWorkflowDialog {...base} />); await ready();
    expect(screen.getByText("Latest decision")).toBeVisible();
    expect(screen.getByText("Earlier retest")).toBeVisible();
    expect(screen.getByLabelText("Rationale or note")).toHaveValue("");
    await userEvent.click(screen.getByText("Recorded changes"));
    expect(screen.getByText("Unassigned → Owner Name")).toBeVisible();
    expect(screen.queryByText(/2026-10-30/)).not.toBeInTheDocument();
    expect(screen.getByText("Technical finding IDs")).toBeVisible();
  });
  it("makes saved rationale and verification discoverable without refilling new-note fields", async () => {
    routes({ "GET /orgs/o1/findings/f1/workflow/history": () => [{ id: "h1", actor_label: "Admin", version: 4, created_at: "2026-10-23T12:00:00Z", rationale: "Approved patch", verification: "Rescan passed", before: {}, after: {} }] });
    render(<FindingWorkflowDialog {...base} />); await ready();
    expect(await screen.findByRole("link", { name: "Saved notes and history (1 on this page)" })).toBeVisible();
    expect(screen.getByText("Approved patch")).toBeVisible();
    expect(screen.getByText("Rescan passed")).toBeVisible();
    expect(screen.getByLabelText("Rationale or note")).toHaveValue("");
    expect(screen.getByLabelText("Verification note")).toHaveValue("");
    const section = screen.getByRole("region", { name: "Workflow history" });
    section.scrollIntoView = vi.fn();
    await userEvent.click(screen.getByRole("link", { name: /Saved notes and history/ }));
    expect(section.scrollIntoView).toHaveBeenCalled(); expect(section).toHaveFocus();
  });
  it("explains mixed selections and enables risk-date setting only for an explicit compatible target state", async () => {
    routes({ "GET /orgs/o1/findings/f2/workflow": () => ({ ...row, finding_id: "f2", status: "accepted_risk", risk_review_date: "2099-01-01" }) });
    render(<FindingWorkflowDialog {...base} ids={["f1", "f2"]} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply to 2 findings" })).toBeEnabled());
    expect(screen.getByRole("region", { name: "Selection summary" })).toHaveTextContent("1 Open · 1 Accepted risk");
    expect(screen.getByRole("option", { name: "Set risk review date" })).toBeDisabled();
    expect(screen.getByRole("option", { name: "Clear risk review date" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("New status"), "accepted_risk");
    expect(screen.getByRole("option", { name: "Set risk review date" })).toBeEnabled();
    await userEvent.selectOptions(screen.getByLabelText("Risk review action"), "set");
    await userEvent.selectOptions(screen.getByLabelText("New status"), "");
    expect(screen.getByRole("alert")).toHaveTextContent("every selected finding");
    expect(screen.getByRole("button", { name: "Apply to 2 findings" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Risk review action"), "keep");
    expect(screen.getByRole("button", { name: "Apply to 2 findings" })).toBeEnabled();
    expect(screen.getByLabelText("New status")).toHaveValue("");
  });
  it("permits all-accepted selections to set but not clear risk dates", async () => {
    routes({ "GET /orgs/o1/findings/f1/workflow": () => ({ ...row, status: "accepted_risk" }) });
    render(<FindingWorkflowDialog {...base} />); await ready();
    expect(screen.getByRole("option", { name: "Set risk review date" })).toBeEnabled();
    expect(screen.getByRole("option", { name: "Clear risk review date" })).toBeDisabled();
    expect(screen.getByLabelText("Rationale or note")).toBeRequired();
  });
  it("sends only explicit changes and the captured version", async () => {
    let payload: unknown;
    routes({ "PATCH /orgs/o1/findings/f1/workflow": (init: RequestInit) => { payload = JSON.parse(String(init.body)); return row; } });
    render(<FindingWorkflowDialog {...base} />); await ready();
    await userEvent.selectOptions(screen.getByLabelText("New status"), "resolved");
    await userEvent.type(screen.getByLabelText("Rationale or note"), "Patched");
    await userEvent.type(screen.getByLabelText("Verification note"), "Retested");
    await userEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    expect(payload).toEqual({ expected_version: 4, status: "resolved", rationale: "Patched", verification: "Retested" });
    expect(base.onSaved).toHaveBeenCalled();
  });
  it("keeps viewer read-only and still displays history", async () => {
    routes(); render(<FindingWorkflowDialog {...base} role="viewer" />);
    expect(await screen.findByText("No workflow history yet.")).toBeVisible();
    expect(screen.getByRole("note")).toHaveTextContent("Read-only access");
    expect(screen.queryByLabelText("New status")).not.toBeInTheDocument();
  });
  it("lets auditors append notes, not mutate accepted risk", async () => {
    routes({ "GET /orgs/o1/findings/f1/workflow": () => ({ ...row, status: "accepted_risk" }) });
    render(<FindingWorkflowDialog {...base} role="auditor" />); await ready();
    expect(screen.getByText(/auditors may add notes only/)).toBeVisible();
    expect(screen.queryByLabelText("New status")).not.toBeInTheDocument();
  });
  it("preserves the draft on conflict and requires explicit reload", async () => {
    routes({ "PATCH /orgs/o1/findings/f1/workflow": () => json({ detail: { code: "workflow_conflict", message: "Finding changed" } }, 409) });
    render(<FindingWorkflowDialog {...base} />); await ready();
    await userEvent.type(screen.getByLabelText("Rationale or note"), "Retain this note");
    await userEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No automatic retry");
    expect(screen.getByLabelText("Rationale or note")).toHaveValue("Retain this note");
    expect(screen.getByRole("button", { name: "Save workflow" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Reload latest state" })); await ready();
  });
  it("bulk confirms exact target count and versions", async () => {
    let payload: unknown;
    routes({ "GET /orgs/o1/findings/f2/workflow": () => ({ ...row, finding_id: "f2", version: 2 }),
      "POST /orgs/o1/findings/workflow/bulk": (init: RequestInit) => { payload = JSON.parse(String(init.body)); return []; } });
    render(<FindingWorkflowDialog {...base} ids={["f1", "f2"]} />);
    const save = screen.getByRole("button", { name: "Apply to 2 findings" });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.type(screen.getByLabelText("Rationale or note"), "Review both"); await userEvent.click(save);
    expect(payload).toEqual({ patch: { rationale: "Review both" }, targets: [{ finding_id: "f1", expected_version: 4 }, { finding_id: "f2", expected_version: 2 }] });
  });
  it("traps keyboard focus and restores focus on close", async () => {
    routes(); const trigger = document.createElement("button"); document.body.append(trigger); trigger.focus();
    const view = render(<FindingWorkflowDialog {...base} />); await ready();
    const first = screen.getByRole("button", { name: "Close finding workflow" });
    const last = screen.getByRole("button", { name: "Older history" });
    // Last history button is disabled without a full page; select the last enabled control.
    expect(last).toBeDisabled();
    const save = screen.getByRole("button", { name: "Save workflow" }); save.focus();
    fireEvent.keyDown(save, { key: "Tab" }); expect(first).toHaveFocus();
    view.unmount(); expect(trigger).toHaveFocus(); trigger.remove();
  });
  it("fails closed when workflow loading fails and supports retry", async () => {
    routes({ "GET /orgs/o1/findings/f1/workflow": () => json({ detail: "Unavailable" }, 503) });
    render(<FindingWorkflowDialog {...base} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
    expect(screen.getByRole("button", { name: "Save workflow" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reload latest state" })).toBeVisible();
  });
});
