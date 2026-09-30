import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ImportProfilesPanel from "@/components/ImportProfilesPanel";
import type { ImportProfile } from "@/lib/types";
import { json, mockApi, requestBody } from "@/test/helpers";
import { BUILTIN_PROFILES, CUSTOM_EDR_PROFILE, DIRECTORY_PROFILE, NETWORK_PROFILE } from "@/test/profiles";

const URL = "/orgs/org-1/import-profiles";

function setup(isAdmin = true, extra: Record<string, (init: RequestInit) => unknown> = {}) {
  let profiles: ImportProfile[] = [...BUILTIN_PROFILES, CUSTOM_EDR_PROFILE];
  const fetchMock = mockApi({
    [`GET ${URL}`]: () => profiles,
    ...extra,
    [`DELETE ${URL}/${CUSTOM_EDR_PROFILE.key}`]: () => {
      profiles = profiles.filter((p) => p.key !== CUSTOM_EDR_PROFILE.key);
      return new Response(null, { status: 204 });
    },
  });
  render(<ImportProfilesPanel orgId="org-1" isAdmin={isAdmin} />);
  return fetchMock;
}

function row(name: string) {
  return screen.getByText(name).closest("tr")!;
}

describe("ImportProfilesPanel", () => {
  it("lists built-in and custom profiles with what they read", async () => {
    setup();

    expect(await screen.findByText("Our EDR")).toBeInTheDocument();
    expect(row("Endpoint agent export")).toHaveTextContent("Built-in");
    expect(row("Endpoint agent export")).toHaveTextContent("Assets + findings");
    expect(row("Generic findings")).toHaveTextContent("Findings");
    expect(row("Generic asset list")).toHaveTextContent("Assets");
    expect(row("Generic asset list")).not.toHaveTextContent("findings");
    expect(row("Our EDR")).toHaveTextContent("Device_Name");
    expect(row("Our EDR")).not.toHaveTextContent("Built-in");
    // Built-ins can be copied but not edited or deleted.
    expect(within(row("Endpoint agent export")).queryByRole("button", { name: /Edit|Delete/ })).not.toBeInTheDocument();
    expect(within(row("Our EDR")).getByRole("button", { name: "Edit Our EDR" })).toBeInTheDocument();
  });

  it("copies a profile under a new name, then opens it for editing", async () => {
    const created = { ...CUSTOM_EDR_PROFILE, key: "new-id", name: "Scanner B" };
    const fetchMock = setup(true, { [`POST ${URL}`]: () => json(created, 201) });

    fireEvent.click(await screen.findByRole("button", { name: "Copy Endpoint agent export" }));
    const name = screen.getByLabelText("New format name");
    expect(name).toHaveValue("Endpoint agent export (copy)");
    fireEvent.change(name, { target: { value: "Scanner B" } });
    fireEvent.click(screen.getByRole("button", { name: "Create copy" }));

    expect(await screen.findByRole("region", { name: "Edit Scanner B" })).toBeInTheDocument();
    const post = fetchMock.mock.calls.findIndex(([, init]) => init?.method === "POST");
    expect(requestBody(fetchMock, post)).toEqual({ name: "Scanner B", copy_from: "endpoint_agent" });
  });

  it("shows why a copy was refused", async () => {
    setup(true, { [`POST ${URL}`]: () => json({ detail: "A profile named 'Our EDR' already exists" }, 409) });

    fireEvent.click(await screen.findByRole("button", { name: "Copy Our EDR" }));
    fireEvent.change(screen.getByLabelText("New format name"), { target: { value: "Our EDR" } });
    fireEvent.click(screen.getByRole("button", { name: "Create copy" }));

    expect(await screen.findByText("A profile named 'Our EDR' already exists")).toBeInTheDocument();
  });

  it("edits an endpoint profile's columns and rules", async () => {
    const fetchMock = setup(true, {
      [`PATCH ${URL}/${CUSTOM_EDR_PROFILE.key}`]: (init) => ({ ...CUSTOM_EDR_PROFILE, ...JSON.parse(String(init.body)) }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Edit Our EDR" }));
    const editor = screen.getByRole("region", { name: "Edit Our EDR" });
    fireEvent.change(within(editor).getByLabelText("Name"), { target: { value: "Our EDR v2" } });
    fireEvent.change(within(editor).getByLabelText("Column for Hostname"), { target: { value: " Host " } });
    fireEvent.change(within(editor).getByLabelText("Column for Endpoint ID"), { target: { value: "" } });
    fireEvent.change(within(editor).getByLabelText("Agent not reporting after (days)"), { target: { value: "14" } });
    fireEvent.click(within(editor).getByLabelText(/Dates are day first/));
    fireEvent.change(within(editor).getByLabelText("Statuses that mean compliant"), { target: { value: "compliant, ok" } });
    fireEvent.click(within(editor).getByLabelText(/Keep the file's other columns/));
    fireEvent.click(within(editor).getByRole("button", { name: "+ Add default value" }));
    fireEvent.change(within(editor).getByLabelText("Default field 3"), { target: { value: "hostname" } });
    fireEvent.change(within(editor).getByLabelText("Default value 3"), { target: { value: "unknown-host" } });
    fireEvent.click(within(editor).getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(screen.queryByRole("region", { name: /^Edit / })).not.toBeInTheDocument());
    const patch = fetchMock.mock.calls.findIndex(([, init]) => init?.method === "PATCH");
    const body = requestBody(fetchMock, patch) as { name: string; column_map: object; params: Record<string, unknown> };
    expect(body.name).toBe("Our EDR v2");
    expect(body.column_map).toEqual({
      hostname: "Host",
      last_heartbeat: "LastHeartbeat",
      threats_detected: "ThreatsDetected",
      compliance_status: "ComplianceStatus",
    });
    expect(body.params).toEqual({
      default_values: { type: "workstation", subtype: "endpoint", hostname: "unknown-host" },
      type_aliases: {},
      keep_other_columns: false,
      threats_high_at: 1,
      threats_critical_at: 5,
      stale_after_days: 14,
      day_first_dates: true,
      compliance_severity: { warning: "low", "non-compliant": "medium" },
      compliant_values: ["compliant", "ok"],
    });
  });

  it("edits a network profile's ports and vulnerability domains", async () => {
    const custom = { ...NETWORK_PROFILE, key: "net-1", name: "Our scanner", builtin: false };
    let saved: Record<string, unknown> = {};
    mockApi({
      [`GET ${URL}`]: () => [...BUILTIN_PROFILES, custom],
      [`PATCH ${URL}/net-1`]: (init) => {
        saved = JSON.parse(String(init.body));
        return { ...custom, ...saved };
      },
    });
    render(<ImportProfilesPanel orgId="org-1" isAdmin />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit Our scanner" }));
    const editor = screen.getByRole("region", { name: "Edit Our scanner" });
    expect(within(editor).queryByLabelText("Statuses that mean compliant")).not.toBeInTheDocument();
    fireEvent.change(within(editor).getByLabelText("Values that mean no vulnerability"), { target: { value: "none, n/a, clean" } });
    fireEvent.change(within(editor).getByLabelText("High at risk score"), { target: { value: "6.5" } });
    fireEvent.click(within(editor).getByRole("button", { name: "+ Add port" }));
    fireEvent.change(within(editor).getByLabelText("Port 2"), { target: { value: "3389" } });
    fireEvent.change(within(editor).getByLabelText("Label for port 2"), { target: { value: "RDP" } });
    fireEvent.change(within(editor).getByLabelText("Severity for port 2"), { target: { value: "high" } });
    fireEvent.click(within(editor).getByRole("button", { name: "Remove vulnerability 1" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(saved.params).toBeDefined());
    expect(saved.params).toMatchObject({
      risk_critical_at: 9,
      risk_high_at: 6.5,
      risk_medium_at: 4,
      vulnerability_domains: {},
      no_vulnerability_values: ["none", "n/a", "clean"],
      risky_ports: { "23": { label: "Telnet", severity: "high" }, "3389": { label: "RDP", severity: "high" } },
      keep_other_columns: true,
    });
  });

  it("keeps the editor open and shows the server's message when a save is refused", async () => {
    setup(true, {
      [`PATCH ${URL}/${CUSTOM_EDR_PROFILE.key}`]: () =>
        json({ detail: "params.stale_after_days: Input should be greater than or equal to 1" }, 422),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Edit Our EDR" }));
    fireEvent.change(screen.getByLabelText("Agent not reporting after (days)"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    expect(await screen.findByText("params.stale_after_days: Input should be greater than or equal to 1")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Edit Our EDR" })).toBeInTheDocument();
  });

  it("deletes a custom profile after confirming", async () => {
    const fetchMock = setup();

    fireEvent.click(await screen.findByRole("button", { name: "Delete Our EDR" }));
    const confirm = screen.getByRole("group", { name: "Delete format" });
    expect(confirm).toHaveTextContent("Delete Our EDR? Past uploads keep their reports.");
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete format" }));

    await waitFor(() => expect(screen.queryByText("Our EDR")).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true);
  });

  it("is read-only for non-admins", async () => {
    setup(false);

    expect(await screen.findByText("Only organization admins can change file formats.")).toBeInTheDocument();
    expect(screen.getByText("Our EDR")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("names an emptied number setting instead of saving", async () => {
    const fetchMock = setup();

    fireEvent.click(await screen.findByRole("button", { name: "Edit Our EDR" }));
    fireEvent.change(screen.getByLabelText("Threats for a critical finding"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    expect(await screen.findByText("Threats for a critical finding needs a number.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("edits a directory profile's rules", async () => {
    const custom = { ...DIRECTORY_PROFILE, key: "dir-1", name: "Our AD", builtin: false };
    let saved: Record<string, unknown> = {};
    mockApi({
      [`GET ${URL}`]: () => [...BUILTIN_PROFILES, custom],
      [`PATCH ${URL}/dir-1`]: (init) => {
        saved = JSON.parse(String(init.body));
        return { ...custom, ...saved };
      },
    });
    render(<ImportProfilesPanel orgId="org-1" isAdmin />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit Our AD" }));
    const editor = screen.getByRole("region", { name: "Edit Our AD" });
    fireEvent.change(within(editor).getByLabelText("Stale after no login for (days)"), { target: { value: "30" } });
    fireEvent.change(within(editor).getByLabelText("Stale account severity"), { target: { value: "high" } });
    fireEvent.change(within(editor).getByLabelText("Statuses that need no finding"), { target: { value: "active, pending, quarantined" } });
    fireEvent.change(within(editor).getByLabelText("Column for hostname"), { target: { value: "Hostname|DNSHostName|Name" } });
    fireEvent.click(within(editor).getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(saved.params).toBeDefined());
    expect(saved.params).toMatchObject({
      stale_login_days: 30,
      stale_severity: "high",
      disabled_severity: "low",
      disabled_values: ["disabled", "inactive"],
      ok_values: ["active", "pending", "quarantined"],
      day_first_dates: false,
      keep_other_columns: true,
    });
    expect((saved.column_map as Record<string, string>).hostname).toBe("Hostname|DNSHostName|Name");
  });
});
