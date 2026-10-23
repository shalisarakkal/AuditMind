import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SysadminOnly } from "@/components/SysadminOnly";
import { AppProvider } from "@/context/AppContext";
import { setToken } from "@/lib/apiClient";
import { callsTo, json, mockApi } from "@/test/helpers";

const me = { id: "root", email: "root@example.com", name: "Root", is_sysadmin: true,
  must_change_password: false, password_expires_at: null };

describe("Platform account gate", () => {
  it("shows a failed lookup with Retry, then recovers without a page refresh", async () => {
    setToken("token");
    let unavailable = true;
    mockApi({ "GET /orgs": () => [], "GET /auth/me": () => unavailable
      ? json({ detail: "Account service unavailable" }, 503) : me });
    render(<AppProvider><SysadminOnly><p>Protected settings</p></SysadminOnly></AppProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Account service unavailable");
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
    expect(screen.queryByText("Protected settings")).not.toBeInTheDocument();
    unavailable = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Protected settings")).toBeInTheDocument();
  });

  it("renews an expired account token before admitting a sysadmin", async () => {
    setToken("old");
    const fetchMock = mockApi({ "GET /orgs": () => [],
      "GET /auth/me": init => (init.headers as Record<string, string>).Authorization === "Bearer new"
        ? me : json({ detail: "Expired" }, 401),
      "POST /auth/refresh": () => ({ access_token: "new", must_change_password: false }),
    });
    render(<AppProvider><SysadminOnly><p>Protected settings</p></SysadminOnly></AppProvider>);
    expect(await screen.findByText("Protected settings")).toBeInTheDocument();
    expect(callsTo(fetchMock, "POST /auth/refresh")).toHaveLength(1);
  });

  it("keeps non-sysadmins out after a successful lookup", async () => {
    setToken("token");
    mockApi({ "GET /orgs": () => [], "GET /auth/me": () => ({ ...me, is_sysadmin: false }) });
    render(<AppProvider><SysadminOnly><p>Protected settings</p></SysadminOnly></AppProvider>);
    expect(await screen.findByText("This page is for the Sysadmin.")).toBeInTheDocument();
    expect(screen.queryByText("Protected settings")).not.toBeInTheDocument();
  });
});
