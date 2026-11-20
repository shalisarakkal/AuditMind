import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockApi, json, callsTo } from "@/test/helpers";
import FindingRemediationProof from "./FindingRemediationProof";

const path = "/orgs/o/findings/f/remediation-proof";
const empty = { version: 0, workflow_version: 2, state: "not_submitted", can_submit: true, can_review: false, self_review_required: false, records: [], next_before: null, blocked_reason: null };
const record = { id: "r1", version: 1, state: "pending", source_reference: "https://example.com/test", observed_at: "2026-11-16T12:00:00Z", created_at: "2026-11-16T13:00:00Z", actor_label: "Submitter", submitter_label: "Submitter", note: "Synthetic retest" };
const pending = { ...empty, version: 1, state: "pending", can_review: true, self_review_required: true, records: [record] };
async function open(disabled = false, busy = vi.fn(), hasWorkflowDraft = false) {
  render(<FindingRemediationProof orgId="o" findingId="f" disabled={disabled} hasWorkflowDraft={hasWorkflowDraft} onBusyChange={busy} />);
  await userEvent.click(screen.getByText("Remediation proof", { selector: "summary" }));
  await screen.findByRole("region", { name: "Remediation proof review" });
}
async function fill() {
  await userEvent.type(await screen.findByLabelText("Proof evidence reference"), "https://example.com/retest");
  fireEvent.change(screen.getByLabelText("Proof observed at"), { target: { value: "2026-11-16T10:00" } });
  await userEvent.type(screen.getByLabelText("Proof submission note"), "Synthetic retest attached");
}

