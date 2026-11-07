import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { mockApi, json } from "@/test/helpers";
import FindingIdentityBinding from "./FindingIdentityBinding";
const path = "/orgs/o1/findings/f1/observations/obs1/identity-binding";
const asset = "33333333-3333-4333-8333-333333333333";
const tool = { id: "t1", name: "Reviewed scanner", version: 1, active: true };
const view = { asset_identity: { asset_id: asset }, identity_binding: null };
const props = { orgId: "o1", findingId: "f1", observationId: "obs1", disabled: false, onSaved: vi.fn() };
async function open() {
  await userEvent.click(screen.getByRole("button", { name: "Review identity binding" }));
  await screen.findByRole("option", { name: "Reviewed scanner" });
}
async function fill() {
  await userEvent.selectOptions(screen.getByLabelText("Registered tool instance"), "t1");
  await userEvent.type(screen.getByLabelText("Identity review reason"), "Reviewed scanner and host");
  await userEvent.click(screen.getByLabelText(/I verified the scanner/));
}
it("loads only on demand and saves the explicit tool and canonical asset without merging", async () => {
  let body: unknown;
  const calls = mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool],
    ["PUT " + path]: init => { body = JSON.parse(String(init.body)); return view; } });
  const busy = vi.fn(); render(<FindingIdentityBinding {...props} onBusyChange={busy} />);
  expect(calls).not.toHaveBeenCalled(); await open(); await fill();
  await userEvent.click(screen.getByRole("button", { name: "Save identity binding" }));
  await waitFor(() => expect(body).toEqual({ expected_version: 0, tool_id: "t1", expected_tool_version: 1,
    canonical_asset_id: asset, confirm_mapping: true, rationale: "Reviewed scanner and host" }));
  expect(busy).toHaveBeenCalledWith(true); await waitFor(() => expect(busy).toHaveBeenLastCalledWith(false));
});
it("retains the draft on a version conflict and requires explicit reload", async () => {
  mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool],
    ["PUT " + path]: () => json({detail:"Identity binding changed; reload before retrying"},409) });
  render(<FindingIdentityBinding {...props} />); await open(); await fill();
  await userEvent.click(screen.getByRole("button", { name: "Save identity binding" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Identity binding changed");
  expect(screen.getByRole("button", { name: "Save identity binding" })).toBeDisabled();
  expect(screen.getByLabelText("Identity review reason")).toHaveValue("Reviewed scanner and host");
  await userEvent.click(screen.getByRole("button", { name: "Reload identity context" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save identity binding" })).toBeEnabled());
  expect(screen.getByLabelText(/I verified the scanner/)).not.toBeChecked();
});
it("cancels a review without writes and preserves explicit background-operation wording", async () => {
  const calls=mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool] });
  render(<FindingIdentityBinding {...props} />); await open();
  await userEvent.click(screen.getByRole("button", {name:"Cancel identity review"}));
  expect(screen.getByRole("button", {name:"Review identity binding"})).toBeVisible();
  expect(calls.mock.calls.every(([,init]) => !init?.method || init.method === "GET")).toBe(true);
});

it("registers a namespace without closing or discarding the binding draft", async () => {
  let created = false;
  mockApi({ ["GET " + path]: () => view,
    "GET /orgs/o1/identity-tools": () => created ? [tool] : [],
    "POST /orgs/o1/identity-tools": () => { created = true; return tool; } });
  const saved=vi.fn(); render(<FindingIdentityBinding {...props} onSaved={saved} />);
  await userEvent.click(screen.getByRole("button", {name:"Review identity binding"}));
  await waitFor(() => expect(screen.getByLabelText("Identity review reason")).toBeEnabled());
  await userEvent.type(screen.getByLabelText("Identity review reason"), "Retain this review draft");
  await userEvent.click(screen.getByText("Register a tool instance", {exact:true}));
  await userEvent.type(screen.getByLabelText("Tool instance name"), "Reviewed scanner");
  await userEvent.click(screen.getByRole("button", {name:"Register tool instance"}));
  await screen.findByRole("option", {name:"Reviewed scanner"});
  expect(screen.getByLabelText("Identity review reason")).toHaveValue("Retain this review draft");
  expect(screen.getByRole("region", {name:"Review identity binding"})).toBeVisible();
  expect(saved).not.toHaveBeenCalled();
});

it("requires fresh confirmation after changing the canonical asset or scanner", async () => {
  mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool, {...tool,id:"t2",name:"Other scanner"}] });
  render(<FindingIdentityBinding {...props} />); await open(); await fill();
  await userEvent.clear(screen.getByLabelText("Canonical asset UUID"));
  await userEvent.type(screen.getByLabelText("Canonical asset UUID"), "44444444-4444-4444-8444-444444444444");
  expect(screen.getByLabelText(/I verified the scanner/)).not.toBeChecked();
  await userEvent.click(screen.getByLabelText(/I verified the scanner/));
  await userEvent.selectOptions(screen.getByLabelText("Registered tool instance"), "t2");
  expect(screen.getByLabelText(/I verified the scanner/)).not.toBeChecked();
});
it("abandons confirmation and draft choices when a cancelled review is reopened", async () => {
  mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool] });
  render(<FindingIdentityBinding {...props} />); await open(); await fill();
  await userEvent.click(screen.getByRole("button", {name:"Cancel identity review"}));
  await open();
  expect(screen.getByLabelText(/I verified the scanner/)).not.toBeChecked();
  expect(screen.getByLabelText("Registered tool instance")).toHaveValue("");
  expect(screen.getByLabelText("Identity review reason")).toHaveValue("");
});
it("freezes and names the tool being retired while confirmation is open", async () => {
  mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool] });
  render(<FindingIdentityBinding {...props} />); await open(); await fill();
  await userEvent.click(screen.getByRole("button", {name:"Retire selected tool instance"}));
  expect(screen.getByRole("group", {name:"Retire identity tool"})).toHaveTextContent("Reviewed scanner");
  expect(screen.getByLabelText("Registered tool instance")).toBeDisabled();
  expect(screen.getByRole("button", {name:"Save identity binding"})).toBeDisabled();
});

