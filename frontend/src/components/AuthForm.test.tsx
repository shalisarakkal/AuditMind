import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/(auth)/login/page";
import RegisterPage from "@/app/(auth)/register/page";
import { AppProvider } from "@/context/AppContext";
import { getToken } from "@/lib/apiClient";
import { callsTo, json, mockApi, org } from "@/test/helpers";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

function body(fetchMock: ReturnType<typeof mockApi>, key: string): unknown {
  return JSON.parse(String(callsTo(fetchMock, key)[0][1].body));
}

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("login and register pages", () => {
  beforeEach(() => replace.mockReset());

  it("signs in and goes to the dashboard", async () => {
    const fetchMock = mockApi({
      "POST /auth/login": () => ({ access_token: "tok", token_type: "bearer", expires_in: 900, must_change_password: false }),
      "GET /orgs": () => [org()],
    });
    render(<AppProvider><LoginPage /></AppProvider>);

    fill("Email", "owner@acme.io");
    fill("Password", "Sup3rSecret!");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(body(fetchMock, "POST /auth/login")).toEqual({ email: "owner@acme.io", password: "Sup3rSecret!" });
    expect(getToken()).toBe("tok");
  });

  it("shows the error for wrong credentials and stays put", async () => {
    mockApi({ "POST /auth/login": () => json({ detail: "Invalid email or password" }, 401) });
    render(<AppProvider><LoginPage /></AppProvider>);

    fill("Email", "owner@acme.io");
    fill("Password", "wrong");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("registers a new organization and account", async () => {
    const fetchMock = mockApi({
      "POST /auth/register": () =>
        json({ access_token: "tok", token_type: "bearer", expires_in: 900, must_change_password: false }, 201),
      "GET /orgs": () => [org({ name: "Globex" })],
    });
    render(<AppProvider><RegisterPage /></AppProvider>);

    fill("Organization name", "Globex");
    fill("Email", "founder@globex.io");
    fill("Password", "Sup3rSecret!");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(body(fetchMock, "POST /auth/register")).toEqual({
      org_name: "Globex",
      email: "founder@globex.io",
      password: "Sup3rSecret!",
    });
  });
});
