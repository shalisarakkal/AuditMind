import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockApi, json, callsTo } from "@/test/helpers";
import type { Catalog, Control, ControlMapping, MappingDecision } from "@/lib/controlCatalog";
import ControlMappingDialog from "./ControlMappingDialog";
import ControlMappingWorkspace from "./ControlMappingWorkspace";

const findingId = "11111111-1111-4111-8111-111111111111";
const path = `/orgs/o/findings/${findingId}/control-mapping`;
const catalog: Catalog = { id: "c", framework: "SYNTHETIC", edition: "test-1", title: "Synthetic catalog", source: "local:synthetic", rights: "Synthetic fixture only", content_hash: "a".repeat(64), installed_at: "2026-11-16T12:00:00Z" };
const control: Control = { control_id: "k", reference: "TEST-1", title: "TEST-1: Synthetic outcome", description: "Synthetic expected outcome" };
const decision: MappingDecision = { id: "d", version: 1, state: "proposed", proposal_version: null, catalog, controls: [control], rationale: "Reviewed synthetic proposal", actor_label: "Reviewer", created_at: "2026-11-16T12:00:00Z" };
const mapping: ControlMapping = { available: true, finding_id: findingId, source: "manual", domain: "identity_access", category: "Synthetic category", archived: false, inactive: false, version: 0, rule_id: null, status: "unmapped", effective: null, proposal: null };
function setup(routes: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({ "GET /orgs/o/control-catalogs": () => ({ available: true, items: [catalog] }), "GET /orgs/o/control-catalogs/c": () => ({ catalog, controls: [control] }), ["GET " + path]: () => mapping, ...routes });
}
async function edit() {
  await userEvent.click(await screen.findByLabelText(control.title));
  await userEvent.type(screen.getByLabelText("Review rationale"), "Synthetic relevance reviewed");
}

