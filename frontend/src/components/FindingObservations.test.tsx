import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json, mockApi } from "@/test/helpers";
import FindingObservations from "./FindingObservations";

const observation = { id: "obs-1", import_id: "import-1", filename: "source.csv", source: "scanner", source_row: 2,
  recorded_at: "2026-11-05T12:00:00Z", observed_at: null, reconciliation_eligible: false,
  ineligibility_reasons: ["stable_source_identifier_unavailable"],
  payload: { severity: "critical", category: "RULE-1", description: "Source description" } };

describe("Finding source observations", () => {
  it("shows a recoverable API error and an honest empty history after retry", async () => {
    let attempts = 0;
    mockApi({ "GET /orgs/o1/findings/f1/observations": () => ++attempts === 1
      ? json({ detail: "Source history temporarily unavailable" }, 503) : [] });
    render(<FindingObservations orgId="o1" findingId="f1" />);
    await userEvent.click(screen.getByRole("button", { name: "Show source observations" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Source history temporarily unavailable");
    expect(screen.getByRole("button", { name: "Older observations" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Retry observations" }));
    expect(await screen.findByText("No source observations recorded.")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("loads on demand and keeps source history separate from workflow", async () => {
    const calls = mockApi({ "GET /orgs/o1/findings/f1/observations": () => [observation] });
    render(<FindingObservations orgId="o1" findingId="f1" />);
    expect(screen.queryByText("source.csv · Row 2")).not.toBeInTheDocument();
    expect(calls).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Show source observations" }));
    expect(await screen.findByText("source.csv · Row 2")).toBeVisible();
    expect(screen.getByText("Source observed time: Not provided")).toBeVisible();
    expect(screen.getByText("Not eligible for automatic reconciliation")).toBeVisible();
    expect(screen.getByText("Stable source finding identifier is unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: "Older observations" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Hide source observations" }));
    expect(screen.queryByText("source.csv · Row 2")).not.toBeInTheDocument();
  });

  it("shows identity diagnostics without granting reconciliation authority", async () => {
    mockApi({ "GET /orgs/o1/findings/f1/observations": () => [{ ...observation,
      identity_assessment: { version: "finding-identity-v1", mapping: "nessus-plugin-service-v1", candidate_key: null } }] });
    render(<FindingObservations orgId="o1" findingId="f1" />);
    await userEvent.click(screen.getByRole("button", { name: "Show source observations" }));
    await userEvent.click(await screen.findByText("Identity assessment"));
    expect(screen.getByText("Source mapping: nessus-plugin-service-v1")).toBeVisible();
    expect(screen.getByText(/Unavailable until tool and asset bindings/)).toBeVisible();
    expect(screen.getByText("Not eligible for automatic reconciliation")).toBeVisible();
    expect(screen.getByText(/Identity diagnostics do not authorize/)).toBeVisible();
    expect(screen.queryByRole("button", {name:"Review identity binding"})).not.toBeInTheDocument();
  });

  it("uses the last observation as a seek cursor and can return to newer entries", async () => {
    mockApi({ "GET /orgs/o1/findings/f1/observations?limit=20&before=obs-19": () => [{ ...observation, id: "old", filename: "older.csv" }],
      "GET /orgs/o1/findings/f1/observations": () => Array.from({ length: 20 }, (_, i) => ({ ...observation, id: `obs-${i}` })) });
    render(<FindingObservations orgId="o1" findingId="f1" />);
    await userEvent.click(screen.getByRole("button", { name: "Show source observations" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Older observations" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Older observations" }));
    expect(await screen.findByText("older.csv · Row 2")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Newer observations" }));
    await waitFor(() => expect(screen.getAllByText("source.csv · Row 2")).toHaveLength(20));
  });
});
