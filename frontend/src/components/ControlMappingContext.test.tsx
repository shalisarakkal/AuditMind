import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import ControlMappingWorkspace from "./ControlMappingWorkspace";

const state = vi.hoisted(() => ({ available: true, responseId: "11111111-1111-4111-8111-111111111111" }));
vi.mock("@/lib/useApi", () => ({ useApi: (path: string | null) => ({
  loading: false, error: null, reload: vi.fn(), data: path?.endsWith("/control-catalogs") ? { available: true, items: [] } : path ? {
    available: state.available, context_kind: "finding", finding_id: state.responseId, rule_id: null,
    source: "manual", domain: "identity_access", category: "Old response category", archived: false, inactive: false,
    version: 0, status: "unmapped", effective: null, proposal: null,
  } : null,
}) }));
beforeEach(() => { state.available = true; state.responseId = "11111111-1111-4111-8111-111111111111"; });

it("does not classify an unavailable mapping capability as Unmapped", () => {
  state.available = false;
  render(<ControlMappingWorkspace orgId="o" orgName="Organization" role="viewer" initialFindingId={state.responseId} />);
  expect(screen.getByRole("heading", { name: "Mapping unavailable" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Unmapped" })).not.toBeInTheDocument();
});

it("does not display a retained prior response as the newly requested context", async () => {
  render(<ControlMappingWorkspace orgId="o" orgName="Organization" role="viewer" initialFindingId={state.responseId} />);
  expect(screen.getByText("Old response category")).toBeVisible();
  // useApi may retain its prior data until the path-change effect sets loading.
  await userEvent.clear(screen.getByLabelText("Finding ID"));
  await userEvent.type(screen.getByLabelText("Finding ID"), "22222222-2222-4222-8222-222222222222");
  await userEvent.click(screen.getByRole("button", { name: "Open / reload finding" }));
  expect(screen.queryByText("Old response category")).not.toBeInTheDocument();
});
