import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { mockApi, json } from "@/test/helpers";
import FindingIdentityComparison from "./FindingIdentityComparison";

const path = "/orgs/o1/findings/f1/observations/obs2/identity-binding";
const props = { orgId: "o1", findingId: "f1", observationId: "obs2", disabled: false, onSaved: vi.fn() };
const preview = { review_token: "a".repeat(64), source_observation_id: "obs1", target_version: 0,
  source_finding_id: "f1", target_finding_id: "f1", tool_name: "Reviewed scanner",
  canonical_asset_id: "asset1", target_asset_id: "asset1", result: "same_finding", already_reviewed: false,
  source_material: { plugin_id: "123", port: 0, protocol: "tcp" } };

async function compare() {
  await userEvent.click(screen.getByRole("button", { name: "Review against an earlier observation" }));
  await userEvent.type(screen.getByLabelText("Earlier observation UUID"), "obs1");
  await userEvent.click(screen.getByRole("button", { name: "Compare identity" }));
  await screen.findByText("Scanner: Reviewed scanner");
}

it("compares on demand and requires independent confirmation before saving", async () => {
  let saved: unknown;
  const calls = mockApi({ ["POST " + path + "/compare"]: () => preview,
    ["POST " + path + "/carry-forward"]: init => { saved = JSON.parse(String(init.body)); return {}; } });
  const busy=vi.fn(); render(<FindingIdentityComparison {...props} onBusyChange={busy} />);
  expect(calls).not.toHaveBeenCalled(); await compare();
  expect(screen.getByRole("button", { name: "Save reviewed mapping" })).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Carry-forward review reason"), "Reviewed this upload");
  await userEvent.click(screen.getByLabelText(/I independently verified/));
  await userEvent.click(screen.getByRole("button", { name: "Save reviewed mapping" }));
  await waitFor(() => expect(saved).toEqual({ source_observation_id: "obs1", expected_version: 0,
    review_token: preview.review_token, confirm_mapping: true, rationale: "Reviewed this upload" }));
  expect(busy).toHaveBeenCalledWith(true);
  await waitFor(() => expect(busy).toHaveBeenLastCalledWith(false));
});

it("clears preview and confirmation when the reference changes", async () => {
  mockApi({ ["POST " + path + "/compare"]: () => preview });
  render(<FindingIdentityComparison {...props} />); await compare();
  await userEvent.click(screen.getByLabelText(/I independently verified/));
  await userEvent.type(screen.getByLabelText("Earlier observation UUID"), "other");
  expect(screen.queryByRole("button", { name: "Save reviewed mapping" })).not.toBeInTheDocument();
});

it("shows canonical conflicts without offering to merge or save", async () => {
  mockApi({ ["POST " + path + "/compare"]: () => ({ ...preview, result: "canonical_conflict", target_finding_id: "f2" }) });
  render(<FindingIdentityComparison {...props} />); await compare();
  expect(screen.getByText(/Canonical conflict resolution is required/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "Save reviewed mapping" })).not.toBeInTheDocument();
});

it("requires a new comparison after a stale or uncertain save", async () => {
  mockApi({ ["POST " + path + "/compare"]: () => preview,
    ["POST " + path + "/carry-forward"]: () => json({ detail: "Identity context changed; compare again" }, 409) });
  render(<FindingIdentityComparison {...props} />); await compare();
  await userEvent.type(screen.getByLabelText("Carry-forward review reason"), "Reviewed");
  await userEvent.click(screen.getByLabelText(/I independently verified/));
  await userEvent.click(screen.getByRole("button", { name: "Save reviewed mapping" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Identity context changed");
  expect(screen.queryByRole("button", { name: "Save reviewed mapping" })).not.toBeInTheDocument();
});

it("abandons a cancelled comparison and makes no mutation", async () => {
  const calls=mockApi({ ["POST " + path + "/compare"]: () => preview });
  render(<FindingIdentityComparison {...props} />); await compare();
  await userEvent.click(screen.getByRole("button", { name: "Cancel comparison" }));
  await userEvent.click(screen.getByRole("button", { name: "Review against an earlier observation" }));
  expect(screen.getByLabelText("Earlier observation UUID")).toHaveValue("");
  expect(screen.queryByText("Scanner: Reviewed scanner")).not.toBeInTheDocument();
  expect(calls.mock.calls).toHaveLength(1);
});
