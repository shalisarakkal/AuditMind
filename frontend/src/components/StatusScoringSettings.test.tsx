import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import StatusScoringSettings from "./StatusScoringSettings";
import { renderSignedIn, json } from "@/test/helpers";

const initial = { enabled: true, platform_enabled: true, enabled_override: null as boolean | null, version: 0, platform_version: 0 };

it("saves explicit Off and restores Platform inheritance with one Save action", async () => {
  let current = initial;
  const writes: unknown[] = [];
  await renderSignedIn(<StatusScoringSettings orgId="org-1" editable />, "admin", {
    "GET /orgs/org-1/status-scoring": () => current,
    "PATCH /orgs/org-1/status-scoring": init => {
      const body = JSON.parse(String(init.body)); writes.push(body);
      current = { ...current, enabled_override: body.enabled_override,
        enabled: body.enabled_override ?? current.platform_enabled, version: current.version + 1 };
      return current;
    },
  });
  const select = await screen.findByLabelText("Organization policy");
  expect(select).toHaveValue("inherit");
  fireEvent.change(select, { target: { value: "off" } });
  fireEvent.click(screen.getByRole("button", { name: "Save scoring policy" }));
  await screen.findByText(/Effective policy: Off/);
  fireEvent.change(screen.getByLabelText("Organization policy"), { target: { value: "inherit" } });
  fireEvent.click(screen.getByRole("button", { name: "Save scoring policy" }));
  await screen.findByText(/Effective policy: On/);
  expect(writes).toEqual([{ expected_version: 0, enabled_override: false }, { expected_version: 1, enabled_override: null }]);
});

it("requires reload after a conflicting update", async () => {
  await renderSignedIn(<StatusScoringSettings orgId="org-1" editable />, "admin", {
    "GET /orgs/org-1/status-scoring": () => initial,
    "PATCH /orgs/org-1/status-scoring": () => json({ detail: "Policy changed" }, 409),
  });
  fireEvent.click(await screen.findByRole("button", { name: "Save scoring policy" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save scoring policy" })).toBeDisabled());
  expect(screen.getByRole("button", { name: "Reload saved policy" })).toBeEnabled();
});

it("shows effective settings without mutation controls to read-only members", async () => {
  await renderSignedIn(<StatusScoringSettings orgId="org-1" editable={false} />, "viewer", {
    "GET /orgs/org-1/status-scoring": () => initial,
  });
  await screen.findByText(/Effective policy: On/);
  expect(screen.queryByRole("button", { name: "Save scoring policy" })).not.toBeInTheDocument();
});
