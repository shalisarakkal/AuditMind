import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppProvider, useApp } from "@/context/AppContext";
import { api, getToken, setToken } from "@/lib/apiClient";
import { callsTo, json, mockApi, org } from "@/test/helpers";

function Probe() {
  const app = useApp();
  return (
    <div>
      <span data-testid="hydrated">{String(app.hydrated)}</span>
      <span data-testid="auth">{String(app.isAuthenticated)}</span>
      <span data-testid="must-change">{String(app.mustChangePassword)}</span>
      <span data-testid="reason">{app.signedOutReason ?? "none"}</span>
      <span data-testid="selected">{app.selectedOrg?.name ?? "none"}</span>
      <button onClick={() => app.login("a@acme.io", "pw")}>login</button>
      <button onClick={() => app.logout()}>logout</button>
      <button onClick={() => app.changePassword("old-password", "new-password")}>change</button>
      <button onClick={() => app.selectOrg("org-2")}>select-2</button>
      <span data-testid="role">{app.selectedOrg?.role ?? "none"}</span>
      <button onClick={() => api.get("/orgs").catch(() => undefined)}>reload-orgs</button>
    </div>
  );
}

const TWO_ORGS = [org(), org({ id: "org-2", name: "Globex", role: "viewer" })];
const TOKEN = { token_type: "bearer", expires_in: 900, must_change_password: false };

describe("AppProvider", () => {
  it("starts signed out when there's no session cookie", async () => {
    const fetchMock = mockApi({});
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("hydrated")).toHaveTextContent("true"));
    expect(screen.getByTestId("auth")).toHaveTextContent("false");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/v1/auth/refresh"]);
  });

  it("picks the session up again on load from the cookie (a reload, a new tab)", async () => {
    mockApi({ "POST /auth/refresh": () => ({ access_token: "renewed", ...TOKEN }), "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));
    expect(screen.getByTestId("auth")).toHaveTextContent("true");
    expect(getToken()).toBe("renewed");
  });

  it("logs in, keeps the token in memory and selects the first org", async () => {
    mockApi({ "POST /auth/login": () => ({ access_token: "tok", ...TOKEN }), "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);
    await waitFor(() => expect(screen.getByTestId("hydrated")).toHaveTextContent("true"));

    await act(() => screen.getByText("login").click());

    expect(getToken()).toBe("tok");
    expect(window.localStorage.getItem("auditmind_token")).toBeNull();
    expect(screen.getByTestId("auth")).toHaveTextContent("true");
    expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp");
  });

  it("a password that must be changed: signed in, but no orgs until it is", async () => {
    const fetchMock = mockApi({
      "POST /auth/login": () => ({ access_token: "tok", ...TOKEN, must_change_password: true }),
      "POST /auth/change-password": () => new Response(null, { status: 204 }),
      "GET /orgs": () => TWO_ORGS,
    });
    render(<AppProvider><Probe /></AppProvider>);
    await waitFor(() => expect(screen.getByTestId("hydrated")).toHaveTextContent("true"));

    await act(() => screen.getByText("login").click());
    expect(screen.getByTestId("must-change")).toHaveTextContent("true");
    expect(callsTo(fetchMock, "GET /orgs")).toHaveLength(0);

    await act(() => screen.getByText("change").click());
    expect(screen.getByTestId("must-change")).toHaveTextContent("false");
    expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp");
    const [[, init]] = callsTo(fetchMock, "POST /auth/change-password");
    expect(JSON.parse(String(init.body))).toEqual({ current_password: "old-password", new_password: "new-password" });
  });

  it("a session that ends signs the app out and says why", async () => {
    setToken("tok");
    let orgsCalls = 0;
    const idle = { code: "session_ended", message: "You were signed out after a period of inactivity." };
    mockApi({ "GET /orgs": () => (++orgsCalls === 1 ? TWO_ORGS : json({ detail: idle }, 401)) });
    render(<AppProvider><Probe /></AppProvider>);
    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));

    await act(() => screen.getByText("reload-orgs").click());

    await waitFor(() => expect(screen.getByTestId("auth")).toHaveTextContent("false"));
    expect(screen.getByTestId("reason")).toHaveTextContent("inactivity");
    expect(screen.getByTestId("selected")).toHaveTextContent("none");
  });

  it("restores the remembered org, and persists a new selection", async () => {
    setToken("tok");
    window.localStorage.setItem("auditmind_org_id", "org-2");
    mockApi({ "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Globex"));
    await act(() => screen.getByText("select-2").click());
    expect(window.localStorage.getItem("auditmind_org_id")).toBe("org-2");
  });

  it("falls back to the first org when the remembered one is no longer available", async () => {
    setToken("tok");
    window.localStorage.setItem("auditmind_org_id", "org-gone");
    mockApi({ "GET /orgs": () => TWO_ORGS });
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));
    expect(window.localStorage.getItem("auditmind_org_id")).toBe("org-1");
  });

  it("an archived org is read-only: its pages act as for a viewer", async () => {
    setToken("tok");
    mockApi({ "GET /orgs": () => [org({ archived: true })] });
    render(<AppProvider><Probe /></AppProvider>);

    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));
    expect(screen.getByTestId("role")).toHaveTextContent("viewer");
  });

  it("logout ends the session on the server and clears the org", async () => {
    setToken("tok");
    const fetchMock = mockApi({
      "GET /orgs": () => TWO_ORGS,
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    render(<AppProvider><Probe /></AppProvider>);
    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("Acme Corp"));

    await act(() => screen.getByText("logout").click());

    expect(callsTo(fetchMock, "POST /auth/logout")).toHaveLength(1);
    expect(screen.getByTestId("auth")).toHaveTextContent("false");
    expect(screen.getByTestId("selected")).toHaveTextContent("none");
    expect(getToken()).toBeNull();
    expect(window.localStorage.getItem("auditmind_org_id")).toBeNull();
  });
});
