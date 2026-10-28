import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GenerateReportModal } from "@/components/GenerateReportModal";
import { mockApi, json } from "@/test/helpers";

const base = { orgId: "sa01", orgName: "SA01", canApprove: true, isOpen: true,
  onClose: vi.fn(), onGenerate: vi.fn().mockResolvedValue(undefined) };

describe("Report generation dialog", () => {
  it("does not reuse approval across organizations or dialog openings", async () => {
    let approved = true;
    mockApi({
      "GET /orgs/sa01/documents/settings": () => ({ report_granted: approved }),
      "GET /orgs/sa02/documents/settings": () => ({ report_granted: false }),
    });
    const view = render(<GenerateReportModal {...base} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate report" })).toBeEnabled());
    view.rerender(<GenerateReportModal {...base} orgId="sa02" orgName="SA02" />);
    expect(screen.getByRole("button", { name: "Generate report" })).toBeDisabled();
    await screen.findByText(/not approved for SA02/);
    view.rerender(<GenerateReportModal {...base} isOpen={false} />);
    approved = false;
    view.rerender(<GenerateReportModal {...base} />);
    expect(screen.getByRole("button", { name: "Generate report" })).toBeDisabled();
    await screen.findByText(/not approved for SA01/);
  });
  it("wraps Tab and Shift+Tab inside the dialog", () => {
    render(<GenerateReportModal {...base} mode="rule_based_test" />);
    const first = screen.getByRole("button", { name: "Close report generation" });
    const last = screen.getByRole("button", { name: "Generate test report" });
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
  });
  it("checks approval and blocks generation with an organization-scoped next action", async () => {
    const generate = vi.fn();
    mockApi({ "GET /orgs/sa01/documents/settings": () => ({ report_granted: false }) });
    render(<GenerateReportModal {...base} onGenerate={generate} />);
    expect(screen.getByLabelText("Report title")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Generate report" })).toBeDisabled();
    expect(await screen.findByText(/not approved for SA01/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review consent in Documents" })).toHaveAttribute("href", "/documents?org=sa01");
    fireEvent.submit(screen.getByLabelText("Report title").closest("form")!);
    expect(generate).not.toHaveBeenCalled();
  });

  it("tells auditors to ask an admin, without granting consent", async () => {
    const fetchMock = mockApi({ "GET /orgs/sa01/documents/settings": () => ({ report_granted: false }) });
    render(<GenerateReportModal {...base} canApprove={false} />);
    expect(await screen.findByText(/Ask an organization admin/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([, init]) => init?.method === "GET")).toBe(true);
  });

  it("fails closed on approval-check errors and recovers with Retry", async () => {
    let failed = true;
    mockApi({ "GET /orgs/sa01/documents/settings": () => failed ? json({ detail: "Unavailable" }, 503) : { report_granted: true, report_target: "test-target" } });
    render(<GenerateReportModal {...base} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
    expect(screen.getByRole("button", { name: "Generate report" })).toBeDisabled();
    failed = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry approval check" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate report" })).toBeEnabled());
    expect(screen.getByRole("group", { name: "Frameworks" })).toBeInTheDocument();
  });

  it("validates framework selection, announces errors and prevents duplicate submission", async () => {
    mockApi({ "GET /orgs/sa01/documents/settings": () => ({ report_granted: true }) });
    const user = userEvent.setup();
    let resolve!: () => void;
    const generate = vi.fn(() => new Promise<void>(done => { resolve = done; }));
    const close = vi.fn();
    render(<GenerateReportModal {...base} onGenerate={generate} onClose={close} />);
    const submit = screen.getByRole("button", { name: "Generate report" });
    await waitFor(() => expect(submit).toBeEnabled());
    for (const checkbox of screen.getAllByRole("checkbox")) await user.click(checkbox);
    await user.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("Select at least one framework");
    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.click(submit);
    fireEvent.submit(submit.closest("form")!);
    expect(generate).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Close report generation" })).toBeDisabled();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(close).not.toHaveBeenCalled();
    resolve();
    await waitFor(() => expect(submit).not.toHaveTextContent("Queueing"));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("rechecks consent after server refusal", async () => {
    let approved = true;
    mockApi({ "GET /orgs/sa01/documents/settings": () => ({ report_granted: approved }) });
    render(<GenerateReportModal {...base} onGenerate={async () => { approved = false; throw new Error("Consent revoked"); }} />);
    const submit = screen.getByRole("button", { name: "Generate report" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("Consent revoked");
    await screen.findByText(/not approved for SA01/);
    expect(submit).toBeDisabled();
  });

  it("closes on native Escape cancellation and restores the opener's focus", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>Open preview</button><GenerateReportModal {...base} mode="rule_based_test" isOpen={open} onClose={() => setOpen(false)} /></>;
    }
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open preview" });
    await user.click(opener);
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: false, cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("allows explicitly non-AI previews without fetching consent", async () => {
    const fetchMock = mockApi({});
    const generate = vi.fn().mockResolvedValue(undefined);
    render(<GenerateReportModal {...base} mode="rule_based_test" onGenerate={generate} />);
    expect(screen.getByRole("note")).toHaveTextContent("does not use AI or an external provider");
    fireEvent.click(screen.getByRole("button", { name: "Generate test report" }));
    await waitFor(() => expect(generate).toHaveBeenCalledWith(expect.objectContaining({ frameworks: [] }), "rule_based_test"));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
