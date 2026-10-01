import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "@/app/(app)/account/page";
import PeoplePage from "@/app/(app)/people/page";
import AccountMenu from "@/components/AccountMenu";
import { eventSummary } from "@/lib/activity";
import type { ActivityEvent, Me, Member } from "@/lib/types";
import { callsTo, json, renderSignedIn } from "@/test/helpers";

const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => "/people",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
});

const ME: Me = {
  id: "u-ann",
  email: "ann@acme.io",
  name: "Ann",
  is_sysadmin: false,
  must_change_password: false,
  password_expires_at: null,
};

function member(overrides: Partial<Member> = {}): Member {
  return {
    id: "u-bob",
    email: "bob@acme.io",
    name: "Bob",
    auth_provider: "local",
    created_at: "2026-10-01T09:00:00Z",
    role: "viewer",
    added_at: "2026-10-01T09:00:00Z",
    status: "active",
    locked_until: null,
    temp_password_expires_at: null,
    in_other_orgs: false,
    ...overrides,
  };
}

const ann = member({ id: "u-ann", email: "ann@acme.io", name: "Ann", role: "admin" });
const page = (items: Member[]) => ({ items, total: items.length });

function routes(items: Member[], extra = {}) {
  return {
    "GET /auth/me": () => ME,
    "GET /orgs/org-1/members": () => page(items),
    "GET /orgs/org-1/members/facets": () => ({ role: ["admin", "viewer"], status: ["active", "locked"] }),
    ...extra,
  };
}

const rowOf = async (text: string) => (await screen.findByText(text)).closest("tr")!;

