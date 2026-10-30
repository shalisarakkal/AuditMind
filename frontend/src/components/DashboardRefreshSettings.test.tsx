import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import DashboardRefreshSettings from "./DashboardRefreshSettings";
import { renderSignedIn, json } from "@/test/helpers";

const inherited = { enabled: true, platform_refresh_interval_seconds: 3600, refresh_interval_seconds: 3600, refresh_interval_override_seconds: null as number | null, version: 0 };

it("saves an override and restores inheritance only after checkbox plus Save", async () => {
  let current = inherited;
  const writes: unknown[] = [];
  await renderSignedIn(<DashboardRefreshSettings orgId="org-1" editable />, "admin", {
    "GET /orgs/org-1/dashboard/settings": () => current,
    "PATCH /orgs/org-1/dashboard/settings": init => {
      const body = JSON.parse(String(init.body)); writes.push(body);
      current = { ...current, version: current.version + 1, refresh_interval_override_seconds: body.refresh_interval_override_seconds,
        refresh_interval_seconds: body.refresh_interval_override_seconds ?? current.platform_refresh_interval_seconds };
      return current;
    },
  });
  expect(await screen.findByText(/Effective interval: 60 minutes \(inherited\)/)).toBeVisible();
  fireEvent.click(screen.getByRole("checkbox", { name: "Inherit Platform refresh interval" }));
  fireEvent.change(screen.getByLabelText("Organization refresh interval (minutes)"), { target: { value: "10" } });
  fireEvent.click(screen.getByRole("button", { name: "Save refresh interval" }));
  await screen.findByText(/Effective interval: 10 minutes \(organization override\)/);
  expect(screen.queryByRole("button", { name: "Reset to Platform default" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "Inherit Platform refresh interval" }));
  expect(writes).toHaveLength(1);
  expect(screen.getByText(/Effective interval: 10 minutes \(organization override\)/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Save refresh interval" }));
  await screen.findByText(/Effective interval: 60 minutes \(inherited\)/);
  expect(writes).toEqual([{ expected_version: 0, refresh_interval_override_seconds: 600 }, { expected_version: 1, refresh_interval_override_seconds: null }]);
});

it("shows inherited settings read-only to non-admins", async () => {
  await renderSignedIn(<DashboardRefreshSettings orgId="org-1" editable={false} />, "viewer", {
    "GET /orgs/org-1/dashboard/settings": () => inherited,
  });
  expect(await screen.findByText(/Read-only: an organization administrator/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "Save refresh interval" })).not.toBeInTheDocument();
});

it("requires explicit reload after another administrator changes the override", async () => {
  await renderSignedIn(<DashboardRefreshSettings orgId="org-1" editable />, "admin", {
    "GET /orgs/org-1/dashboard/settings": () => inherited,
    "PATCH /orgs/org-1/dashboard/settings": () => json({ detail: "Dashboard refresh settings changed" }, 409),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Save refresh interval" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save refresh interval" })).toBeDisabled());
  expect(screen.getByRole("button", { name: "Reload saved settings" })).toBeEnabled();
});
