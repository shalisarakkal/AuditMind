import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ImportButton from "@/components/ImportButton";
import { json, mockApi, requestInit } from "@/test/helpers";
import { BUILTIN_PROFILES, CUSTOM_EDR_PROFILE } from "@/test/profiles";

const REPORT = {
  created: 2,
  updated: 0,
  skipped: 0,
  duplicates: 0,
  failed: 1,
  findings_created: 0,
  errors: [{ row: 3, message: "bad" }],
  warnings: [],
};

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

describe("ImportButton with import profiles", () => {
  function renderWithProfiles(kind: "assets" | "findings" = "assets", onComplete = vi.fn()) {
    render(
      <ImportButton
        orgId="org-1"
        kind={kind}
        accept=".csv,.json,.nessus"
        label="Import data"
        profiles={[...BUILTIN_PROFILES, CUSTOM_EDR_PROFILE]}
        onComplete={onComplete}
        pollIntervalMs={10}
      />,
    );
    return onComplete;
  }

  function pick(kind: string, content: string, name: string) {
    fireEvent.change(screen.getByTestId(`${kind}-file-input`), { target: { files: [new File([content], name)] } });
  }

  it("detects the source from the file's columns and imports with that profile", async () => {
    const fetchMock = mockApi({
      "POST /orgs/org-1/imports": () => json({ scan_id: "s1", status: "completed", report: REPORT }, 201),
    });
    const onComplete = renderWithProfiles();

    pick("assets", "EndPointID,DeviceName,LastHeartbeat,ThreatsDetected,ComplianceStatus\nEP-1,a,b,0,ok\n", "edr.csv");

    const options = await screen.findByRole("group", { name: "Import options" });
    expect(within(options).getByLabelText("Source")).toHaveValue("endpoint_agent");
    expect(options).toHaveTextContent("edr.csv");
    expect(options).toHaveTextContent("Detected from the file's columns");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Import data" })).toBeDisabled();

    fireEvent.click(within(options).getByRole("button", { name: "Import" }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith({ status: "completed", report: REPORT, filename: "edr.csv" }));
    const body = requestInit(fetchMock).body as FormData;
    expect(body.get("profile")).toBe("endpoint_agent");
    expect((body.get("file") as File).name).toBe("edr.csv");
    expect(screen.queryByRole("group", { name: "Import options" })).not.toBeInTheDocument();
  });

  it("defaults to the page's generic source and lists the page's first", async () => {
    const fetchMock = mockApi({
      "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "completed", report: REPORT }, 201),
    });
    renderWithProfiles("findings");

    pick("findings", "col_a,col_b\n1,2\n", "f.csv");

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

    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect((requestInit(fetchMock).body as FormData).get("profile")).toBeNull();
  });

  it("lets the user pick another source, including the org's own profile", async () => {
    const fetchMock = mockApi({
      "POST /orgs/org-1/imports": () => json({ scan_id: "s1", status: "completed", report: REPORT }, 201),
    });
    renderWithProfiles();

    pick("assets", "Device_Name\nPC-1\n", "edr.csv");
    fireEvent.change(await screen.findByLabelText("Source"), { target: { value: CUSTOM_EDR_PROFILE.key } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect((requestInit(fetchMock).body as FormData).get("profile")).toBe(CUSTOM_EDR_PROFILE.key);
  });

  it("only offers generic findings for a .nessus file", async () => {
    mockApi({});
    renderWithProfiles("findings");

    pick("findings", "<x/>", "scan.nessus");

    const source = await screen.findByLabelText("Source");
    expect(within(source).getAllByRole("option").map((o) => o.textContent)).toEqual(["Generic findings"]);
  });

  it("can be cancelled without uploading", async () => {
    const fetchMock = mockApi({});
    const onComplete = renderWithProfiles();

    pick("assets", "type,hostname\nserver,a\n", "a.csv");
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("group", { name: "Import options" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import data" })).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("uploads once even if Import is clicked twice quickly", async () => {
    let finish: (value: Response) => void = () => {};
    const fetchMock = mockApi({ "POST /orgs/org-1/assets/import": () => new Promise<Response>((resolve) => (finish = resolve)) });
    renderWithProfiles();

    pick("assets", "type,hostname\nserver,a\n", "a.csv");
    const importButton = await screen.findByRole("button", { name: "Import" });
    fireEvent.click(importButton);
    fireEvent.click(importButton);

    expect(await screen.findByText("Uploading…")).toBeInTheDocument();
    finish(json({ scan_id: "s1", status: "completed", report: REPORT }, 201));
    await waitFor(() => expect(screen.getByRole("button", { name: "Import data" })).toBeEnabled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