describe("Remediation proof", () => {
  it("loads lazily and submits the captured proof/workflow versions", async () => {
    let state: typeof empty | typeof pending = empty;
    const calls = mockApi({ ["GET " + path]: () => state, ["POST " + path]: () => { state = pending; return pending; } });
    await open(); await fill();
    await userEvent.click(screen.getByRole("button", { name: "Submit remediation proof" }));
    expect(await screen.findByText("Verification pending. The workflow remains Open.")).toBeInTheDocument();
    const body = JSON.parse(String(callsTo(calls, "POST " + path)[0][1].body));
    expect(body).toMatchObject({ expected_version: 0, expected_workflow_version: 2, source_reference: "https://example.com/retest", note: "Synthetic retest attached" });
    expect(body.observed_at).toBe(new Date("2026-11-16T10:00").toISOString());
    expect(callsTo(calls, "PATCH /orgs/o/findings/f/workflow")).toHaveLength(0);
  });
  it("records rejection with a next action and explicit review acknowledgments", async () => {
    const rejected = { ...pending, version: 2, state: "rejected", can_review: false, records: [{ ...record, id: "r2", state: "rejected", note: "Patch and retest" }, record] };
    let state = pending;
    const calls = mockApi({ ["GET " + path]: () => state, ["POST " + path + "/review"]: () => { state = rejected; return rejected; } });
    await open();
    expect(await screen.findByLabelText("Proof decision")).toHaveValue("rejected");
    await userEvent.selectOptions(screen.getByLabelText("Proof decision"), "approved");
    expect(screen.getByRole("combobox", { name: "Proof decision" })).toHaveValue("approved");
    await userEvent.selectOptions(screen.getByLabelText("Proof decision"), "rejected");
    expect(screen.getByRole("combobox", { name: "Proof decision" })).toHaveValue("rejected");
    await userEvent.click(screen.getByLabelText("I reviewed the referenced remediation evidence."));
    await userEvent.click(screen.getByLabelText("I acknowledge reviewing remediation proof I submitted."));
    await userEvent.type(screen.getByLabelText("Proof review reason and next action"), "Patch and retest");
    await userEvent.click(screen.getByRole("button", { name: "Save proof decision" }));
    expect(await screen.findByText(/Proof rejected\. The finding remains Open/)).toBeInTheDocument();
    expect(JSON.parse(String(callsTo(calls, "POST " + path + "/review")[0][1].body))).toMatchObject({ decision: "rejected", evidence_reviewed: true, self_review_acknowledged: true, expected_version: 1 });
  });
  it("blocks duplicate requests and reports busy state to its workflow dialog", async () => {
    let release!: (response: Response) => void;
    const held = new Promise<Response>(resolve => { release = resolve; });
    const busy = vi.fn();
    const calls = mockApi({ ["GET " + path]: () => empty, ["POST " + path]: () => held });
    await open(false, busy); await fill();
    await userEvent.dblClick(screen.getByRole("button", { name: "Submit remediation proof" }));
    expect(screen.getByRole("button", { name: "Saving proof…" })).toBeDisabled();
    expect(callsTo(calls, "POST " + path)).toHaveLength(1);
    expect(busy).toHaveBeenCalledWith(true);
    await act(async () => { release(json(pending)); });
    expect(busy).toHaveBeenLastCalledWith(false);
  });
  it("retains conflict drafts and requires reload before another submission", async () => {
    const calls = mockApi({ ["GET " + path]: () => empty, ["POST " + path]: () => json({ detail: "Workflow changed" }, 409) });
    await open(); await fill();
    await userEvent.click(screen.getByRole("button", { name: "Submit remediation proof" }));
    expect(await screen.findByText("Reload remediation proof before retrying.")).toBeInTheDocument();
    expect(screen.getByLabelText("Proof submission note")).toHaveValue("Synthetic retest attached");
    expect(screen.getByRole("button", { name: "Submit remediation proof" })).toBeDisabled();
    expect(callsTo(calls, "POST " + path)).toHaveLength(1);
  });
  it("shows retained history to viewers without write controls", async () => {
    mockApi({ ["GET " + path]: () => ({ ...pending, can_submit: false, can_review: false }) });
    await open();
    expect(await screen.findByText("Synthetic retest")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save proof decision" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Proof action")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /example/ })).not.toBeInTheDocument();
  });
  it.each([0, 503])("requires reload after an unknown outcome (%s), then discovers the committed proof", async status => {
    let state: typeof empty | typeof pending = empty;
    const calls = mockApi({ ["GET " + path]: () => state, ["POST " + path]: () => {
      state = pending;
      if (status === 0) throw new Error("Synthetic dropped response");
      return json({ detail: "Synthetic response loss after commit" }, status);
    } });
    await open(); await fill();
    await userEvent.click(screen.getByRole("button", { name: "Submit remediation proof" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("save outcome is unknown");
    expect(screen.getByLabelText("Proof submission note")).toHaveValue("Synthetic retest attached");
    expect(screen.getByRole("button", { name: "Submit remediation proof" })).toBeDisabled();
    expect(callsTo(calls, "POST " + path)).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Reload remediation proof" }));
    expect(await screen.findByText("Verification pending. The workflow remains Open.")).toBeInTheDocument();
    expect(callsTo(calls, "POST " + path)).toHaveLength(1);
  });
  it("disables proof submission while the parent has a workflow draft", async () => {
    mockApi({ ["GET " + path]: () => empty });
    await open(false, vi.fn(), true);
    expect(await screen.findByText("Save or clear the workflow draft before submitting or reviewing remediation proof.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Submit remediation proof" })).toBeDisabled();
  });
  it("pages retained decisions without exposing actions against an old page", async () => {
    mockApi({ ["GET " + path]: () => ({ ...pending, next_before: 1 }), ["GET " + path + "?before=1"]: () => ({ ...pending, records: [], next_before: null }) });
    await open();
    await userEvent.click(await screen.findByRole("button", { name: "Older proof decisions" }));
    expect(await screen.findByText("No retained proof decisions.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Proof action")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Latest proof decisions" }));
    expect(await screen.findByLabelText("Proof action")).toBeInTheDocument();
  });
});
