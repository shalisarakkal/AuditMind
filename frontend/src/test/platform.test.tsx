import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/(auth)/login/page";
import RegisterPage from "@/app/(auth)/register/page";
import AccountsPage from "@/app/(app)/platform/accounts/page";
import OrganizationsPage from "@/app/(app)/platform/organizations/page";
import OrgGate from "@/components/OrgGate";
import SecuritySettingsForm from "@/components/SecuritySettingsForm";
import Sidebar from "@/components/Sidebar";
import { AppProvider } from "@/context/AppContext";
import { ImportsProvider } from "@/context/ImportsContext";
import type { Me, PlatformOrg, PlatformUser, SecuritySettings } from "@/lib/types";
import { callsTo, json, mockApi, org, renderSignedIn } from "@/test/helpers";
import { setToken } from "@/lib/apiClient";

const navigation = vi.hoisted(() => ({ search: "", path: "/" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => navigation.path,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
  navigation.path = "/";
});

const ROOT: Me = {
  id: "u-root",
  email: "root@platform.io",
  name: "Root",
  is_sysadmin: true,
  must_change_password: false,
  password_expires_at: null,
};

const bodyOf = (fetchMock: ReturnType<typeof mockApi>, key: string, index = 0) =>
  JSON.parse(String(callsTo(fetchMock, key)[index][1].body));

describe("sign-up", () => {
  it("offers Create an account only while sign-up is open", async () => {
    mockApi({ "GET /auth/options": () => ({ public_signup: true }) });
    const { unmount } = render(<AppProvider><LoginPage /></AppProvider>);
    expect(await screen.findByRole("link", { name: "Create an account" })).toBeInTheDocument();
    unmount();

    mockApi({ "GET /auth/options": () => ({ public_signup: false }) });
    render(<AppProvider><LoginPage /></AppProvider>);
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled());
    expect(screen.queryByRole("link", { name: "Create an account" })).not.toBeInTheDocument();
  });

  it("says when it's closed", async () => {
    mockApi({ "GET /auth/options": () => ({ public_signup: false }) });
    render(<AppProvider><RegisterPage /></AppProvider>);
    expect(await screen.findByRole("heading", { name: "Sign-up is closed" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Organization name")).not.toBeInTheDocument();
  });
});

describe("archived orgs and the Sysadmin's pages", () => {
  it("shows a read-only banner in an archived org", async () => {
    setToken("tok");
    mockApi({ "GET /orgs": () => [org({ archived: true })] });
    render(
      <AppProvider>
        <OrgGate>
          <p>page</p>
        </OrgGate>
      </AppProvider>,
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Acme Corp is archived, so it's read-only.");
    expect(screen.getByText("page")).toBeInTheDocument();
  });

  it("lets the Platform pages open without an org (a new Sysadmin has none)", async () => {
    navigation.path = "/platform/organizations";
    setToken("tok");
    mockApi({ "GET /orgs": () => [] });
    render(
      <AppProvider>
        <OrgGate>
          <p>platform page</p>
        </OrgGate>
      </AppProvider>,
    );
    expect(await screen.findByText("platform page")).toBeInTheDocument();
  });

  it("gives the Sysadmin a Platform section in the sidebar", async () => {
    setToken("tok");
    mockApi({
      "GET /orgs": () => [],
      "GET /auth/me": () => ROOT,
      "GET /worker-status": () => ({ running: true, last_seen: null }),
    });
    render(
      <AppProvider>
        <ImportsProvider pollIntervalMs={1000}>
          <Sidebar />
        </ImportsProvider>
      </AppProvider>,
    );
    const platform = await screen.findByRole("list", { name: "Platform" });
    for (const name of ["Organizations", "Accounts", "Platform activity", "Security defaults"]) {
      expect(within(platform).getByRole("link", { name })).toBeInTheDocument();
    }
    // No org: none of an org's pages.
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
  });
});

function platformOrg(overrides: Partial<PlatformOrg> = {}): PlatformOrg {
  return {
    id: "o1",
    name: "Acme",
    industry: null,
    size: null,
    created_at: "2026-10-01T09:00:00Z",
    status: "active",
    archived_at: null,
    members: 3,
    admins: ["ann@acme.io"],
    ...overrides,
  };
}

const sysadminRoutes = (extra = {}) => ({ "GET /auth/me": () => ROOT, ...extra });

describe("Organizations", () => {
  it("creates an organization and shows its admin's temporary password", async () => {
    const { fetchMock } = await renderSignedIn(<OrganizationsPage />, "viewer", sysadminRoutes({
      "GET /platform/orgs": () => ({ items: [platformOrg()], total: 1 }),
      "GET /platform/orgs/facets": () => ({ status: ["active"] }),
      "POST /platform/orgs": () =>
        json({ ...platformOrg({ id: "o2", name: "Globex", admins: ["zed@globex.io"] }), temporary_password: "Tmp-Zed-12345678", temp_password_expires_at: null }, 201),
    }));
    fireEvent.click(await screen.findByRole("button", { name: "Create organization" }));
    const form = screen.getByRole("form", { name: "Create organization" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Globex" } });
    fireEvent.change(within(form).getByLabelText("Admin's email"), { target: { value: "zed@globex.io" } });
    fireEvent.click(within(form).getByRole("button", { name: "Create" }));

    const panel = await screen.findByRole("group", { name: "Temporary password" });
    expect(within(panel).getByText("Tmp-Zed-12345678")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST /platform/orgs")).toEqual({ name: "Globex", admin_email: "zed@globex.io" });
  });

  it("archives after confirming, and purges only once the name is typed", async () => {
    let orgs = [platformOrg()];
    const { fetchMock } = await renderSignedIn(<OrganizationsPage />, "viewer", sysadminRoutes({
      "GET /platform/orgs": () => ({ items: orgs, total: orgs.length }),
      "GET /platform/orgs/facets": () => ({ status: ["active"] }),
      "POST /platform/orgs/o1/archive": () => {
        orgs = [platformOrg({ status: "archived", archived_at: "2026-10-01T10:00:00Z" })];
        return orgs[0];
      },
      "POST /platform/orgs/o1/purge": () => json(platformOrg({ status: "purging" }), 202),
    }));
    fireEvent.click(await screen.findByRole("button", { name: "Archive" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm" })).getByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Acme is archived");

    fireEvent.click(await screen.findByRole("button", { name: "Purge" }));
    const form = screen.getByRole("form", { name: "Purge Acme" });
    const purge = within(form).getByRole("button", { name: "Purge" });
    expect(purge).toBeDisabled();
    fireEvent.change(within(form).getByLabelText(/to confirm/), { target: { value: "Acme" } });
    fireEvent.click(purge);
    expect(await screen.findByRole("status")).toHaveTextContent("Acme is gone for everyone");
    expect(bodyOf(fetchMock, "POST /platform/orgs/o1/purge")).toEqual({ name: "Acme" });
  });
});

function account(overrides: Partial<PlatformUser> = {}): PlatformUser {
  return {
    id: "u-ann",
    email: "ann@acme.io",
    name: "Ann",
    created_at: "2026-10-01T09:00:00Z",
    status: "active",
    is_sysadmin: false,
    locked_until: null,
    temp_password_expires_at: null,
    orgs: [{ org_id: "o1", name: "Acme", role: "admin" }],
    ...overrides,
  };
}

describe("Accounts", () => {
  it("deactivates after confirming, and shows why it was refused", async () => {
    await renderSignedIn(<AccountsPage />, "viewer", sysadminRoutes({
      "GET /platform/users": () => ({ items: [account(), account({ id: "u-root", email: "root@platform.io", name: "Root", is_sysadmin: true, orgs: [] })], total: 2 }),
      "GET /platform/users/facets": () => ({ status: ["active"] }),
      "PATCH /platform/users/u-ann": () =>
        json({ detail: { code: "last_admin", message: "ann@acme.io is the only admin of Acme. Make someone else admin there first." } }, 409),
    }));
    const ann = (await screen.findByText("ann@acme.io")).closest("tr")!;
    fireEvent.click(within(ann).getByRole("button", { name: "Deactivate" }));
    const confirm = screen.getByRole("group", { name: "Confirm" });
    expect(confirm).toHaveTextContent("Deactivate Ann?");
    fireEvent.click(within(confirm).getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("the only admin of Acme");

    // The Sysadmin's own row: only Edit.
    const root = screen.getByText("root@platform.io").closest("tr")!;
    expect(within(root).getAllByRole("button").map((b) => b.textContent)).toEqual(["Edit"]);
  });

  it("changes a role in an org after confirming", async () => {
    const { fetchMock } = await renderSignedIn(<AccountsPage />, "viewer", sysadminRoutes({
      "GET /platform/users": () => ({ items: [account()], total: 1 }),
      "GET /platform/users/facets": () => ({ status: ["active"] }),
      "PATCH /platform/users/u-ann/orgs/o1": () => account({ orgs: [{ org_id: "o1", name: "Acme", role: "auditor" }] }),
    }));
    fireEvent.change(await screen.findByRole("combobox", { name: "Role of Ann in Acme" }), { target: { value: "auditor" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm" })).getByRole("button", { name: "Change role" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Ann is now Auditor in Acme");
    expect(bodyOf(fetchMock, "PATCH /platform/users/u-ann/orgs/o1")).toEqual({ role: "auditor" });
  });
});

const BUILT_IN: SecuritySettings = {
  idle_minutes: 480,
  max_session_days: 7,
  lockout_threshold: 5,
  lockout_window_minutes: 15,
  lock_minutes: 15,
  password_rule: "simple",
  min_length: 14,
  require_upper: true,
  require_lower: true,
  require_digit: true,
  require_symbol: true,
  history_count: 5,
  expiry_days: 0,
};

describe("Security settings", () => {
  it("sends only what changed, and null to go back to the default", async () => {
    setToken("tok");
    const layer = { values: { ...BUILT_IN, idle_minutes: 60 }, changed: ["idle_minutes"], below: BUILT_IN };
    const fetchMock = mockApi({
      "GET /orgs": () => [org()],
      "GET /orgs/org-1/security": () => layer,
      "PATCH /orgs/org-1/security": () => layer,
    });
    render(
      <AppProvider>
        <SecuritySettingsForm path="/orgs/org-1/security" editable belowName="platform default" />
      </AppProvider>,
    );
    const idle = await screen.findByLabelText("Signed out after idle (minutes)");
    expect(idle).toHaveValue(60);
    expect(screen.getByText("(platform default: 480)")).toBeInTheDocument();
    // The Complex rule's settings show only with that rule.
    expect(screen.queryByLabelText("Minimum length")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Use default" }));
    fireEvent.change(screen.getByLabelText("Password rule"), { target: { value: "complex" } });
    fireEvent.change(screen.getByLabelText("Minimum length"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(callsTo(fetchMock, "PATCH /orgs/org-1/security")).toHaveLength(1));
    expect(bodyOf(fetchMock, "PATCH /orgs/org-1/security")).toEqual({
      idle_minutes: null,
      password_rule: "complex",
      min_length: 20,
    });
  });

  it("is read-only for those who can't change it", async () => {
    setToken("tok");
    mockApi({
      "GET /orgs": () => [org()],
      "GET /orgs/org-1/security": () => ({ values: BUILT_IN, changed: [], below: BUILT_IN }),
    });
    render(
      <AppProvider>
        <SecuritySettingsForm path="/orgs/org-1/security" editable={false} belowName="platform default" />
      </AppProvider>,
    );
    expect(await screen.findByLabelText("Signed out after idle (minutes)")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });
});
