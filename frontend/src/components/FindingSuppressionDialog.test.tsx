import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { callsTo, json, mockApi } from "@/test/helpers";
import FindingSuppressionDialog from "./FindingSuppressionDialog";
import SuppressedFindingsDialog from "./SuppressedFindingsDialog";

const preview = { label: "Synthetic native finding", finding_id: "f1", review_token: "a".repeat(64), expected_version: 0,
  lifecycle: "retained", finding_status: "open", identity: { tool_name: "Reviewed scanner", candidate_key: "native-v1",
    source_material: { plugin_id: "1001", port: 443, protocol: "tcp" } } };
const props = { orgId: "o1", orgName: "Synthetic org", target: { action: "suppress" as const, finding_id: "f1" }, onClose: vi.fn(), onSaved: vi.fn() };
const root = "/orgs/o1/finding-suppressions";

async function complete() {
  await screen.findByText("Synthetic native finding");
  await userEvent.type(screen.getByLabelText("Rationale"), "Reviewed exact scanner identity");
  await userEvent.click(screen.getByRole("checkbox"));
}

describe("Reviewed finding suppression", () => {
  it("requires rationale and explicit target confirmation and submits the server token", async () => {
    const onSaved = vi.fn();
    const calls = mockApi({ [`POST ${root}/preview`]: () => preview, [`POST ${root}/decisions`]: () => ({ state: "suppressed" }) });
    render(<FindingSuppressionDialog {...props} onSaved={onSaved} />);
    const button = await screen.findByRole("button", { name: "Suppress finding" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Rationale"), "Review");
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(button);
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    const body = JSON.parse(String(callsTo(calls, `POST ${root}/decisions`)[0][1].body));
    expect(body).toMatchObject({ finding_id: "f1", review_token: preview.review_token, expected_version: 0, rationale: "Review", confirm: true });
    expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("freezes dismissal, inputs and repeated submission while the request is held", async () => {
    let release!: (value: object) => void;
    const held = new Promise<object>(resolve => { release = resolve; });
    const onClose = vi.fn(); const onSaved = vi.fn();
    const calls = mockApi({ [`POST ${root}/preview`]: () => preview, [`POST ${root}/decisions`]: () => held });
    render(<FindingSuppressionDialog {...props} onClose={onClose} onSaved={onSaved} />);
    await complete();
    await userEvent.click(screen.getByRole("button", { name: "Suppress finding" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByLabelText("Rationale")).toBeDisabled();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }));
    expect(onClose).not.toHaveBeenCalled();
    expect(callsTo(calls, `POST ${root}/decisions`)).toHaveLength(1);
    release({ state: "suppressed" });
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it("retains rationale on a stale context and requires a new preview", async () => {
    mockApi({ [`POST ${root}/preview`]: () => preview,
      [`POST ${root}/decisions`]: () => json({ detail: "Identity changed; reload preview" }, 409) });
    render(<FindingSuppressionDialog {...props} />);
    await complete(); await userEvent.click(screen.getByRole("button", { name: "Suppress finding" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed");
    expect(screen.getByRole("button", { name: "Suppress finding" })).toBeDisabled();
    expect(screen.getByLabelText("Rationale")).toHaveValue("Reviewed exact scanner identity");
    await userEvent.click(screen.getByRole("button", { name: "Reload preview" }));
    await waitFor(() => expect(screen.getByLabelText("Rationale")).toBeEnabled());
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByLabelText("Rationale")).toHaveValue("Reviewed exact scanner identity");
  });

  it("retries an uncertain outcome using the identical request and rationale", async () => {
    let attempt = 0;
    const calls = mockApi({ [`POST ${root}/preview`]: () => preview,
      [`POST ${root}/decisions`]: () => ++attempt === 1 ? json({ detail: "Temporary gateway failure" }, 503) : { replayed: true } });
    const onSaved = vi.fn();
    render(<FindingSuppressionDialog {...props} onSaved={onSaved} />);
    await complete(); await userEvent.click(screen.getByRole("button", { name: "Suppress finding" }));
    expect(await screen.findByText(/outcome is unknown/)).toBeVisible();
    expect(screen.getByLabelText("Rationale")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    const requests = callsTo(calls, `POST ${root}/decisions`);
    expect(requests[0][1].body).toEqual(requests[1][1].body);
  });

  it("explains an unsupported identity without offering a write", async () => {
    const calls = mockApi({ [`POST ${root}/preview`]: () => json({ detail: "Review every retained observation" }, 409) });
    render(<FindingSuppressionDialog {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Review every");
    expect(screen.queryByRole("button", { name: "Suppress finding" })).not.toBeInTheDocument();
    expect(callsTo(calls, `POST ${root}/decisions`)).toHaveLength(0);
  });

  it.each(["purged", "archived"])("clearing a %s payload explains what cannot be restored", async lifecycle => {
    mockApi({ [`POST ${root}/preview`]: () => ({ ...preview, lifecycle }) });
    render(<FindingSuppressionDialog {...props} target={{ action: "clear", suppression_id: "s1" }} />);
    const target = await screen.findByRole("region", { name: "Reviewed suppression target" });
    expect(target).toHaveTextContent(lifecycle === "purged" ? "cannot be restored" : "remains archived");
    expect(screen.getByRole("button", { name: "Clear suppression" })).toBeDisabled();
  });

  it.each(["viewer", "auditor"])("keeps %s suppression management read-only", async role => {
    mockApi({ [`GET ${root}`]: () => ({ items: [{ id: "s1", finding_id: "f1", label: "Suppressed native", state: "suppressed", version: 1, reappearance_count: 0 }], has_more: false }),
      [`GET ${root}/s1/history`]: () => ({ items: [{ id: "d1", version: 1, state: "suppressed", actor_label: "Reviewed administrator", rationale: "Recorded rationale", created_at: "2026-11-11T12:00:00Z" }], has_more: false }) });
    render(<SuppressedFindingsDialog orgId="o1" orgName="Synthetic org" role={role} onClose={vi.fn()} onSaved={vi.fn()} />);
    await screen.findByText("Suppressed native");
    expect(screen.queryByRole("button", { name: "Clear suppression" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Recorded rationale")).toBeVisible();
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" })).toBeEnabled();
  });
});
