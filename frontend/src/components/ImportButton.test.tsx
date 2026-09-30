import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
    expect(options).toHaveTextContent("Detected from the file's columns");
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

  it("won't import a file no source can read (e.g. an activity log): Cancel is the way out", async () => {
    const { fetchMock } = await renderWithProfiles({});
    const activityLog = JSON.stringify([
      { operation_id: "AZ-1", time: "t", operation_name: "x", subscription_id: "s", resource_group: "r", resource_type: "v", status: "ok", caller: "u" },
    ]);

    pick("assets", activityLog, "azure_activity.json");

    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(
      "No source can read this file: none of its columns (operation_id, time, operation_name, subscription_id, resource_group, resource_type, …) identifies a host",
    );
    const importButton = screen.getByRole("button", { name: "Upload" });
    expect(importButton).toBeDisabled();
    // No other source helps either.
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "endpoint_agent" } });
    expect(importButton).toBeDisabled();
    fireEvent.click(importButton);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
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

    expect(screen.getByRole("note")).toHaveTextContent("Cloud inventory export can't read this file");
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "generic_assets" } });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
  });

  it("has no such note for a recognised file", async () => {
    await renderWithProfiles({});

    pick("assets", "EndPointID,DeviceName,LastHeartbeat,ThreatsDetected,ComplianceStatus\nEP-1,a,b,0,ok\n", "edr.csv");

    expect(await screen.findByText("Detected from the file's columns")).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("group", { name: "Upload options" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload file" })).toBeEnabled();
    expect(uploaded(fetchMock)).toBe(-1);
  });

  it("clears the last upload's error when another file is picked, or on Cancel", async () => {
    await renderWithProfiles({
      "POST /orgs/org-1/assets/import": () => json({ detail: "Unsupported file type" }, 400),
    });

    pick("assets", "type,hostname\nserver,a\n", "first.csv");
    fireEvent.click(await screen.findByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("first.csv: Unsupported file type");

    pick("assets", "type,hostname\nserver,a\n", "second.csv");
    await screen.findByRole("group", { name: "Upload options" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("second.csv: Unsupported file type");
    pick("assets", "type,hostname\nserver,a\n", "third.csv");
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
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
