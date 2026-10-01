import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OrgPicker from "@/components/OrgPicker";
import { AppProvider } from "@/context/AppContext";
import { setToken } from "@/lib/apiClient";
import { mockApi, org } from "@/test/helpers";

async function renderPicker(routes = {}) {
  setToken("tok");
  let orgs = [org(), org({ id: "org-2", name: "Globex", role: "viewer" })];
  const fetchMock = mockApi({
    "GET /orgs": () => orgs,
    "POST /orgs": (init: RequestInit) => {
      const created = org({ id: "org-3", name: JSON.parse(String(init.body)).name });
      orgs = [...orgs, created];
      return created;
    },
    ...routes,
  });
  render(
    <AppProvider>
      <OrgPicker />
    </AppProvider>,
  );
  await waitFor(() => expect(screen.getByLabelText("Organization")).toHaveValue("org-1"));
  return fetchMock;
}

describe("OrgPicker", () => {
  it("lists the user's orgs and shows their role in the selected one", async () => {
    await renderPicker();

    expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Globex" })).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
  });

  it("switching org remembers the choice", async () => {
    await renderPicker();

    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "org-2" } });

    expect(screen.getByLabelText("Organization")).toHaveValue("org-2");
    expect(screen.getByText("viewer")).toBeInTheDocument();
    expect(window.localStorage.getItem("auditmind_org_id")).toBe("org-2");
  });

  it("creates a new organization and selects it", async () => {
    const fetchMock = await renderPicker();

    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "__new__" } });
    fireEvent.change(screen.getByLabelText("New organization name"), { target: { value: "Acme Labs" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(screen.getByLabelText("Organization")).toHaveValue("org-3"));
    expect(screen.getByRole("option", { name: "Acme Labs" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true);
  });

  it("cancelling creation keeps the current org", async () => {
    await renderPicker();

    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "__new__" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByLabelText("Organization")).toHaveValue("org-1");
    expect(screen.queryByLabelText("New organization name")).not.toBeInTheDocument();
  });
});
