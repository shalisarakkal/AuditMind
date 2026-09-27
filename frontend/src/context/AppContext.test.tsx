import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppProvider, useApp } from "@/context/AppContext";
import { mockApi, org } from "@/test/helpers";

function Probe() {
  const app = useApp();
  return (
    <div>
      <span data-testid="auth">{String(app.isAuthenticated)}</span>
      <span data-testid="selected">{app.selectedOrg?.name ?? "none"}</span>
      <button onClick={() => app.login("a@acme.io", "pw")}>login</button>
      <button onClick={() => app.logout()}>logout</button>
      <button onClick={() => app.selectOrg("org-2")}>select-2</button>
      <button onClick={() => app.createOrg("Acme Labs")}>create</button>
    </div>
  );
}

const TWO_ORGS = [org(), org({ id: "org-2", name: "Globex", role: "viewer" })];

describe("AppProvider", () => {
  it("starts signed out without a stored token", async () => {
    const fetchMock = mockApi({});
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("auth")).toHaveTextContent("false"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("logs in, stores the token and selects the first org", async () => {
    mockApi({ "POST /auth/login": () => ({ access_token: "tok", token_type: "bearer" }), "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);

    await act(() => screen.getByText("login").click());

    expect(window.localStorage.getItem("auditmind_token")).toBe("tok");
    expect(screen.getByTestId("auth")).toHaveTextContent("true");
    expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp");
  });

  it("restores the remembered org, and persists a new selection", async () => {
    window.localStorage.setItem("auditmind_token", "tok");
    window.localStorage.setItem("auditmind_org_id", "org-2");
    mockApi({ "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Globex"));
    await act(() => screen.getByText("select-2").click());
    expect(window.localStorage.getItem("auditmind_org_id")).toBe("org-2");
  });

  it("falls back to the first org when the remembered one is no longer available", async () => {
    window.localStorage.setItem("auditmind_token", "tok");
    window.localStorage.setItem("auditmind_org_id", "org-gone");
    mockApi({ "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));
    expect(window.localStorage.getItem("auditmind_org_id")).toBe("org-1");
  });

  it("creating an org selects it", async () => {
    window.localStorage.setItem("auditmind_token", "tok");
    let orgs = [org()];
    mockApi({
      "GET /orgs": () => orgs,
      "POST /orgs": () => {
        orgs = [...orgs, org({ id: "org-3", name: "Acme Labs" })];
        return orgs[1];
      },
    });
    render(<AppProvider><Probe /></AppProvider>);
    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));

    await act(() => screen.getByText("create").click());

    expect(screen.getByTestId("selected")).toHaveTextContent("Acme Labs");
  });

  it("logout clears the session and org", async () => {
    window.localStorage.setItem("auditmind_token", "tok");
    mockApi({ "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);
    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));

    await act(() => screen.getByText("logout").click());

    expect(screen.getByTestId("auth")).toHaveTextContent("false");
    expect(screen.getByTestId("selected")).toHaveTextContent("none");
    expect(window.localStorage.getItem("auditmind_token")).toBeNull();
    expect(window.localStorage.getItem("auditmind_org_id")).toBeNull();
  });
});
