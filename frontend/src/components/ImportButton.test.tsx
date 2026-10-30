import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ImportButton from "@/components/ImportButton";
import { json, renderSignedIn, requestInit, scan } from "@/test/helpers";
import { BUILTIN_PROFILES, CUSTOM_EDR_PROFILE } from "@/test/profiles";

const TRACK = { "GET /orgs/org-1/scans/s1": () => scan() };

function renderButton(routes: Parameters<typeof renderSignedIn>[2]) {
  return renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv,.nessus" label="Upload findings" />, "admin", {
    ...TRACK,
    ...routes,
  });
}

function pickFile(name = "scan.nessus") {
  fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File(["<x/>"], name)] } });
}

function calls(fetchMock: Awaited<ReturnType<typeof renderSignedIn>>["fetchMock"]) {
  return fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${String(url).replace(/^.*\/api\/v1/, "")}`);
}

describe("ImportButton", () => {
  it.each(["assets", "findings"] as const)("rejects oversized %s files at selection before content reads or POST", async kind => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind={kind} accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "GET /upload-limits": () => ({ import_max_bytes: 1024, document_max_bytes: 10 * 1024**2, logo_max_bytes: 2 * 1024**2 }),
    });
    const file = new File(["type,hostname\nserver,large"], "oversized.csv");
    Object.defineProperty(file, "size", { value: 1025 });
    const sniff = vi.spyOn(file, "slice");
    fireEvent.change(screen.getByTestId(`${kind}-file-input`), { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("oversized.csv exceeds the 1 KiB file limit");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sniff).not.toHaveBeenCalled();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  it("accepts a 251 MiB inventory against a configured 256 MiB ceiling without transferring file content", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".json" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin");
    const file = new File(['[{"type":"server","hostname":"test"}]'], "cloud_assets.json");
    Object.defineProperty(file, "size", { value: 251 * 1024**2 });
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [file] } });
    expect(await screen.findByRole("button", { name: "Upload all ready files (1)" })).toBeEnabled();
    expect(screen.getByText(/Asset\/finding import limit: 256 MiB/)).toBeVisible();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  it("keeps valid files ready when the same selection contains an oversized or unsupported file", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "GET /upload-limits": () => ({ import_max_bytes: 100, document_max_bytes: 10 * 1024**2, logo_max_bytes: 2 * 1024**2 }),
    });
    const large = new File(["type,hostname\nserver,large"], "large.csv");
    Object.defineProperty(large, "size", { value: 101 });
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [large, new File(["type,hostname\nserver,ok"], "ok.csv"), new File(["x"], "bad.exe")] } });
    expect(await screen.findByRole("button", { name: "Upload all ready files (1)" })).toBeEnabled();
    expect(screen.getByRole("alert")).toHaveTextContent("large.csv exceeds the 100 bytes file limit");
    expect(screen.getByRole("alert")).toHaveTextContent("bad.exe: Unsupported file type");
    expect(screen.getAllByRole("group", { name: "Upload options" })).toHaveLength(1);
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  it.each([0, -1, 1.5, null, Number.MAX_SAFE_INTEGER + 1])("does not guess a limit when metadata is invalid (%s)", async limit => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "GET /upload-limits": () => ({ import_max_bytes: limit }),
    });
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File(["type,hostname\nserver,a"], "a.csv")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload limit is unavailable");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  it("ignores a delayed file-limit response after the upload component is unmounted", async () => {
    let finish!: (value: Response) => void;
    const { fetchMock, unmount } = await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "GET /upload-limits": () => new Promise<Response>(resolve => { finish = resolve; }),
    });
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File(["type,hostname\nserver,a"], "a.csv")] } });
    await screen.findByText(/Checking file sizes/);
    unmount();
    await act(async () => { finish(json({ import_max_bytes: 256 * 1024**2 })); });
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  it("accepts multi-file drops outside the small upload button without navigation or duplicate delivery", async () => {
    await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin");
    fireEvent.drop(document.body, { dataTransfer: { files: [new File(["type,hostname\nserver,a"], "a.csv"), new File(["type,hostname\nserver,b"], "b.csv")] } });
    await screen.findByLabelText("Source for a.csv");
    await screen.findByLabelText("Source for b.csv");
    fireEvent.drop(screen.getByLabelText("File upload area"), { dataTransfer: { files: [new File(["type,hostname\nserver,c"], "c.csv")] } });
    await screen.findByLabelText("Source for c.csv");
    expect(screen.getAllByRole("group", { name: "Upload options" })).toHaveLength(3);
  });

  it("explains a skipped single upload without creating a tracker entry", async () => {
    const { fetchMock } = await renderButton({
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "existing", status: "running", report: null, skipped: true, skip_reason: "An identical import is already queued or running" }),
    });
    pickFile();
    expect(await screen.findByText(/Skipped scan.nessus: An identical import/)).toBeInTheDocument();
    expect(calls(fetchMock).some(call => call.includes("/scans/existing"))).toBe(false);
  });

  it("counts policy skips without tracking another uploader's existing scan", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "someone-elses-scan", status: "completed", report: null, skipped: true, skip_reason: "Exact duplicate skipped by organization policy" }),
    });
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [
      new File(["hostname,severity,description\none,high,first"], "one.csv"),
      new File(["hostname,severity,description\ntwo,high,second"], "two.csv"),
    ] } });
    fireEvent.click(await screen.findByRole("button", { name: "Upload all ready files (2)" }));
    await screen.findByText(/0 submitted; 0 failed; 0 already uploaded; 2 skipped/);
    expect(calls(fetchMock).some(call => call.includes("someone-elses-scan"))).toBe(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps queue options in a named cancellable dialog without submitting files", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin");
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File(["type,hostname\nserver,one"], "one.csv")] } });
    const dialog = await screen.findByRole("dialog", { name: "Upload files" });
    expect(within(dialog).getByRole("button", { name: "Cancel queued uploads" })).toHaveFocus();
    await within(dialog).findByRole("group", { name: "Upload options" });
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  function selectBatch() {
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [
      new File(["hostname,severity,description\none,high,first"], "one.csv"),
      new File(["hostname,severity,description\ntwo,high,second"], "two.csv"),
    ] } });
  }

  it.each(["assets", "findings"] as const)("cancels the %s queue in one click without a confirmation or submission", async kind => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind={kind} accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin");
    const trigger = screen.getByRole("button", { name: "Upload file" });
    trigger.focus();
    fireEvent.change(screen.getByTestId(`${kind}-file-input`), { target: { files: [
      new File(["type,hostname\nserver,one"], "one.csv"), new File(["type,hostname\nserver,two"], "two.csv"),
    ] } });
    await screen.findByLabelText("Source for two.csv");
    fireEvent.click(screen.getByRole("button", { name: "Cancel queued uploads" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(0);
  });

  it("locks all other row and bulk actions during an individual submission and retains accepted jobs when the queue closes", async () => {
    let finish: (value: Response) => void = () => {};
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK, "POST /orgs/org-1/findings/import": () => new Promise<Response>(resolve => { finish = resolve; }),
    });
    selectBatch();
    await screen.findByLabelText("Source for two.csv");
    const rows = screen.getAllByRole("group", { name: "Upload options" });
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Upload" }));
    await screen.findByText("Uploading…");
    expect(within(rows[1]).getByRole("button", { name: "Upload" })).toBeDisabled();
    expect(within(rows[1]).getByRole("button", { name: "Remove" })).toBeDisabled();
    expect(screen.getByLabelText("Source for two.csv")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel queued uploads" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Upload all ready files/ })).toBeDisabled();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(screen.getByRole("dialog", { name: "Upload files" })).toBeInTheDocument();
    finish(json({ scan_id: "s1", status: "pending", report: null }, 202));
    await waitFor(() => expect(screen.queryByLabelText("Source for one.csv")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel queued uploads" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toEqual(["POST /orgs/org-1/findings/import"]);
    expect(calls(fetchMock)).toContain("GET /orgs/org-1/scans/s1");
  });

  it("discards failed and duplicate queue entries without resubmitting them", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "POST /orgs/org-1/findings/import": init => ((init.body as FormData).get("file") as File).name === "one.csv"
        ? json({ detail: "Temporary failure" }, 503)
        : json({ detail: { imported_by: "Test member", imported_at: null } }, 409),
    });
    selectBatch();
    fireEvent.click(await screen.findByRole("button", { name: "Upload all ready files (2)" }));
    await screen.findByText(/0 submitted; 1 failed; 1 already uploaded/);
    const duplicate = await screen.findByLabelText("two.csv");
    fireEvent.click(duplicate);
    fireEvent.click(screen.getByRole("button", { name: "Cancel queued uploads" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("one.csv: Temporary failure")).not.toBeInTheDocument();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(2);
  });

  it("removes only the selected same-name row and uploads the remaining file once", async () => {
    let submitted: File | null = null;
    await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK, "POST /orgs/org-1/assets/import": init => {
        submitted = (init.body as FormData).get("file") as File;
        return json({ scan_id: "s1", status: "pending", report: null }, 202);
      },
    });
    const first = new File(["type,hostname\nserver,first"], "same.csv");
    const second = new File(["type,hostname\nserver,second"], "same.csv");
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [first, second] } });
    await screen.findByRole("button", { name: "Upload all ready files (2)" });
    const rows = screen.getAllByRole("group", { name: "Upload options" });
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Remove" }));
    expect(screen.getAllByRole("group", { name: "Upload options" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(submitted).toBe(second);
  });

  it("submits sequentially, locks sources, prevents double starts and stops unsent files", async () => {
    let finish: (value: Response) => void = () => {};
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK, "POST /orgs/org-1/findings/import": () => new Promise<Response>(resolve => { finish = resolve; }),
    });
    selectBatch();
    const start = await screen.findByRole("button", { name: "Upload all ready files (2)" });
    fireEvent.click(start); fireEvent.click(start);
    await waitFor(() => expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(1));
    expect(screen.getByLabelText("Source for two.csv")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Stop remaining uploads" }));
    finish(json({ scan_id: "s1", status: "pending", report: null }, 202));
    await screen.findByText(/Stopped. Remaining files/);
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Upload all ready files (1)" })).toBeEnabled();
  });

  it("continues after a failure and retries only failed files", async () => {
    let attempts = 0;
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK, "POST /orgs/org-1/findings/import": () => ++attempts === 1 ? json({ detail: "Rejected" }, 400) : json({ scan_id: "s1", status: "pending", report: null }, 202),
    });
    selectBatch();
    fireEvent.click(await screen.findByRole("button", { name: "Upload all ready files (2)" }));
    await screen.findByText(/1 submitted; 1 failed/);
    const retry = await screen.findByRole("button", { name: "Retry failed (1)" });
    await waitFor(() => expect(retry).toBeEnabled());
    fireEvent.click(retry);
    await screen.findByText(/1 submitted; 0 failed/);
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(3);
  });

  it("collects all duplicates without confirming them and skips only selected files", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      "POST /orgs/org-1/findings/import": () => json({ detail: { imported_by: "Test member", imported_at: null } }, 409),
    });
    selectBatch();
    fireEvent.click(await screen.findByRole("button", { name: "Upload all ready files (2)" }));
    await screen.findByText(/0 submitted; 0 failed; 2 already uploaded/);
    const group = await screen.findByRole("region", { name: "Already uploaded files" });
    expect(within(group).getByRole("button", { name: "Upload selected anyway (0)" })).toBeDisabled();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(2);
    fireEvent.click(within(group).getByLabelText("one.csv"));
    fireEvent.click(within(group).getByRole("button", { name: "Skip selected (1)" }));
    expect(within(group).queryByLabelText("one.csv")).not.toBeInTheDocument();
    expect(within(group).getByLabelText("two.csv")).toBeInTheDocument();
    expect(calls(fetchMock).filter(call => call.startsWith("POST"))).toHaveLength(2);
  });

  it("submits later ready files before one grouped explicit duplicate approval", async () => {
    const submitted: { name: string; confirmed: boolean }[] = [];
    await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK, "POST /orgs/org-1/findings/import": (init) => {
        const body = init.body as FormData;
        const name = (body.get("file") as File).name;
        const confirmed = body.get("confirm") === "true";
        submitted.push({ name, confirmed });
        return name === "one.csv" && !confirmed ? json({ detail: { imported_by: "Test member", imported_at: null } }, 409) : json({ scan_id: "s1", status: "pending", report: null }, 202);
      },
    });
    selectBatch();
    fireEvent.click(await screen.findByRole("button", { name: "Upload all ready files (2)" }));
    await screen.findByText(/1 submitted; 0 failed; 1 already uploaded/);
    expect(submitted).toEqual([{ name: "one.csv", confirmed: false }, { name: "two.csv", confirmed: false }]);
    const group = await screen.findByRole("region", { name: "Already uploaded files" });
    fireEvent.click(within(group).getByLabelText("Select all already uploaded files"));
    const confirm = within(group).getByRole("button", { name: "Upload selected anyway (1)" });
    fireEvent.click(confirm); fireEvent.click(confirm);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(submitted).toEqual([{ name: "one.csv", confirmed: false }, { name: "two.csv", confirmed: false }, { name: "one.csv", confirmed: true }]);
  });

  it("separates failures, duplicates and unreadable sources and retries only failures", async () => {
    const submitted: string[] = [];
    await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK, "POST /orgs/org-1/findings/import": init => {
        const name = ((init.body as FormData).get("file") as File).name;
        submitted.push(name);
        if (name === "duplicate.csv") return json({ detail: { imported_by: "Test member", imported_at: null } }, 409);
        if (name === "failed.csv" && submitted.filter(file => file === name).length === 1) return json({ detail: "Temporary failure" }, 503);
        return json({ scan_id: "s1", status: "pending", report: null }, 202);
      },
    });
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [
      ...["failed.csv", "duplicate.csv", "ready.csv"].map(name => new File(["hostname,severity,description\none,high,test"], name)),
      new File(["unrecognized\nunknown"], "blocked.csv"),
    ] } });
    fireEvent.click(await screen.findByRole("button", { name: "Upload all ready files (3)" }));
    await screen.findByText(/1 submitted; 1 failed; 1 already uploaded/);
    await screen.findByRole("heading", { name: "Submission failed (1)" });
    expect(screen.getByRole("heading", { name: "Source needs attention (1)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Already uploaded (1)" })).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Retry failed (1)" });
    await waitFor(() => expect(retry).toBeEnabled());
    fireEvent.click(retry);
    await screen.findByText(/1 submitted; 0 failed; 0 already uploaded/);
    expect(submitted).toEqual(["failed.csv", "duplicate.csv", "ready.csv", "failed.csv"]);
    expect(screen.getByRole("heading", { name: "Already uploaded (1)" })).toBeInTheDocument();
  });

  it("keeps each ready file's independently selected source", async () => {
    const { fetchMock } = await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin", {
      ...TRACK,
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
      "POST /orgs/org-1/assets/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
    });
    selectBatch();
    await screen.findByRole("button", { name: "Upload all ready files (2)" });
    fireEvent.change(screen.getByLabelText("Source for two.csv"), { target: { value: "generic_assets" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload all ready files (2)" }));
    await screen.findByText(/2 submitted; 0 failed/);
    expect(calls(fetchMock)).toContain("POST /orgs/org-1/findings/import");
    expect(calls(fetchMock)).toContain("POST /orgs/org-1/assets/import");
  });

  it("gives every selected file independent source confirmation and cancellation", async () => {
    await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin");
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [
      new File(["type,hostname\nserver,one"], "one.csv"), new File(["type,hostname\nserver,two"], "two.csv"),
    ] } });
    await screen.findByLabelText("Source for one.csv");
    await screen.findByLabelText("Source for two.csv");
    expect(screen.getAllByRole("group", { name: "Upload options" })).toHaveLength(2);
    const first = screen.getByLabelText("Source for one.csv").closest<HTMLElement>('[role="group"]')!;
    fireEvent.click(within(first).getByRole("button", { name: "Remove" }));
    expect(screen.queryByLabelText("Source for one.csv")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Source for two.csv")).toBeInTheDocument();
  });

  it("accepts dropped files and rejects batches over the limit", async () => {
    await renderSignedIn(<ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" profiles={BUILTIN_PROFILES} />, "admin");
    const area = screen.getByLabelText("File upload area");
    fireEvent.drop(area, { dataTransfer: { files: Array.from({ length: 21 }, (_, i) => new File(["x"], `${i}.csv`)) } });
    expect(screen.getByRole("alert")).toHaveTextContent("at most 20");
    fireEvent.drop(area, { dataTransfer: { files: [new File(["type,hostname\nserver,a"], "drop.csv")] } });
    await screen.findByLabelText("Source for drop.csv");
  });
  it("uploads the file and hands its import to the tracker", async () => {
    const { fetchMock } = await renderButton({
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
    });

    pickFile();

    await waitFor(() => expect(calls(fetchMock)).toContain("GET /orgs/org-1/scans/s1"));
    expect(calls(fetchMock)).toContain("POST /orgs/org-1/findings/import");
    await waitFor(() => expect(screen.getByRole("button", { name: "Upload findings" })).toBeEnabled());
  });

  it("shows why an upload was rejected (e.g. unsupported type)", async () => {
    await renderButton({
      "POST /orgs/org-1/findings/import": () => json({ detail: "Unsupported file type; expected .csv, .json, .nessus" }, 400),
    });

    pickFile("notes.txt");

    expect(await screen.findByRole("alert")).toHaveTextContent("notes.txt: Unsupported file type; expected .csv, .json, .nessus");
  });

  it("disables itself while uploading", async () => {
    let finish: (value: Response) => void = () => {};
    await renderButton({ "POST /orgs/org-1/findings/import": () => new Promise<Response>((resolve) => (finish = resolve)) });

    pickFile();

    expect(await screen.findByText("Uploading…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeDisabled();
    finish(json({ scan_id: "s1", status: "completed", report: null }, 201));
    await waitFor(() => expect(screen.getByRole("button", { name: "Upload findings" })).toBeEnabled());
  });
});

describe("ImportButton with import profiles", () => {
  function renderWithProfiles(routes: Parameters<typeof renderSignedIn>[2], kind: "assets" | "findings" = "assets") {
    return renderSignedIn(
      <ImportButton
        orgId="org-1"
        kind={kind}
        accept=".csv,.json,.nessus"
        label="Upload file"
        profiles={[...BUILTIN_PROFILES, CUSTOM_EDR_PROFILE]}
      />,
      "admin",
      { ...TRACK, ...routes },
    );
  }

  function pick(kind: string, content: string, name: string) {
    fireEvent.change(screen.getByTestId(`${kind}-file-input`), { target: { files: [new File([content], name)] } });
  }

  const uploaded = (fetchMock: Awaited<ReturnType<typeof renderSignedIn>>["fetchMock"]) =>
    fetchMock.mock.calls.findIndex(([, init]) => init?.method === "POST");

  it("detects the source from the file's columns and imports with that profile", async () => {
    const { fetchMock } = await renderWithProfiles({
      "POST /orgs/org-1/imports": () => json({ scan_id: "s1", status: "completed", report: null }, 201),
    });

    pick("assets", "EndPointID,DeviceName,LastHeartbeat,ThreatsDetected,ComplianceStatus\nEP-1,a,b,0,ok\n", "edr.csv");

    const options = await screen.findByRole("group", { name: "Upload options" });
    expect(within(options).getByLabelText("Source")).toHaveValue("endpoint_agent");
    expect(options).toHaveTextContent("edr.csv");
    expect(within(options).getByTitle("Detected from the file's columns")).toHaveTextContent("Detected");
    expect(uploaded(fetchMock)).toBe(-1);
    expect(screen.getByRole("button", { name: "Upload file" })).toBeDisabled();

    fireEvent.click(within(options).getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(calls(fetchMock)).toContain("GET /orgs/org-1/scans/s1"));
    const body = requestInit(fetchMock, uploaded(fetchMock)).body as FormData;
    expect(body.get("profile")).toBe("endpoint_agent");
    expect((body.get("file") as File).name).toBe("edr.csv");
    expect(screen.queryByRole("group", { name: "Upload options" })).not.toBeInTheDocument();
  });

  it("defaults to the page's generic source and lists the page's first", async () => {
    const { fetchMock } = await renderWithProfiles(
      { "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "completed", report: null }, 201) },
      "findings",
    );

    pick("findings", "hostname,notes\nweb-01,x\n", "f.csv");

    const source = await screen.findByLabelText("Source");
    expect(source).toHaveValue("generic_findings");
    expect(within(source).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Generic findings",
      "Generic asset list",
      "Endpoint agent export",
      "Network scan export",
      "Cloud inventory export",
      "Directory (Active Directory) export",
      "Our EDR (Endpoint agent export)",
    ]);
    expect(screen.queryByText(/Detected from/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(uploaded(fetchMock)).not.toBe(-1));
    expect((requestInit(fetchMock, uploaded(fetchMock)).body as FormData).get("profile")).toBeNull();
  });

  it("lets the user pick another source, including the org's own profile", async () => {
    const { fetchMock } = await renderWithProfiles({
      "POST /orgs/org-1/imports": () => json({ scan_id: "s1", status: "completed", report: null }, 201),
    });

    pick("assets", "Device_Name\nPC-1\n", "edr.csv");
    fireEvent.change(await screen.findByLabelText("Source"), { target: { value: CUSTOM_EDR_PROFILE.key } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(uploaded(fetchMock)).not.toBe(-1));
    expect((requestInit(fetchMock, uploaded(fetchMock)).body as FormData).get("profile")).toBe(CUSTOM_EDR_PROFILE.key);
  });

  it("won't import a file no source can read (here an activity log, its source not installed): Cancel is the way out", async () => {
    const { fetchMock } = await renderWithProfiles({});
    const activityLog = JSON.stringify([
      { operation_id: "AZ-1", time: "t", operation_name: "x", subscription_id: "s", resource_group: "r", resource_type: "v", status: "ok", caller: "u" },
    ]);

    pick("assets", activityLog, "azure_activity.json");

    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(
      "No supported source matches this file",
    );
    const importButton = screen.getByRole("button", { name: "Upload" });
    expect(importButton).toBeDisabled();
    // No other source helps either.
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "endpoint_agent" } });
    expect(importButton).toBeDisabled();
    fireEvent.click(importButton);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByRole("group", { name: "Upload options" })).not.toBeInTheDocument();
  });

  it("imports a minimal generic file, even though no source is detected from so few columns", async () => {
    await renderWithProfiles({});

    pick("assets", "type,hostname\nserver,web-01\n", "a.csv");

    expect(await screen.findByLabelText("Source")).toHaveValue("generic_assets");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
  });

  it("asks for another source when the one chosen can't read the file", async () => {
    await renderWithProfiles({});

    pick("assets", "type,hostname\nserver,web-01\n", "a.csv");
    fireEvent.change(await screen.findByLabelText("Source"), { target: { value: "cloud_inventory" } });

    expect(screen.getByRole("note")).toHaveTextContent("Cloud inventory export cannot read this file");
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "generic_assets" } });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
  });

  it("has no such note for a recognised file", async () => {
    await renderWithProfiles({});

    pick("assets", "EndPointID,DeviceName,LastHeartbeat,ThreatsDetected,ComplianceStatus\nEP-1,a,b,0,ok\n", "edr.csv");

    expect(await screen.findByTitle("Detected from the file's columns")).toHaveTextContent("Detected");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("only offers generic findings for a .nessus file", async () => {
    await renderWithProfiles({}, "findings");

    pick("findings", "<x/>", "scan.nessus");

    const source = await screen.findByLabelText("Source");
    expect(within(source).getAllByRole("option").map((o) => o.textContent)).toEqual(["Generic findings"]);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("can be cancelled without uploading", async () => {
    const { fetchMock } = await renderWithProfiles({});

    pick("assets", "type,hostname\nserver,a\n", "a.csv");
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

    expect(screen.queryByRole("group", { name: "Upload options" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload file" })).toBeEnabled();
    expect(uploaded(fetchMock)).toBe(-1);
  });

  it("clears a cancelled upload's error before another file is picked", async () => {
    await renderWithProfiles({
      "POST /orgs/org-1/assets/import": () => json({ detail: "Unsupported file type" }, 400),
    });

    pick("assets", "type,hostname\nserver,a\n", "first.csv");
    fireEvent.click(await screen.findByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("first.csv: Unsupported file type");

    fireEvent.click(screen.getByRole("button", { name: "Cancel queued uploads" }));
    pick("assets", "type,hostname\nserver,a\n", "second.csv");
    await screen.findByRole("group", { name: "Upload options" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("second.csv: Unsupported file type");
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uploads once even if Import is clicked twice quickly", async () => {
    let finish: (value: Response) => void = () => {};
    const { fetchMock } = await renderWithProfiles({
      "POST /orgs/org-1/assets/import": () => new Promise<Response>((resolve) => (finish = resolve)),
    });

    pick("assets", "type,hostname\nserver,a\n", "a.csv");
    const importButton = await screen.findByRole("button", { name: "Upload" });
    fireEvent.click(importButton);
    fireEvent.click(importButton);

    expect(await screen.findByText("Uploading…")).toBeInTheDocument();
    finish(json({ scan_id: "s1", status: "completed", report: null }, 201));
    await waitFor(() => expect(screen.getByRole("button", { name: "Upload file" })).toBeEnabled());
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toHaveLength(1);
  });
});
