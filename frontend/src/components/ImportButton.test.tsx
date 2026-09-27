import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ImportButton from "@/components/ImportButton";
import { json, mockApi } from "@/test/helpers";

const REPORT = { created: 2, updated: 0, skipped: 0, duplicates: 0, failed: 1, errors: [{ row: 3, message: "bad" }] };

function renderButton(onComplete = vi.fn()) {
  render(
    <ImportButton orgId="org-1" kind="findings" accept=".csv,.nessus" label="Upload findings" onComplete={onComplete} pollIntervalMs={10} />,
  );
  return onComplete;
}

function pickFile(name = "scan.nessus") {
  fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File(["<x/>"], name)] } });
}

describe("ImportButton", () => {
  it("reports a small file's result straight away", async () => {
    const fetchMock = mockApi({
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "completed", report: REPORT }, 201),
    });
    const onComplete = renderButton();

    pickFile();

    await waitFor(() =>
      expect(onComplete).toHaveBeenCalledWith({ status: "completed", report: REPORT, filename: "scan.nessus" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("polls the scan for a large file until the background import finishes", async () => {
    const statuses = ["pending", "running", "completed"];
    const fetchMock = mockApi({
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
      "GET /orgs/org-1/scans/s1": () => {
        const status = statuses.shift();
        return { id: "s1", status, summary: status === "completed" ? REPORT : null };
      },
    });
    const onComplete = renderButton();

    pickFile();

    expect(await screen.findByText(/importing in the background/)).toBeInTheDocument();
    await waitFor(() =>
      expect(onComplete).toHaveBeenCalledWith({ status: "completed", report: REPORT, error: undefined, filename: "scan.nessus" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(4); // upload + 3 polls
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeEnabled();
  });

  it("surfaces a background import that crashed", async () => {
    mockApi({
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
      "GET /orgs/org-1/scans/s1": () => ({ id: "s1", status: "failed", summary: { error: "Unexpected error during import" } }),
    });
    const onComplete = renderButton();

    pickFile();

    await waitFor(() =>
      expect(onComplete).toHaveBeenCalledWith({
        status: "failed",
        report: null,
        error: "Unexpected error during import",
        filename: "scan.nessus",
      }),
    );
  });

  it("reports a rejected upload (e.g. unsupported type)", async () => {
    mockApi({
      "POST /orgs/org-1/findings/import": () => json({ detail: "Unsupported file type; expected .csv, .json, .nessus" }, 400),
    });
    const onComplete = renderButton();

    pickFile("notes.txt");

    await waitFor(() =>
      expect(onComplete).toHaveBeenCalledWith({
        status: "failed",
        report: null,
        error: "Unsupported file type; expected .csv, .json, .nessus",
        filename: "notes.txt",
      }),
    );
  });

  it("disables itself while uploading", async () => {
    let finish: (value: Response) => void = () => {};
    mockApi({ "POST /orgs/org-1/findings/import": () => new Promise<Response>((resolve) => (finish = resolve)) });
    renderButton();

    pickFile();

    expect(await screen.findByText("Uploading…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeDisabled();
    finish(json({ scan_id: "s1", status: "completed", report: REPORT }, 201));
    await waitFor(() => expect(screen.getByRole("button", { name: "Upload findings" })).toBeEnabled());
  });
});