describe("Control mapping review", () => {
  it("submits a fixed category scope and catalog revision only after explicit proposal", async () => {
    const changed = vi.fn(), close = vi.fn();
    const calls = setup({ ["POST " + path + "/proposals"]: () => ({ ...mapping, version: 1, proposal: decision }) });
    render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={mapping} catalogs={[catalog]} action="propose" onClose={close} onChanged={changed} />);
    expect(screen.getByRole("button", { name: "Save proposal" })).toBeDisabled();
    await edit();
    expect(callsTo(calls, "POST " + path + "/proposals")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Save proposal" }));
    expect(changed).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce();
    expect(JSON.parse(String(callsTo(calls, "POST " + path + "/proposals")[0][1].body))).toEqual({ source: "manual", domain: "identity_access", category: "Synthetic category", expected_version: 0, rationale: "Synthetic relevance reviewed", catalog_id: "c", control_ids: ["k"] });
  });
  it("does not offer an unchanged proposal save", async () => {
    setup(); render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={{ ...mapping, version: 1, proposal: decision }} catalogs={[catalog]} action="propose" onClose={vi.fn()} onChanged={vi.fn()} />);
    expect(await screen.findByLabelText(control.title)).toBeChecked();
    expect(screen.getByRole("button", { name: "Save proposal" })).toBeDisabled();
  });
  it("requires reselection when changing catalog release even if control IDs are stable", async () => {
    const newer = { ...catalog, id: "c2", edition: "synthetic-revision-2", content_hash: "b".repeat(64) };
    const changedControl = { ...control, title: "TEST-1: Synthetic later outcome", description: "Synthetic revised description" };
    const calls = setup({ "GET /orgs/o/control-catalogs/c2": () => ({ catalog: newer, controls: [changedControl] }), ["POST " + path + "/proposals"]: () => ({ ...mapping, version: 2 }) });
    render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={{ ...mapping, version: 1, proposal: decision }} catalogs={[catalog, newer]} action="propose" onClose={vi.fn()} onChanged={vi.fn()} />);
    expect(await screen.findByLabelText(control.title)).toBeChecked();
    await userEvent.selectOptions(screen.getByLabelText("Catalog release"), "c2");
    expect(await screen.findByLabelText(changedControl.title)).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Save proposal" })).toBeDisabled();
    await userEvent.click(screen.getByLabelText(changedControl.title));
    await userEvent.click(screen.getByRole("button", { name: "Save proposal" }));
    expect(JSON.parse(String(callsTo(calls, "POST " + path + "/proposals")[0][1].body))).toMatchObject({ expected_version: 1, catalog_id: "c2", control_ids: ["k"] });
  });
  it("blocks dismissal and duplicate submission until the review finishes", async () => {
    let release!: (response: Response) => void;
    const held = new Promise<Response>(resolve => { release = resolve; });
    const close = vi.fn(), calls = setup({ ["POST " + path + "/proposals"]: () => held });
    render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={mapping} catalogs={[catalog]} action="propose" onClose={close} onChanged={vi.fn()} />);
    await edit(); await userEvent.click(screen.getByRole("button", { name: "Save proposal" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }));
    expect(close).not.toHaveBeenCalled(); expect(callsTo(calls, "POST " + path + "/proposals")).toHaveLength(1);
    await act(async () => { release(json(mapping)); }); expect(close).toHaveBeenCalledOnce();
  });
  it.each([409, 503])("retains the draft after HTTP %s and never retries automatically", async status => {
    const changed = vi.fn(), close = vi.fn(), calls = setup({ ["POST " + path + "/proposals"]: () => json({ detail: "Synthetic refusal" }, status) });
    render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={mapping} catalogs={[catalog]} action="propose" onClose={close} onChanged={changed} />);
    await edit(); await userEvent.click(screen.getByRole("button", { name: "Save proposal" }));
    const alert = await screen.findByRole("alert"); expect(alert).toHaveTextContent("Closing does not undo");
    if (status === 503) expect(alert).toHaveTextContent("Outcome unknown");
    expect(screen.getByLabelText("Review rationale")).toHaveValue("Synthetic relevance reviewed");
    expect(screen.getByRole("button", { name: "Save proposal" })).toBeDisabled();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }));
    expect(changed).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce(); expect(callsTo(calls, "POST " + path + "/proposals")).toHaveLength(1);
  });
  it("shows both the effective and pending controls when withdrawing them", async () => {
    setup(); const effective = { ...decision, id: "approved", state: "approved" as const, controls: [{ ...control, control_id: "old", title: "Previously approved outcome" }] };
    render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={{ ...mapping, version: 3, effective, proposal: decision }} catalogs={[catalog]} action="withdraw" onClose={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.getByText("Previously approved outcome")).toBeVisible(); expect(screen.getByText(control.title)).toBeVisible();
  });
  it("keeps unmapped findings visible and viewers read-only", async () => {
    setup(); render(<ControlMappingWorkspace orgId="o" orgName="Organization" role="viewer" initialFindingId={findingId} />);
    expect(await screen.findByRole("heading", { name: "Unmapped" })).toBeVisible();
    expect(screen.getByText(/does not indicate a control pass or failure/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Propose mapping" })).not.toBeInTheDocument();
  });
  it("reviews a retained rule without inventing a finding reference", async () => {
    const retained = { ...mapping, context_kind: "rule" as const, finding_id: null, rule_id: "retained-rule", version: 2, status: "mapped" as const, effective: { ...decision, state: "approved" as const, version: 2 } };
    const endpoint = "/orgs/o/control-rules/retained-rule/withdraw";
    const calls = setup({ ["POST " + endpoint]: () => ({ ...retained, version: 3, status: "unmapped" }) });
    render(<ControlMappingDialog orgId="o" orgName="Organization" mapping={retained} catalogs={[catalog]} action="withdraw" onClose={vi.fn()} onChanged={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Review rationale"), "Retire policy after source purge");
    await userEvent.click(screen.getByRole("button", { name: "Withdraw mapping" }));
    expect(callsTo(calls, "POST " + endpoint)).toHaveLength(1);
    expect(JSON.parse(String(callsTo(calls, "POST " + endpoint)[0][1].body))).toMatchObject({ expected_version: 2, source: "manual", category: "Synthetic category" });
  });
  it("can open retained rule context when no source finding remains", async () => {
    const rule = "33333333-3333-4333-8333-333333333333";
    setup({ [`GET /orgs/o/control-rules/${rule}`]: () => ({ ...mapping, context_kind: "rule", finding_id: null, rule_id: rule, version: 2, status: "mapped", effective: { ...decision, state: "approved", version: 2 } }) });
    render(<ControlMappingWorkspace orgId="o" orgName="Organization" role="admin" initialRuleId={rule} />);
    expect(await screen.findByRole("heading", { name: "Approved category mapping" })).toBeVisible();
    expect(screen.getByLabelText("Rule ID")).toHaveValue(rule);
    expect(screen.getByRole("button", { name: "Withdraw mapping" })).toBeEnabled();
  });
  it("can switch to a rule lookup while a finding read is pending", async () => {
    let finish!: (response: Response) => void;
    const held = new Promise<Response>(resolve => { finish = resolve; });
    const rule = "33333333-3333-4333-8333-333333333333";
    setup({ ["GET " + path]: () => held, [`GET /orgs/o/control-rules/${rule}`]: () => ({ ...mapping, context_kind: "rule", finding_id: null, rule_id: rule, category: "Retained pending-read category" }) });
    render(<ControlMappingWorkspace orgId="o" orgName="Organization" role="admin" initialFindingId={findingId} />);
    await screen.findByText("Loading mapping context…");
    try {
      await userEvent.selectOptions(screen.getByLabelText("Lookup by"), "rule");
      await userEvent.type(screen.getByLabelText("Rule ID"), rule);
      const button = screen.getByRole("button", { name: "Open / reload rule" });
      expect(button).toBeEnabled();
      await userEvent.click(button);
      expect(await screen.findByText("Retained pending-read category")).toBeVisible();
    } finally { await act(async () => { finish(json(mapping)); }); }
  });
});
