import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EvidenceScoringSettings from "./EvidenceScoringSettings";
import { mockApi } from "@/test/helpers";
import type { EvidenceEvaluationJob } from "./EvidenceEvaluationPanel";

function stream(data: unknown) {
  return new Response(JSON.stringify({ type: "progress", phase: "assets", processed: 2, total: 5, elapsed_seconds: 1 }) + "\n" + JSON.stringify({ type: "result", data }) + "\n", { headers: { "Content-Type": "application/x-ndjson" } });
}

function setup(editable = true, holdProgress = false) {
  const writes: unknown[] = [];
  let expensiveReads = 0;
  const saved = { rows: [] as unknown[], reads: 0, fail: false };
  let mode = { evidence_qualified_enabled: false, version: 0, available: true };
  let job: EvidenceEvaluationJob | null = null;
  function progressResponse(data: unknown, init: RequestInit) {
    if (!holdProgress) return stream(data);
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode(JSON.stringify({ type: "progress", phase: "assets", processed: 2, total: 5 }) + "\n"));
      init.signal?.addEventListener("abort", () => controller.error(new DOMException("Cancelled", "AbortError")));
    } }), { headers: { "Content-Type": "application/x-ndjson" } });
  }
  mockApi({
    "GET /orgs/org-1/scoring/settings": () => mode,
    "PATCH /orgs/org-1/scoring/settings": init => { const body = JSON.parse(String(init.body)); writes.push({ mode: body }); mode = { ...mode, ...body, version: mode.version + 1 }; return mode; },
    "GET /orgs/org-1/scoring/evaluations/current": () => job,
    "POST /orgs/org-1/scoring/evaluations": () => {
      expensiveReads++;
      job = { id: "job-1", status: holdProgress ? "running" : "completed", created_at: new Date().toISOString(), run_started_at: new Date().toISOString(), cancel_requested_at: null,
        can_cancel: holdProgress, is_current: !holdProgress, error_message: null, progress: { phase: "assets", processed: 2, total: 5 },
        result: holdProgress ? null : { evaluated_at: new Date().toISOString(), assessment_status: "not_assessed", qualified_domain_count: 0, domains: [{ domain: "identity_access", reason_code: "no_evidence", eligible: false }] } };
      return job;
    },
    "POST /orgs/org-1/scoring/evaluations/job-1/cancel": () => { job = { ...job!, status: "cancelled", can_cancel: false }; return job; },
    "GET /orgs/org-1/scoring/profiles": () => ({ profiles: { identity_access: ["access_review"] } }),
    "GET /orgs/org-1/scoring/qualifications": () => { saved.reads++; return saved.fail ? new Response(JSON.stringify({ detail: "Reload unavailable" }), { status: 500 }) : saved.rows; },
    "GET /orgs/org-1/scoring/progress/inventory": init => { expensiveReads++; return progressResponse({ inventory_sha256: "a".repeat(64), asset_count: 2, finding_count: 3 }, init); },
    "PUT /orgs/org-1/scoring/qualifications/identity_access": init => {
      const body = JSON.parse(String(init.body)); writes.push(body);
      return { ...body, domain: "identity_access", version: 1, status: "draft" };
    },
    "POST /orgs/org-1/scoring/qualifications/identity_access/review": init => {
      const body = JSON.parse(String(init.body)); writes.push({ review: body });
      return { ...(saved.rows[0] as Record<string, unknown>), version: 8, status: "approved" };
    },
    "POST /orgs/org-1/scoring/qualifications/identity_access/revoke": init => {
      const body = JSON.parse(String(init.body)); writes.push({ revoke: body });
      return { ...(saved.rows[0] as Record<string, unknown>), version: 8, status: "revoked" };
    },
  });
  render(<EvidenceScoringSettings orgId="org-1" editable={editable} />);
  return { writes, reads: () => expensiveReads, saved };
}