describe("People page", () => {
  it("lists the members; viewers see no actions", async () => {
    await renderSignedIn(<PeoplePage />, "viewer", routes([ann, member({ status: "locked", locked_until: null, in_other_orgs: true })]));
    const bob = await rowOf("bob@acme.io");
    expect(within(bob).getByText("Locked")).toBeInTheDocument();
    expect(within(bob).getByText("until an admin unlocks it")).toBeInTheDocument();
    expect(within(bob).getByText("Also in other organizations")).toBeInTheDocument();
    expect(within(bob).getByText("Viewer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add person" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /Role of/ })).not.toBeInTheDocument();
  });

  it("gives admins actions on others, but not on themselves", async () => {
    await renderSignedIn(<PeoplePage />, "admin", routes([ann, member({ status: "locked" })]));
    const bob = await rowOf("bob@acme.io");
    for (const name of ["Unlock", "Rename", "Reset password", "Remove"]) {
      expect(within(bob).getByRole("button", { name })).toBeInTheDocument();
    }
    const me = await rowOf("ann@acme.io");
    expect(within(me).queryByRole("button")).not.toBeInTheDocument();
    expect(within(me).getByRole("link", { name: "Your account" })).toHaveAttribute("href", "/account");
    expect(within(me).getByText("(you)")).toBeInTheDocument();
  });

  it("leaves renaming and password resets of people in other orgs to the Sysadmin", async () => {
    await renderSignedIn(<PeoplePage />, "admin", routes([ann, member({ in_other_orgs: true })]));
    const bob = await rowOf("bob@acme.io");
    expect(within(bob).queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
    expect(within(bob).queryByRole("button", { name: "Reset password" })).not.toBeInTheDocument();
    expect(within(bob).getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("adds a person and shows their temporary password once", async () => {
    const { fetchMock } = await renderSignedIn(
      <PeoplePage />,
      "admin",
      routes([ann], {
        "POST /orgs/org-1/members": () =>
          json({ ...member({ status: "must_change_password", temp_password_expires_at: "2026-10-08T09:00:00Z" }), temporary_password: "Tmp-Pass-1234567" }, 201),
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Add person" }));
    const form = screen.getByRole("form", { name: "Add person" });
    fireEvent.change(within(form).getByLabelText("Email"), { target: { value: " bob@acme.io " } });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Bob" } });
    fireEvent.change(within(form).getByLabelText("Role"), { target: { value: "auditor" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add" }));

    const panel = await screen.findByRole("group", { name: "Temporary password" });
    expect(within(panel).getByText("Tmp-Pass-1234567")).toBeInTheDocument();
    expect(panel).toHaveTextContent("Bob is added.");
    const [[, init]] = callsTo(fetchMock, "POST /orgs/org-1/members");
    expect(JSON.parse(String(init.body))).toEqual({ email: "bob@acme.io", name: "Bob", role: "auditor" });

    fireEvent.click(within(panel).getByRole("button", { name: "Done" }));
    expect(screen.queryByText("Tmp-Pass-1234567")).not.toBeInTheDocument();
  });

  it("says when the person already had an account", async () => {
    await renderSignedIn(
      <PeoplePage />,
      "admin",
      routes([ann], { "POST /orgs/org-1/members": () => json({ ...member(), temporary_password: null }, 201) }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Add person" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "bob@acme.io" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("status")).toHaveTextContent("bob@acme.io already had an account");
    expect(screen.queryByRole("group", { name: "Temporary password" })).not.toBeInTheDocument();
  });

  it("changes a role only after confirming", async () => {
    const { fetchMock } = await renderSignedIn(
      <PeoplePage />,
      "admin",
      routes([ann, member()], { "PATCH /orgs/org-1/members/u-bob": () => member({ role: "auditor" }) }),
    );
    fireEvent.change(await screen.findByRole("combobox", { name: "Role of Bob" }), { target: { value: "auditor" } });
    const confirm = screen.getByRole("group", { name: "Confirm" });
    expect(confirm).toHaveTextContent("Change Bob's role from Viewer to Auditor?");
    expect(callsTo(fetchMock, "PATCH /orgs/org-1/members/u-bob")).toHaveLength(0);

    fireEvent.click(within(confirm).getByRole("button", { name: "Change role" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Bob is now Auditor.");
    const [[, init]] = callsTo(fetchMock, "PATCH /orgs/org-1/members/u-bob");
    expect(JSON.parse(String(init.body))).toEqual({ role: "auditor" });
  });

  it("shows why a change was refused", async () => {
    await renderSignedIn(
      <PeoplePage />,
      "admin",
      routes([ann, member()], {
        "DELETE /orgs/org-1/members/u-bob": () =>
          json({ detail: { code: "last_admin", message: "An organization must keep at least one admin." } }, 409),
      }),
    );
    fireEvent.click(within(await rowOf("bob@acme.io")).getByRole("button", { name: "Remove" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm" })).getByRole("button", { name: "Remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An organization must keep at least one admin.");
  });

  it("resets a password and shows the temporary one", async () => {
    await renderSignedIn(
      <PeoplePage />,
      "admin",
      routes([ann, member()], {
        "POST /orgs/org-1/members/u-bob/reset-password": () => ({
          temporary_password: "New-Temp-7654321",
          expires_at: "2026-10-08T09:00:00Z",
        }),
      }),
    );
    fireEvent.click(within(await rowOf("bob@acme.io")).getByRole("button", { name: "Reset password" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm" })).getByRole("button", { name: "Reset password" }));
    const panel = await screen.findByRole("group", { name: "Temporary password" });
    expect(panel).toHaveTextContent("Bob's password is reset.");
    expect(within(panel).getByText("New-Temp-7654321")).toBeInTheDocument();
  });

  it("renames someone", async () => {
    const { fetchMock } = await renderSignedIn(
      <PeoplePage />,
      "admin",
      routes([ann, member()], { "PATCH /orgs/org-1/members/u-bob": () => member({ name: "Robert" }) }),
    );
    fireEvent.click(within(await rowOf("bob@acme.io")).getByRole("button", { name: "Rename" }));
    const form = screen.getByRole("form", { name: "Rename bob@acme.io" });
    fireEvent.change(within(form).getByRole("textbox"), { target: { value: " Robert " } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Renamed to Robert.");
    const [[, init]] = callsTo(fetchMock, "PATCH /orgs/org-1/members/u-bob");
    expect(JSON.parse(String(init.body))).toEqual({ name: "Robert" });
  });

  it("sends the filters to the API", async () => {
    const { fetchMock } = await renderSignedIn(<PeoplePage />, "viewer", routes([ann]));
    fireEvent.click(await screen.findByLabelText("Filter role: All"));
    fireEvent.click(within(screen.getByRole("group", { name: "role values" })).getByLabelText("Admin"));
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("/members?"));
      expect(new URLSearchParams(urls.at(-1)!.split("?")[1]).getAll("role")).toEqual(["admin"]);
    });
  });
});

describe("Your account", () => {
  it("shows the email, orgs and roles, and saves a new name", async () => {
    const { fetchMock } = await renderSignedIn(
      <>
        <AccountPage />
        <AccountMenu />
      </>,
      "auditor",
      {
        "GET /auth/me": () => ME,
        "PATCH /auth/me": () => ({ ...ME, name: "Ann Lee" }),
        "GET /auth/sessions": () => [],
      },
    );
    expect(await screen.findByText("ann@acme.io", { selector: "p" })).toBeInTheDocument();
    const orgs = screen.getAllByRole("table")[0];
    expect(within(orgs).getByText("Acme Corp")).toBeInTheDocument();
    expect(within(orgs).getByText("Auditor")).toBeInTheDocument();

    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled(); // nothing changed yet
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "  Ann Lee " } });
    fireEvent.click(save);
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    const [[, init]] = callsTo(fetchMock, "PATCH /auth/me");
    expect(JSON.parse(String(init.body))).toEqual({ name: "Ann Lee" });
    // The account menu loads the new name.
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/me?v=1"))).toBe(true),
    );
  });
});

describe("Where you're signed in", () => {
  const session = (overrides = {}) => ({
    id: "s1",
    signed_in_at: "2026-10-01T09:00:00Z",
    last_active_at: "2026-10-01T09:30:00Z",
    ip: "127.0.0.1",
    browser: "Chrome on Windows",
    current: true,
    ...overrides,
  });

  it("lists each sign-in and signs out the others", async () => {
    let sessions = [session(), session({ id: "s2", ip: "203.0.113.9", browser: "Safari on iOS", current: false })];
    const { fetchMock } = await renderSignedIn(<AccountPage />, "viewer", {
      "GET /auth/me": () => ME,
      "GET /auth/sessions": () => sessions,
      "DELETE /auth/sessions/s2": () => {
        sessions = [session()];
        return new Response(null, { status: 204 });
      },
    });
    const row = (await screen.findByText("Safari on iOS")).closest("tr")!;
    expect(within(row).getByText("203.0.113.9")).toBeInTheDocument();
    const mine = screen.getByText("Chrome on Windows").closest("tr")!;
    expect(within(mine).getByText("This browser")).toBeInTheDocument();
    expect(within(mine).queryByRole("button")).not.toBeInTheDocument();

    fireEvent.click(within(row).getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.queryByText("Safari on iOS")).not.toBeInTheDocument());
    expect(callsTo(fetchMock, "DELETE /auth/sessions/s2")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Sign out everywhere else" })).not.toBeInTheDocument();
  });
});

describe("People events in Activity", () => {
  const event = (overrides: Partial<ActivityEvent>): ActivityEvent => ({
    id: "e",
    type: "role_changed",
    item: "bob@acme.io",
    actor_id: "u-ann",
    actor_label: "Ann",
    started_at: "2026-10-01T09:00:00Z",
    ended_at: "2026-10-01T09:00:00Z",
    outcome: "completed",
    criticality: "info",
    counts: null,
    details: null,
    ...overrides,
  });

  it("says what changed", () => {
    expect(eventSummary(event({ details: { from: "viewer", to: "auditor" } }))).toBe("viewer → auditor");
    expect(eventSummary(event({ type: "name_changed", details: { from: null, to: "Bob" } }))).toBe("no name → Bob");
    expect(eventSummary(event({ type: "member_added", details: { role: "viewer", new_account: true } }))).toBe(
      "as viewer, new account",
    );
    expect(eventSummary(event({ type: "member_removed", details: { role: "auditor" } }))).toBe("was auditor");
    expect(eventSummary(event({ type: "login_failed", details: { ip: "203.0.113.9", browser: "Chrome on Windows" } }))).toBe(
      "from 203.0.113.9, Chrome on Windows",
    );
    expect(eventSummary(event({ type: "logout", details: { other_sign_ins: 2, from_elsewhere: true } }))).toBe(
      "2 other sign-ins, from another browser",
    );
  });
});
