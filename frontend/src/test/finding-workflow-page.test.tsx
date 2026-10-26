import { act, fireEvent, renderHook, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FindingsPage from "@/app/(app)/findings/page";
import { renderSignedIn } from "./helpers";
import { useSelection } from "@/lib/useSelection";
import { useListState } from "@/lib/useListState";

const nav = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: nav.replace }), usePathname: () => "/findings", useSearchParams: () => new URLSearchParams() }));
const item = (id: string, scan_id: string | null = null) => ({ id: `finding-${id}`, org_id: "org-1", scan_id, asset_id: null, category: null,
  domain: "network_config", severity: "high", description: id, source: "synthetic", created_at: "2026-10-23T00:00:00Z",
  asset_hostname: null, asset_ip: null, asset_cloud_id: null, workflow_status: "open", workflow_version: 0 });
const routes = { "GET /orgs/org-1/import-profiles": () => [],
  "GET /orgs/org-1/findings": () => ({ items: [item("manual"), item("imported", "s1")], total: 2, domain_counts: { network_config: 2 } }),
  "GET /orgs/org-1/findings/facets": () => ({ source: ["synthetic"], workflow_status: ["open", "accepted_risk"], assignee: [{ value: "unassigned", label: "Unassigned" }] }) };

describe("Findings workflow list", () => {
  it("retains manual/imported eligibility across pages", async () => {
    let second = false;
    await renderSignedIn(<FindingsPage />, "admin", { ...routes,
      "GET /orgs/org-1/findings": () => ({ items: second ? [item("imported", "s1")] : [item("manual")], total:101, domain_counts:{} }) });
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select all on this page" }));
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeEnabled();
    second = true; fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select imported" }));
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Update selected workflow" })).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select imported" }));
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Update selected workflow" })).toBeEnabled();
  });
  it("freezes bulk archive targets at confirmation and clears selection after success", async () => {
    const { fetchMock } = await renderSignedIn(<FindingsPage />, "admin", { ...routes,
      "GET /orgs/org-1/findings": () => ({ items: [item("manual"), item("other")], total:2, domain_counts:{} }),
      "POST /orgs/org-1/archive-jobs/bulk": () => ({ jobs:[], refused:[] }),
    });
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select all on this page" }));
    fireEvent.click(screen.getByRole("button", { name: "Archive selected" }));
    const confirm = screen.getByRole("group", { name: "Archive selected findings" });
    expect(confirm).toHaveTextContent("Archive 2 findings");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select other" }));
    expect(screen.getByRole("dialog", { name: "Archive selected findings" })).toHaveAttribute("open");
    fireEvent.click(within(confirm).getByRole("button", { name: "Archive 2 findings" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => url.endsWith('/archive-jobs/bulk') && init?.method === 'POST');
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ action:"archive", item_type:"finding", ids:["finding-manual", "finding-other"] });
    });
    await waitFor(() => expect(screen.queryByRole("group", { name: "Selected" })).not.toBeInTheDocument());
  });
  it("caps a unified selection at 500 and keeps viewer workflow in row Actions", async () => {
    const view = renderHook(() => useSelection(useListState(100, "org-1"), "org-1", 500));
    act(() => view.result.current.set(Array.from({ length:501 }, (_, i) => ({ id:`f-${i}`, name:`Finding ${i}`, metadata:{manual:true} })), true));
    expect(view.result.current.count).toBe(500);
    expect(view.result.current.full).toBe(true);
    expect(view.result.current.has("f-500")).toBe(false);
    expect(view.result.current.metadata("f-0")).toEqual({manual:true});
    view.unmount();
    await renderSignedIn(<FindingsPage />, "viewer", routes);
    const row = (await screen.findByText("manual", { exact: true })).closest("tr")!;
    const workflow = within(row).getByRole("button", { name: "Workflow" });
    expect(workflow.closest("td")).toHaveClass("sticky", "right-0");
    expect(screen.queryByRole("checkbox", { name: /^Select/ })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Archive manual" })).not.toBeInTheDocument();
  });
  it("keeps date-only filters and sends the browser timezone for full-day processing", async () => {
    const { fetchMock } = await renderSignedIn(<FindingsPage />, "admin", routes);
    await screen.findByText("manual", {exact:true});
    const from=screen.getByLabelText("Added from"), to=screen.getByLabelText("Added to");
    expect(from).toHaveAttribute("type","date"); expect(to).toHaveAttribute("type","date");
    fireEvent.change(from,{target:{value:"2026-10-25"}});
    fireEvent.change(to,{target:{value:"2026-10-25"}});
    await waitFor(()=>{
      const request=fetchMock.mock.calls.filter(([url])=>url.includes('/findings?')).at(-1)![0];
      const query=new URL(request,'http://localhost').searchParams;
      expect(query.get('since')).toBe('2026-10-25'); expect(query.get('until')).toBe('2026-10-25');
      expect(query.get('filter_timezone')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
    });
  });
  it("disables manual archiving for uploaded-only organizations and explains manual entry", async () => {
    await renderSignedIn(<FindingsPage />, "admin", { ...routes,
      "GET /orgs/org-1/findings": () => ({ items: [item("imported", "s1")], total:1, domain_counts:{} }),
      "GET /orgs/org-1/findings/facets": () => ({source:["synthetic"],has_manual_findings:false}) });
    await screen.findByText("imported", {exact:true});
    expect(screen.queryByLabelText("Select for")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select imported" }));
    expect(screen.getByRole("button", {name:"Archive selected"})).toBeDisabled();
    expect(screen.getByText(/No active manual findings/)).toBeVisible();
    expect(screen.getByRole("button", {name:"Add finding"})).toBeVisible();
  });
  it("offers both bulk actions, blocks mixed archive selections and resets on filter change", async () => {
    await renderSignedIn(<FindingsPage />, "admin", routes);
    const imported = await screen.findByRole("checkbox", { name: "Select imported" });
    expect(imported).toBeEnabled(); fireEvent.click(imported);
    expect(screen.getByRole("group", { name: "Selected" })).toHaveTextContent("1 selected");
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Update selected workflow" })).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select manual" }));
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeDisabled();
    fireEvent.click(imported);
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeEnabled();
    const row = screen.getByText("manual", { exact: true }).closest("tr")!;
    expect(within(row).getByRole("button", { name: "Workflow" })).toBeDisabled();
    expect(within(row).getByRole("button", { name: "Archive manual" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(within(row).getByRole("button", { name: "Workflow" })).toBeEnabled();
    fireEvent.click(within(row).getByRole("button", { name: "Archive manual" }));
    expect(screen.getByRole("group", { name: "Archive manual" })).toBeVisible();
    fireEvent.click(within(screen.getByRole("group", { name: "Archive manual" })).getByRole("button", { name: "Cancel" }));
    fireEvent.change(screen.getByLabelText("Overdue"), { target: { value: "due" } });
    await waitFor(() => expect(screen.queryByRole("group", { name: "Selected" })).not.toBeInTheDocument());
  });
  it("sends status, assignee and overdue filters and supports workflow sorting", async () => {
    const { fetchMock } = await renderSignedIn(<FindingsPage />, "admin", routes);
    await screen.findByText("manual", { exact: true });
    fireEvent.click(within(screen.getByRole("group", { name: "status values" })).getByLabelText("Accepted risk"));
    fireEvent.click(within(screen.getByRole("group", { name: "assignee values" })).getByLabelText("Unassigned"));
    fireEvent.change(screen.getByLabelText("Overdue"), { target: { value: "risk_review" } });
    fireEvent.click(within(screen.getByRole("columnheader", { name: /^Status/ })).getByRole("button"));
    await waitFor(() => {
      const requests = fetchMock.mock.calls.filter(([url]) => url.includes("/findings?"));
      const query = new URL(requests.at(-1)![0], "http://localhost").searchParams;
      expect(query.get("workflow_status")).toBe("accepted_risk");
      expect(query.get("assignee")).toBe("unassigned"); expect(query.get("overdue")).toBe("risk_review");
      expect(query.get("sort")).toBe("workflow_status");
    });
  });
  it("allows more than 100 selections but caps workflow updates independently", async () => {
    await renderSignedIn(<FindingsPage />, "admin", { ...routes,
      "GET /orgs/org-1/findings": () => ({ items: Array.from({ length: 101 }, (_, i) => item(`item-${i}`)), total: 101, domain_counts: {} }) });
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select all on this page" }));
    expect(screen.getByRole("group", { name: "Selected" })).toHaveTextContent("101 selected");
    expect(screen.getByRole("button", { name: "Update selected workflow" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Archive selected" })).toBeEnabled();
    expect(screen.getByText(/Workflow updates support up to 100/)).toBeVisible();
  });
});
