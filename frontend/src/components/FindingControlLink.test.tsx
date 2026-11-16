import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import FindingControlLink from "./FindingControlLink";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));
beforeEach(() => navigation.push.mockClear());

it("opens the fixed finding context and describes its pending mapping", async () => {
  render(<FindingControlLink orgId="org" findingId="finding" disabled={false} summary={{ available: true, status: "unmapped", proposal_pending: true, version: 1, catalog_id: null }} />);
  const button = screen.getByRole("button", { name: "Controls" });
  expect(button).toHaveAccessibleDescription("Unmapped · Proposal pending");
  await userEvent.click(button);
  expect(navigation.push).toHaveBeenCalledWith("/controls?org=org&finding_id=finding");
});

it("blocks individual navigation while selection or another operation owns the row", async () => {
  render(<FindingControlLink orgId="org" findingId="finding" disabled />);
  const button = screen.getByRole("button", { name: "Controls" });
  expect(button).toBeDisabled();
  await userEvent.click(button);
  expect(navigation.push).not.toHaveBeenCalled();
});

it("does not call unavailable mapping data Unmapped", () => {
  render(<FindingControlLink orgId="org" findingId="finding" disabled={false} summary={{ available: false, status: "unmapped", proposal_pending: false, version: 0, catalog_id: null }} />);
  expect(screen.getByRole("button", { name: "Controls" })).toHaveAccessibleDescription("Not available");
  expect(screen.queryByText("Unmapped")).not.toBeInTheDocument();
});
