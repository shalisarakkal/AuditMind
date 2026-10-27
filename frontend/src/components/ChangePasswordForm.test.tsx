import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AccountMenu from "@/components/AccountMenu";
import ChangePasswordForm, { describeRules } from "@/components/ChangePasswordForm";
import { AppProvider } from "@/context/AppContext";
import { setToken } from "@/lib/apiClient";
import type { PasswordRules } from "@/lib/types";
import { callsTo, json, mockApi, org } from "@/test/helpers";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/" }));

const SIMPLE: PasswordRules = {
  rule: "simple",
  min_length: 12,
  max_length: 128,
  require_upper: false,
  require_lower: false,
  require_digit: false,
  require_symbol: false,
  history_count: 0,
  expiry_days: 0,
  required_by: {},
};

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function renderForm(routes = {}, onDone = vi.fn()) {
  setToken("tok");
  const fetchMock = mockApi({ "GET /orgs": () => [org()], "GET /auth/password-rules": () => SIMPLE, ...routes });
  render(
    <AppProvider>
      <ChangePasswordForm onDone={onDone} />
    </AppProvider>,
  );
  await screen.findByRole("list", { name: "Password rules" });
  return fetchMock;
}

describe("describeRules", () => {
  it("Simple: the length, in any language", () => {
    expect(describeRules(SIMPLE)).toEqual([
      "12 to 128 characters, in any language",
      "Not your email address, nor your current password",
    ]);
  });

  it("Complex: each kind, history and expiry, naming the org that asks", () => {
    const lines = describeRules({
      ...SIMPLE,
      rule: "complex",
      min_length: 16,
      require_upper: true,
      require_symbol: true,
      history_count: 5,
      expiry_days: 90,
      required_by: { min_length: "Acme", expiry_days: "Globex" },
    });
    expect(lines[0]).toBe("16 to 128 characters, in any language (required by Acme)");
    expect(lines[1]).toContain("an upper-case letter");
    expect(lines[1]).toContain("a symbol");
    expect(lines[1]).not.toContain("required by");
    expect(lines).toContain("Not one of your last 5 passwords");
    expect(lines).toContain("It must be changed every 90 days (required by Globex)");
  });
});

it("names each org asking for a kind of character", () => {
  const [, kinds] = describeRules({
    ...SIMPLE,
    rule: "complex",
    require_upper: true,
    require_digit: true,
    required_by: { require_upper: "Acme", require_digit: "Globex", rule: "Acme" },
  });
  expect(kinds).toBe(
    "At least an upper-case letter (A-Z, or any script with capitals), a digit (required by Acme, Globex)",
  );
});

describe("ChangePasswordForm", () => {
  it("changes the password", async () => {
    const onDone = vi.fn();
    const fetchMock = await renderForm({ "POST /auth/change-password": () => new Response(null, { status: 204 }) }, onDone);

    fill("Current password", "Sup3rSecret!");
    fill("New password", "A-new-passphrase-2026");
    fill("New password again", "A-new-passphrase-2026");
    fireEvent.click(screen.getByRole("button", { name: "Show current password" }));
    fireEvent.click(screen.getByRole("button", { name: "Show new password" }));
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password again")).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [[, init]] = callsTo(fetchMock, "POST /auth/change-password");
    expect(JSON.parse(String(init.body))).toEqual({
      current_password: "Sup3rSecret!",
      new_password: "A-new-passphrase-2026",
    });
  });

  it("checks the two new passwords match before sending", async () => {
    const fetchMock = await renderForm();

    fill("Current password", "Sup3rSecret!");
    fill("New password", "A-new-passphrase-2026");
    fill("New password again", "A-new-passphrase-2025");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The new passwords don't match");
    expect(callsTo(fetchMock, "POST /auth/change-password")).toHaveLength(0);
  });

  it("lists every rule the new password breaks", async () => {
    await renderForm({
      "POST /auth/change-password": () =>
        json(
          {
            detail: {
              code: "password_policy",
              message: "...",
              problems: [
                { code: "too_short", message: "Use at least 16 characters (required by Acme)" },
                { code: "symbol", message: "Include a symbol (such as ! or #)" },
              ],
            },
          },
          422,
        ),
    });

    fill("Current password", "Sup3rSecret!");
    fill("New password", "short");
    fill("New password again", "short");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Use at least 16 characters (required by Acme)");
    expect(alert).toHaveTextContent("Include a symbol");
  });
});

describe("AccountMenu", () => {
  it("shows who is signed in, with Change password and Sign out", async () => {
    setToken("tok");
    const fetchMock = mockApi({
      "GET /orgs": () => [org()],
      "GET /auth/me": () => ({ id: "u", email: "ann@acme.io", name: "Ann Lee", is_sysadmin: false, must_change_password: false, password_expires_at: null }),
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    render(
      <AppProvider>
        <AccountMenu />
      </AppProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Ann Lee/ }));
    expect(screen.getByRole("menuitem", { name: "Change password" })).toHaveAttribute("href", "/change-password");

    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(callsTo(fetchMock, "POST /auth/logout")).toHaveLength(1));
  });
});
