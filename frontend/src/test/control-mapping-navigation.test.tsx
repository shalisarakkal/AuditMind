import { useState } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import ControlsPage from "@/app/(app)/controls/page";
import { renderSignedIn } from "./helpers";

const first = "11111111-1111-4111-8111-111111111111", second = "22222222-2222-4222-8222-222222222222";
const navigation = vi.hoisted(() => ({ finding: "11111111-1111-4111-8111-111111111111" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/controls", useRouter: () => ({ replace: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams({ org: "org-1", finding_id: navigation.finding }) }));

it("opens the new finding context when the controls-page query changes", async () => {
  navigation.finding = first;
  function Driver() {
    const [renderCount, renderAgain] = useState(0);
    return <><button type="button" onClick={() => { navigation.finding = second; renderAgain(n => n + 1); }}>Navigate to second control context {renderCount}</button><ControlsPage /></>;
  }
  const base = { available: true, source: "manual", domain: "identity_access", archived: false, inactive: false, version: 0, rule_id: null, status: "unmapped", effective: null, proposal: null };
  await renderSignedIn(<Driver />, "viewer", {
    "GET /orgs/org-1/control-catalogs": () => ({ available: true, items: [] }),
    [`GET /orgs/org-1/findings/${first}/control-mapping`]: () => ({ ...base, finding_id: first, category: "First synthetic category" }),
    [`GET /orgs/org-1/findings/${second}/control-mapping`]: () => ({ ...base, finding_id: second, category: "Second synthetic category" }),
  });
  await screen.findByText("First synthetic category");
  await userEvent.click(screen.getByRole("button", { name: "Navigate to second control context 0" }));
  expect(await screen.findByText("Second synthetic category")).toBeVisible();
  expect(screen.getByLabelText("Finding ID")).toHaveValue(second);
});
