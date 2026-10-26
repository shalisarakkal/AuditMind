import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FindingLookupPage from "@/app/(app)/findings/lookup/page";

const state = vi.hoisted(() => ({ org: "11111111-1111-4111-8111-111111111111", id: "22222222-2222-4222-8222-222222222222", selected: "", allowed: true, replace: vi.fn(), select: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }), useSearchParams: () => new URLSearchParams({ org: state.org, finding_id: state.id }) }));
vi.mock("@/context/AppContext", () => ({ useApp: () => ({ orgs: state.allowed ? [{ id: state.org }] : [], selectedOrg: { id: state.selected }, orgsLoading: false, orgsError: null, selectOrg: state.select }) }));
beforeEach(() => { state.selected = state.org; state.allowed = true; state.id = "22222222-2222-4222-8222-222222222222"; vi.clearAllMocks(); });
describe("Finding lookup", () => {
  it("opens an exact finding filter only after the correct organization is selected", async () => {
    state.selected = "other";
    const view = render(<FindingLookupPage />);
    await waitFor(() => expect(state.select).toHaveBeenCalledWith(state.org));
    expect(state.replace).not.toHaveBeenCalled();
    state.selected = state.org; view.rerender(<FindingLookupPage />);
    await waitFor(() => expect(state.replace).toHaveBeenCalledWith(`/findings?org=${state.org}&finding_id=${state.id}`));
  });
  it("rejects unavailable organizations without switching or navigating", () => {
    state.allowed = false; render(<FindingLookupPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("do not have access");
    expect(state.select).not.toHaveBeenCalled(); expect(state.replace).not.toHaveBeenCalled();
  });
  it("rejects malformed references", () => {
    state.id = "bad"; render(<FindingLookupPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid finding reference");
    expect(state.replace).not.toHaveBeenCalled();
  });
});