describe("EvidenceScoringSettings", () => {
  it.each(["evaluation", "inventory"] as const)("keeps %s progress, errors and active Cancel beside its owning action", async kind => {
    setup(true, true);
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled());
    if (kind === "inventory") { fireEvent.click(open); await screen.findByLabelText("Scope description"); }
    const region = screen.getByRole("region", { name: kind === "evaluation" ? "Organization-wide evidence evaluation" : "Domain qualification" });
    const progressName = kind === "evaluation" ? "Organization evaluation progress" : "Inventory loading progress";
    const submit = within(region).getByRole("button", { name: kind === "evaluation" ? "Evaluate evidence across all domains" : "Load current inventory" });
    await waitFor(() => expect(submit).toBeEnabled()); fireEvent.click(submit);
    const status = await within(region).findByRole("status", { name: progressName });
    await waitFor(() => expect(status).toHaveTextContent("2 / 5 records"));
    const cancel = within(status).getByRole("button", { name: "Cancel operation" });
    expect(cancel).toBeEnabled();
    if (kind === "inventory") expect(open).toBeDisabled();
    else expect(open).toBeEnabled(); // A background job does not lock the editor.
    expect(screen.getAllByRole("status", { name: progressName })).toHaveLength(1);
    const other = screen.getByRole("region", { name: kind === "evaluation" ? "Domain qualification" : "Organization-wide evidence evaluation" });
    expect(within(other).queryByRole("status", { name: progressName })).not.toBeInTheDocument();
    fireEvent.click(cancel);
    if (kind === "inventory") expect(await within(region).findByRole("alert")).toHaveTextContent(/cancelled/i);
    else await within(region).findByText(/Evaluation cancelled/);
    await waitFor(() => expect(open).toBeEnabled());
    expect(within(region).queryByRole("button", { name: "Cancel operation" })).not.toBeInTheDocument();
    expect(status).toHaveTextContent(kind === "inventory" ? "Stopped" : "cancelled");
  });
  it("keeps scoring off by default and expensive checks explicit", async () => {
    const state = setup();
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    await waitFor(() => expect(screen.getByRole("button", { name: "Open / reload domain" })).toBeEnabled());
    expect(state.reads()).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Evaluate evidence across all domains" }));
    expect(await screen.findByText(/Coverage assessment: not assessed/)).toBeInTheDocument();
    expect(state.reads()).toBe(1);
  });
  it("requires application confirmation before a versioned mode change", async () => {
    const state = setup();
    const toggle = screen.getByRole("checkbox");
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    let dialog = screen.getByRole("dialog", { name: "Change Dashboard scoring mode?" });
    expect(state.writes).toHaveLength(0); expect(toggle).not.toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(state.writes).toHaveLength(0);
    fireEvent.click(toggle); dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Enable evidence-qualified scoring" }));
    await waitFor(() => expect(toggle).toBeChecked());
    expect(state.writes).toEqual([{ mode: { expected_version: 0, evidence_qualified_enabled: true } }]);
  });
  it("saves a versioned inventory-bound draft without enabling scoring", async () => {
    const state = setup();
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await screen.findByLabelText("Scope description");
    fireEvent.change(screen.getByLabelText("Scope description"), { target: { value: "Entire organization" } });
    fireEvent.change(screen.getByLabelText("Evidence rationale"), { target: { value: "Operational review" } });
    fireEvent.click(screen.getByRole("button", { name: "Load current inventory" }));
    await screen.findByText("2 assets · 3 findings");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(state.writes).toHaveLength(1));
    expect(state.writes[0]).toMatchObject({ expected_version: 0, inventory_sha256: "a".repeat(64), observations: [] });
    await screen.findByText(/Draft saved/);
    expect(screen.getByRole("button", { name: "Approve saved evidence" })).toBeDisabled();
  });
  it("makes the editor read-only for non-admin members", async () => {
    setup(false);
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await screen.findByLabelText("Scope description");
    expect(screen.getByLabelText("Scope description")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
  });
  it("does not show a discard popup for a read-only reload", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { saved } = setup(false);
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await screen.findByLabelText("Scope description");
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await waitFor(() => expect(saved.reads).toBe(3));
    expect(confirm).not.toHaveBeenCalled();
  });
  it("reloads the latest server record without prompting for a clean form", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { saved } = setup();
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await screen.findByLabelText("Scope description");
    saved.rows = [{ domain: "identity_access", scope: "Updated by another reviewer", rationale: "New rationale", status: "draft", version: 2, observations: [] }];
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await waitFor(() => expect(screen.getByLabelText("Scope description")).toHaveValue("Updated by another reviewer"));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByText(/Version 2/)).toBeVisible();
  });
  it("protects edits on Cancel and on a failed confirmed reload", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { saved } = setup();
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    const scope = await screen.findByLabelText("Scope description");
    fireEvent.change(scope, { target: { value: "Unsaved scope" } });
    fireEvent.click(open);
    let dialog = screen.getByRole("dialog", { name: "Discard unsaved edits?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(open).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(confirm).not.toHaveBeenCalled(); expect(saved.reads).toBe(2);
    expect(scope).toHaveValue("Unsaved scope");
    fireEvent.change(screen.getByLabelText("Domain"), { target: { value: "network_config" } });
    expect(screen.getByLabelText("Domain")).toHaveValue("identity_access");
    dialog = screen.getByRole("dialog", { name: "Discard unsaved edits?" });
    expect(within(dialog).getByRole("button", { name: "Discard and switch" })).toBeEnabled();
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    saved.fail = true;
    fireEvent.click(open);
    fireEvent.click(screen.getByRole("button", { name: "Discard and reload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Reload unavailable");
    expect(scope).toHaveValue("Unsaved scope");
    await waitFor(() => expect(open).toBeEnabled());
    saved.fail = false;
    fireEvent.click(open);
    fireEvent.click(screen.getByRole("button", { name: "Discard and reload" }));
    await waitFor(() => expect(scope).toHaveValue(""));
    confirm.mockClear();
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    await waitFor(() => expect(saved.reads).toBe(5));
    expect(confirm).not.toHaveBeenCalled();
  });
  it("discards and switches only after application confirmation", async () => {
    setup();
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    fireEvent.change(await screen.findByLabelText("Scope description"), { target: { value: "Unsaved" } });
    fireEvent.change(screen.getByLabelText("Domain"), { target: { value: "network_config" } });
    expect(screen.getByRole("dialog")).toHaveTextContent("Identity & Access and switch to Network & Config");
    fireEvent.click(screen.getByRole("button", { name: "Discard and switch" }));
    await waitFor(() => expect(screen.getByLabelText("Domain")).toHaveValue("network_config"));
    expect(screen.queryByLabelText("Scope description")).not.toBeInTheDocument();
  });
  it.each([
    ["draft", "review", "Approve saved evidence"],
    ["approved", "revoke", "Revoke qualification"],
  ] as const)("confirms %s actions in the application before sending the frozen version", async (status, operation, label) => {
    const browserConfirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const state = setup();
    state.saved.rows = [{ domain: "identity_access", scope: "Saved scope", rationale: "Saved rationale", status, version: 7, inventory_sha256: "a".repeat(64), observations: [] }];
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    fireEvent.change(await screen.findByLabelText("Review / revocation note"), { target: { value: "Reviewed reason" } });
    if (status === "draft") {
      fireEvent.change(screen.getByLabelText("Review expiry"), { target: { value: "2026-10-28T15:00" } });
      fireEvent.click(screen.getByLabelText(/I reviewed operational evidence/));
    }
    fireEvent.click(screen.getByRole("button", { name: label }));
    let dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("version 7"); expect(state.writes).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(state.writes).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: label }));
    dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
    await waitFor(() => expect(state.writes).toHaveLength(1));
    expect(state.writes[0]).toMatchObject({ [operation]: { expected_version: 7, note: "Reviewed reason" } });
    expect(browserConfirm).not.toHaveBeenCalled();
  });
  it("keeps organization evaluation outside the domain editor and preserves unsaved edits", async () => {
    const state = setup();
    const region = screen.getByRole("region", { name: "Organization-wide evidence evaluation" });
    expect(region).toHaveTextContent("The domain selected below does not limit this evaluation");
    expect(region.querySelector("select")).toBeNull();
    const open = screen.getByRole("button", { name: "Open / reload domain" });
    await waitFor(() => expect(open).toBeEnabled()); fireEvent.click(open);
    const scope = await screen.findByLabelText("Scope description");
    fireEvent.change(scope, { target: { value: "Unsaved scope" } });
    fireEvent.click(screen.getByRole("button", { name: "Evaluate evidence across all domains" }));
    await screen.findByText(/Coverage assessment:/);
    expect(scope).toHaveValue("Unsaved scope");
    expect(state.reads()).toBe(1);
  });
});