it("keeps a newly registered instance selectable even beyond the first tools page", async () => {
  const page = Array.from({length:100},(_,i)=>({...tool,id:`old-${i}`,name:`A scanner ${i}`}));
  const created = {...tool,id:"new",name:"Z created scanner"};
  mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => page,
    "POST /orgs/o1/identity-tools": () => created });
  render(<FindingIdentityBinding {...props} />);
  await userEvent.click(screen.getByRole("button", {name:"Review identity binding"}));
  await waitFor(() => expect(screen.getByLabelText("Identity review reason")).toBeEnabled());
  await userEvent.type(screen.getByLabelText("Identity review reason"), "Create another scanner namespace");
  await userEvent.click(screen.getByText("Register a tool instance", {exact:true}));
  await userEvent.type(screen.getByLabelText("Tool instance name"), created.name);
  await userEvent.click(screen.getByRole("button", {name:"Register tool instance"}));
  expect(await screen.findByRole("option", {name:created.name})).toBeInTheDocument();
  expect(screen.getByLabelText("Registered tool instance")).toHaveValue("new");
});

it("uses a blocking retirement dialog with Cancel focus and Escape without writes", async () => {
  const calls=mockApi({ ["GET " + path]: () => view, "GET /orgs/o1/identity-tools": () => [tool] });
  render(<FindingIdentityBinding {...props} />); await open(); await fill();
  await userEvent.click(screen.getByRole("button", {name:"Retire selected tool instance"}));
  const dialog=screen.getByRole("dialog", {name:"Retire identity tool"});
  expect(dialog).toHaveAttribute("open");
  expect(dialog).toHaveAttribute("aria-modal","true");
  expect(within(dialog).getByRole("button", {name:"Cancel"})).toHaveFocus();
  fireEvent(dialog,new Event("cancel",{cancelable:true}));
  expect(screen.queryByRole("dialog", {name:"Retire identity tool"})).not.toBeInTheDocument();
  expect(screen.getByLabelText("Registered tool instance")).toBeEnabled();
  expect(calls.mock.calls.every(([,init])=>!init?.method || init.method === "GET")).toBe(true);
});
