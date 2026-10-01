import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OrgPicker from "@/components/OrgPicker";
import { AppProvider } from "@/context/AppContext";
import { setToken } from "@/lib/apiClient";
import type { MyOrganization } from "@/lib/types";
import { mockApi, org } from "@/test/helpers";

async function renderPicker(orgs: MyOrganization[] = [org(), org({ id: "org-2", name: "Globex", role: "viewer" })]) {
  setToken("tok");
  const fetchMock = mockApi({ "GET /orgs": () => orgs });
  render(
    <AppProvider>
      <OrgPicker />
    </AppProvider>,
  );
  await waitFor(() => expect(screen.getByLabelText("Organization")).toHaveValue(orgs[0].id));
  return fetchMock;
}

describe("OrgPicker", () => {
  it("lists the user's orgs and shows their role in the selected one", async () => {
    await renderPicker();

    expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Globex" })).toBeInTheDocument();
    expect(screen.getByText("Your role: admin")).toBeInTheDocument();
    // Only the Sysadmin creates organizations.
    expect(screen.queryByRole("option", { name: /New organization/ })).not.toBeInTheDocument();
  });

  it("switching org remembers the choice", async () => {
    await renderPicker();

    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "org-2" } });

    expect(screen.getByLabelText("Organization")).toHaveValue("org-2");
    expect(screen.getByText("Your role: viewer")).toBeInTheDocument();
    expect(window.localStorage.getItem("auditmind_org_id")).toBe("org-2");
  });

  it("says when an org is archived, or read by the Sysadmin", async () => {
    await renderPicker([org({ archived: true }), org({ id: "org-2", name: "Globex", role: "viewer", access: "sysadmin" })]);

    expect(screen.getByRole("option", { name: "Acme Corp (archived)" })).toBeInTheDocument();
    expect(screen.getByText("Archived: read-only (your role: admin)")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "org-2" } });
    expect(screen.getByText("Sysadmin: read-only")).toBeInTheDocument();
  });
});
