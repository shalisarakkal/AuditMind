import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import IngestionSettingsPanel from "@/components/IngestionSettingsPanel";
import type { IngestionSettings } from "@/lib/types";
import { json, mockApi } from "@/test/helpers";

function settings(overrides: Partial<IngestionSettings> = {}): IngestionSettings {
  return {
    import_partial_success: true,
    asset_existing_strategy: "update",
    nessus_info_severity: "skip",
    nessus_domain_map: { Firewalls: "network_config", "Web Servers": "incident_response" },
    nessus_default_domain: "vulnerability_management",
    overridden: [],
    nessus_domain_map_override: {},
    asset_type_aliases: { laptop: "workstation", lambda: "cloud_resource" },
    asset_type_aliases_override: {},
    archive_retention_days: 180,
    ...overrides,
  };
}

function setup(initial: IngestionSettings, isAdmin = true) {
  const patches: unknown[] = [];
  let current = initial;
  mockApi({
    "GET /orgs/org-1/settings": () => current,
    "PATCH /orgs/org-1/settings": (init) => {
      const body = JSON.parse(String(init.body));
      patches.push(body);
      if (body.asset_existing_strategy === "merge") {
        return json({ detail: [{ loc: ["body", "asset_existing_strategy"], msg: "invalid" }] }, 422);
      }
      const key = Object.keys(body)[0];
      current = {
        ...current,
        ...(body[key] === null ? { [key]: initial[key as keyof IngestionSettings] } : body),
        overridden: body[key] === null ? current.overridden.filter((k) => k !== key) : [...current.overridden, key],
      };
      return current;
    },
  });
  render(<IngestionSettingsPanel orgId="org-1" isAdmin={isAdmin} />);
  return patches;
}

describe("IngestionSettingsPanel", () => {
  it("shows effective values and whether each is an override", async () => {
    setup(settings({ asset_existing_strategy: "skip", overridden: ["asset_existing_strategy"] }));

    expect(await screen.findByLabelText("Asset already in inventory")).toHaveValue("skip");
    expect(screen.getByLabelText("Files with bad rows")).toHaveValue("true");
    expect(screen.getAllByText("Override")).toHaveLength(1);
    expect(screen.getAllByText("Default")).toHaveLength(4);
    expect(screen.getByLabelText("Keep archived items for")).toHaveValue(180);
    expect(screen.getByText("Firewalls → Network & Config")).toBeInTheDocument();
  });

  it("saves the retention days only when changed and valid, and resets them", async () => {
    const patches = setup(settings());
    const days = await screen.findByLabelText("Keep archived items for");
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();

    fireEvent.change(days, { target: { value: "0" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(days, { target: { value: "365" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches).toEqual([{ archive_retention_days: 365 }]));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
    expect(days).toHaveValue(365);

    // Its own Reset (the only override): back to the server default.
    fireEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    await waitFor(() => expect(patches).toEqual([{ archive_retention_days: 365 }, { archive_retention_days: null }]));
    await waitFor(() => expect(days).toHaveValue(180));
  });

  it("viewers see the retention days but can't change them", async () => {
    setup(settings(), false);
    expect(await screen.findByLabelText("Keep archived items for")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("admin changes send only that setting", async () => {
    const patches = setup(settings());

    fireEvent.change(await screen.findByLabelText("Asset already in inventory"), { target: { value: "skip" } });
    await waitFor(() => expect(screen.getAllByText("Override")).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Files with bad rows"), { target: { value: "false" } });

    await waitFor(() => expect(patches).toEqual([{ asset_existing_strategy: "skip" }, { import_partial_success: false }]));
  });

  it("reset to default clears the override", async () => {
    const patches = setup(settings({ nessus_info_severity: "low", overridden: ["nessus_info_severity"] }));

    fireEvent.click(await screen.findByRole("button", { name: "Reset to default" }));

    await waitFor(() => expect(patches).toEqual([{ nessus_info_severity: null }]));
    await waitFor(() => expect(screen.queryByText("Override")).not.toBeInTheDocument());
  });

  it("edits the org's own domain mappings", async () => {
    const patches = setup(settings());

    fireEvent.click(await screen.findByRole("button", { name: "+ Add mapping" }));
    fireEvent.change(screen.getByLabelText("Plugin family 1"), { target: { value: " Databases " } });
    fireEvent.change(screen.getByLabelText("Domain for plugin family 1"), { target: { value: "backup_recovery" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mappings" }));

    await waitFor(() => expect(patches).toEqual([{ nessus_domain_map: { Databases: "backup_recovery" } }]));
  });

  it("a new mapping row starts on the org's default domain", async () => {
    setup(settings({ nessus_default_domain: "compliance_alignment" }));

    fireEvent.click(await screen.findByRole("button", { name: "+ Add mapping" }));

    expect(screen.getByLabelText("Domain for plugin family 1")).toHaveValue("compliance_alignment");
  });

  it("removing every custom mapping clears the override", async () => {
    const patches = setup(settings({ nessus_domain_map_override: { "Web Servers": "incident_response" }, overridden: ["nessus_domain_map"] }));

    // The org's own mapping is editable, not listed as inherited.
    expect(await screen.findByLabelText("Plugin family 1")).toHaveValue("Web Servers");
    expect(screen.queryByText("Web Servers → Incident Response")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove plugin family 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Save mappings" }));

    await waitFor(() => expect(patches).toEqual([{ nessus_domain_map: null }]));
  });

  it("shows a rejected change", async () => {
    setup(settings());
    const select = await screen.findByLabelText("Asset already in inventory");
    // Simulate a value the server rejects.
    const option = document.createElement("option");
    option.value = "merge";
    select.appendChild(option);

    fireEvent.change(select, { target: { value: "merge" } });

    expect(await screen.findByText("asset_existing_strategy: invalid")).toBeInTheDocument();
  });

  it("is read-only for non-admins", async () => {
    setup(settings({ nessus_info_severity: "low", overridden: ["nessus_info_severity"] }), false);

    expect(await screen.findByText("Only organization admins can change these settings.")).toBeInTheDocument();
    for (const select of screen.getAllByRole("combobox")) expect(select).toBeDisabled();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("edits the org's own asset type names", async () => {
    const patches = setup(settings({ asset_type_aliases_override: { hypervisor: "server" } }));

    expect(await screen.findByLabelText("Type name 1")).toHaveValue("hypervisor");
    expect(screen.getByText("laptop → Workstation")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Add type name" }));
    fireEvent.change(screen.getByLabelText("Type name 2"), { target: { value: " Hologram " } });
    fireEvent.change(screen.getByLabelText("Category for type name 2"), { target: { value: "application" } });
    fireEvent.click(screen.getByRole("button", { name: "Save type names" }));

    await waitFor(() =>
      expect(patches).toEqual([{ asset_type_aliases: { hypervisor: "server", Hologram: "application" } }]),
    );
  });

  it("removing every type name clears the override", async () => {
    const patches = setup(settings({ asset_type_aliases_override: { hypervisor: "server" } }));

    fireEvent.click(await screen.findByRole("button", { name: "Remove type name 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Save type names" }));

    await waitFor(() => expect(patches).toEqual([{ asset_type_aliases: null }]));
  });
});
