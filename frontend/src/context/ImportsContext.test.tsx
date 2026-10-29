import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ImportButton from "@/components/ImportButton";
import ImportStatus from "@/components/ImportStatus";
import Sidebar from "@/components/Sidebar";
import { importPages, importState, progressText } from "@/context/ImportsContext";
import type { Scan } from "@/lib/types";
import { useReloadOnImport } from "@/lib/useReloadOnImport";
import { json, renderSignedIn, scan } from "@/test/helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/" }));

const REPORT = {
  created: 3, updated: 0, skipped: 0, duplicates: 0, failed: 0, findings_created: 0, errors: [], warnings: [],
};

function ListReloads({ onReload }: { onReload: () => void }) {
  useReloadOnImport(onReload);
  return null;
}

/** Routes for a server whose imports are `list()`: ?tracked=true returns
 * them all, ?active=true the running ones. */
function server(list: () => Scan[]) {
  return {
    "GET /orgs/org-1/scans?tracked=true": () => list(),
    "GET /orgs/org-1/scans?active=true": () => list().filter((s) => s.status === "running" || s.status === "pending"),
  };
}

function requests(fetchMock: Awaited<ReturnType<typeof renderSignedIn>>["fetchMock"], suffix: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix)).length;
}

beforeEach(() => window.sessionStorage.clear());

describe("Import tracking", () => {
  it("labels finished imports as completed reports", async () => {
    await renderSignedIn(<ImportStatus page="assets" />, "admin", server(() => [scan({ id: "done-a" }), scan({ id: "done-b" })]));
    expect(await screen.findByText("2 imports completed")).toBeVisible();
    expect(screen.getByText("Show reports")).toBeVisible();
  });

  it("distinguishes one actively writing file from two queued files, including their icons", async () => {
    const now = new Date().toISOString();
    await renderSignedIn(<ImportStatus page="assets" />, "admin", server(() => [
      scan({ id: "active", filename: "active.csv", status: "running", heartbeat_at: now, progress: { phase: "writing", rows_done: 378000, rows_total: 500000, updated_at: now } }),
      scan({ id: "queued-a", filename: "queued-a.csv", status: "pending" }),
      scan({ id: "queued-b", filename: "queued-b.csv", status: "pending" }),
    ]));
    const summary = await screen.findByText("1 processing · 2 queued");
    fireEvent.click(summary.closest("summary")!);
    const active = screen.getByRole("region", { name: "Processing active.csv" });
    expect(active).toHaveTextContent("Writing rows: 378,000 / 500,000 (75%)");
    expect(active.querySelector('[class*="animate-spin"]')).not.toBeNull();
    const queued = screen.getByRole("region", { name: "Queued queued-a.csv" });
    expect(queued).toHaveTextContent("Queued — waiting for an available worker.");
    expect(queued.querySelector('[class*="animate-spin"]')).toBeNull();
  });

  it("shows time since real progress and a recent worker heartbeat without inventing row progress", async () => {
    const now = Date.now();
    await renderSignedIn(<ImportStatus page="assets" />, "admin", server(() => [scan({
      id: "slow", filename: "slow.csv", status: "running", heartbeat_at: new Date(now).toISOString(),
      progress: { phase: "writing", rows_done: 100, rows_total: 500, updated_at: new Date(now - 15000).toISOString() },
    })]));
    fireEvent.click((await screen.findByText("1 processing")).closest("summary")!);
    expect(screen.getByRole("region", { name: "Processing slow.csv" })).toHaveTextContent("100 / 500 (20%)");
    expect(screen.getByText(/Progress updated 15s ago/)).toBeVisible();
    expect(screen.getByText(/The worker is still checking in/)).toBeVisible();
  });

  it("counts successful completions separately from failures and queued imports", async () => {
    await renderSignedIn(<ImportStatus page="assets" />, "admin", server(() => [
      scan({ id: "done" }), scan({ id: "bad", status: "failed" }), scan({ id: "queue", status: "pending" }),
    ]));
    expect(await screen.findByText("1 queued · 1 failed · 1 completed")).toBeVisible();
  });

  it("groups running imports in a compact collapsed progress disclosure", async () => {
    await renderSignedIn(<ImportStatus page="assets" />, "admin", server(() => [scan({ id: "one", status: "running" }), scan({ id: "two", status: "pending" })]));
    const summary = await screen.findByText("1 processing · 1 queued");
    const details = summary.closest("details")!;
    expect(details.open).toBe(false);
    fireEvent.click(summary.closest("summary")!);
    expect(details.open).toBe(true);
  });

  it("opens the progress disclosure automatically when an import fails", async () => {
    await renderSignedIn(<ImportStatus page="assets" />, "admin", server(() => [scan({ id: "one", status: "failed" })]));
    const summary = await screen.findByText("Attention required");
    expect(summary.closest("details")!.open).toBe(true);
  });

  it("picks up a running import after a refresh, follows it, then shows its report", async () => {
    const states = [
      scan({ id: "big", filename: "big.csv", status: "running", progress: { phase: "reading" } }),
      scan({ id: "big", filename: "big.csv", status: "running", progress: { phase: "writing", rows_done: 120000, rows_total: 500000 } }),
      scan({ id: "big", filename: "big.csv", status: "completed", summary: REPORT }),
    ];
    let step = 0; // the test moves the import along
    const reload = vi.fn();
    await renderSignedIn(
      <>
        <ImportStatus page="assets" />
        <ListReloads onReload={reload} />
      </>,
      "admin",
      server(() => [states[step]]),
    );

    const running = await screen.findByRole("region", { name: "Processing big.csv" });
    expect(running).toHaveTextContent("Reading file…");
    step = 1;
    expect(await screen.findByText("Writing rows: 120,000 / 500,000 (24%)")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
    step = 2;

    const report = await screen.findByRole("region", { name: "Upload result" });
    expect(report).toHaveTextContent("big.csv");
    expect(report).toHaveTextContent("Assets created 3");
    expect(screen.queryByRole("region", { name: "Processing big.csv" })).not.toBeInTheDocument();
    // Report rendering may precede the passive effect that refreshes the list.
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  });

  it("polls only the light list while nothing starts or finishes", async () => {
    const { fetchMock } = await renderSignedIn(
      <ImportStatus page="assets" />,
      "admin",
      server(() => [scan({ id: "big", status: "running" })]),
    );
    await screen.findByText("Reading file…");

    await waitFor(() => expect(requests(fetchMock, "/scans?active=true")).toBeGreaterThanOrEqual(3));
    expect(requests(fetchMock, "/scans?tracked=true")).toBe(1); // the first load only
  });

  it("waits for each poll to answer before sending the next", async () => {
    let release: () => void = () => {};
    const running = scan({ id: "big", status: "running" });
    const { fetchMock } = await renderSignedIn(<ImportStatus page="assets" />, "admin", {
      "GET /orgs/org-1/scans?tracked=true": () => [running],
      "GET /orgs/org-1/scans?active=true": () => new Promise((resolve) => (release = () => resolve(json([running])))),
    });
    await waitFor(() => expect(requests(fetchMock, "/scans?active=true")).toBe(1));

    await new Promise((resolve) => setTimeout(resolve, 100)); // ten poll intervals
    expect(requests(fetchMock, "/scans?active=true")).toBe(1);

    await act(async () => release());
    await waitFor(() => expect(requests(fetchMock, "/scans?active=true")).toBe(2));
  });

  it("ignores an older response that arrives after a newer one", async () => {
    // The upload's own fetch is slow; meanwhile polling sees the import
    // finish. The late, older answer ("running") must not win.
    let releaseTrack: (() => void) | null = null;
    let finished = false;
    const running = scan({ id: "s1", filename: "big.csv", status: "running" });
    const done = scan({ id: "s1", filename: "big.csv", summary: REPORT });
    const reload = vi.fn();
    await renderSignedIn(
      <>
        <ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" />
        <ImportStatus page="assets" />
        <ListReloads onReload={reload} />
      </>,
      "admin",
      {
        ...server(() => (finished ? [done] : [])),
        "POST /orgs/org-1/assets/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
        "GET /orgs/org-1/scans/s1": () => new Promise((resolve) => (releaseTrack = () => resolve(json(running)))),
      },
    );

    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File(["x"], "big.csv")] } });
    await waitFor(() => expect(releaseTrack).not.toBeNull());
    finished = true;
    await screen.findByRole("region", { name: "Upload result" });
    await act(async () => releaseTrack!());

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText("Reading file…")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Upload result" })).toBeInTheDocument();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("follows an upload whose status couldn't be fetched, via polling", async () => {
    let fetched = 0;
    await renderSignedIn(
      <>
        <ImportButton orgId="org-1" kind="assets" accept=".csv" label="Upload file" />
        <ImportStatus page="assets" />
      </>,
      "admin",
      {
        ...server(() => (fetched++ ? [scan({ id: "s1", filename: "big.csv", summary: REPORT })] : [])),
        "POST /orgs/org-1/assets/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
        "GET /orgs/org-1/scans/s1": () => json({ detail: "Service unavailable" }, 503),
      },
    );

    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File(["x"], "big.csv")] } });

    expect(await screen.findByRole("region", { name: "Upload result" })).toHaveTextContent("big.csv");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("dismisses a report for good", async () => {
    const { fetchMock } = await renderSignedIn(<ImportStatus page="assets" />, "admin", {
      ...server(() => [scan({ summary: REPORT })]),
      "POST /orgs/org-1/scans/s1/dismiss": () => scan({ summary: REPORT, dismissed_at: "2026-09-28T10:00:00Z" }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(screen.queryByRole("region", { name: "Upload result" })).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/scans/s1/dismiss") && init?.method === "POST")).toBe(true);
  });

  it("doesn't bring a dismissed report back from a poll answered before the dismissal", async () => {
    // Another import is running, so polling continues; the list still
    // carries the report until the server has seen the dismissal.
    const report = scan({ summary: REPORT });
    const running = scan({ id: "other", filename: "other.csv", status: "running" });
    let started = 0;
    await renderSignedIn(<ImportStatus page="assets" />, "admin", {
      "GET /orgs/org-1/scans?tracked=true": () => [report, running],
      "GET /orgs/org-1/scans?active=true": () => [scan({ ...running, id: `new-${started++}` })], // changes each time
      "POST /orgs/org-1/scans/s1/dismiss": () => ({ ...report, dismissed_at: "2026-09-28T10:00:00Z" }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Upload result" })).not.toBeInTheDocument());
    await waitFor(() => expect(started).toBeGreaterThanOrEqual(3));
    expect(screen.queryByRole("region", { name: "Upload result" })).not.toBeInTheDocument();
  });

  it("drops the report of an upload archived or purged since, without an error", async () => {
    await renderSignedIn(<ImportStatus page="assets" />, "admin", {
      ...server(() => [scan({ summary: REPORT })]),
      "POST /orgs/org-1/scans/s1/dismiss": () => json({ detail: "Scan not found" }, 404),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(screen.queryByRole("region", { name: "Upload result" })).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the report if dismissing fails", async () => {
    await renderSignedIn(<ImportStatus page="assets" />, "admin", {
      ...server(() => [scan({ summary: REPORT })]),
      "POST /orgs/org-1/scans/s1/dismiss": () => json({ detail: "Only the uploader can dismiss this report" }, 403),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Only the uploader can dismiss this report");
    expect(screen.getByRole("region", { name: "Upload result" })).toBeInTheDocument();
  });

  it("shows an import only on the pages it affects", async () => {
    await renderSignedIn(
      <ImportStatus page="findings" />,
      "admin",
      server(() => [
        scan({ id: "a", filename: "assets.csv", scan_type: "asset_import", summary: REPORT }),
        scan({ id: "n", filename: "weekly.nessus", scan_type: "nessus", summary: REPORT }),
      ]),
    );

    expect(await screen.findByText("weekly.nessus")).toBeInTheDocument();
    expect(screen.queryByText("assets.csv")).not.toBeInTheDocument();
  });

  it("lists running imports in the sidebar on every page", async () => {
    await renderSignedIn(
      <Sidebar />,
      "viewer",
      server(() => [
        scan({ id: "r", filename: "endpoint_agents500K.csv", scan_type: "endpoint_agent_import", status: "running" }),
        scan({ id: "d", filename: "done.csv", summary: REPORT }),
      ]),
    );

    const list = await screen.findByRole("list", { name: "Uploads in progress" });
    const link = within(list).getByRole("link");
    expect(link).toHaveTextContent("Processing endpoint_agents500K.csv…");
    expect(link).toHaveAttribute("href", "/assets");
    expect(list).not.toHaveTextContent("done.csv");
  });

  it("shows a static queued sidebar link rather than processing", async () => {
    await renderSignedIn(<Sidebar />, "viewer", server(() => [scan({ id: "q", filename: "queued.csv", status: "pending" })]));
    const list = await screen.findByRole("list", { name: "Uploads in progress" });
    expect(within(list).getByRole("link")).toHaveTextContent("Queued queued.csv…");
    expect(list.querySelector('[class*="animate-pulse"]')).toBeNull();
  });

  it("links a tool export's import back to the page it was started from", async () => {
    const running = scan({ id: "s1", filename: "scan.csv", scan_type: "network_scan_import", status: "running" });
    await renderSignedIn(
      <>
        <Sidebar />
        <ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload file" />
      </>,
      "admin",
      {
        ...server(() => [running]),
        "POST /orgs/org-1/findings/import": () => json({ scan_id: "s1", status: "pending", report: null }, 202),
        "GET /orgs/org-1/scans/s1": () => running,
      },
    );

    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File(["x"], "scan.csv")] } });

    await waitFor(() =>
      expect(within(screen.getByRole("list", { name: "Uploads in progress" })).getByRole("link")).toHaveAttribute("href", "/findings"),
    );
  });
});

describe("import helpers", () => {
  it("classifies organization-lock waits and unavailable-worker jobs without counting them as processing", () => {
    expect(importState(scan({ status: "running", progress: { phase: "waiting" } }))).toBe("waiting");
    expect(importState(scan({ status: "pending" }), true)).toBe("interrupted");
    expect(importState(scan({ status: "running", heartbeat_at: "2026-10-29T12:00:00Z" }), true)).toBe("interrupted");
    expect(importState(scan())).toBe("completed");
  });
  it("describes progress", () => {
    expect(progressText(scan({ status: "pending" }))).toBe("Queued — waiting for an available worker.");
    // The worker was running it and stopped; one run during its request isn't the worker's.
    const byWorker = scan({ status: "running", heartbeat_at: "2026-09-30T21:08:13Z", progress: { phase: "writing", rows_done: 1, rows_total: 2 } });
    expect(progressText(byWorker, true)).toBe(
      "Interrupted: the background worker stopped. This upload carries on from where it got to when it's back.",
    );
    expect(progressText(byWorker, false)).toBe("Writing rows: 1 / 2 (50%)");
    expect(progressText({ ...byWorker, heartbeat_at: null }, true)).toBe("Writing rows: 1 / 2 (50%)");
    expect(progressText(scan({ status: "pending" }), true)).toBe(
      "Interrupted: the background worker stopped. This upload starts when it's back.",
    );
    expect(progressText(scan({ status: "running", progress: null }))).toBe("Reading file…");
    expect(progressText(scan({ status: "running", progress: { phase: "writing", rows_done: 120000, rows_total: 500000 } }))).toBe(
      "Writing rows: 120,000 / 500,000 (24%)",
    );
    expect(progressText(scan({ status: "running", progress: { phase: "reading", rows_done: 250000, rows_total: 500000 } }))).toBe(
      "Reading file: 250,000 / 500,000 rows (50%)",
    );
    expect(progressText(scan({ status: "running", progress: { phase: "waiting", rows_done: 0, rows_total: 0 } }))).toBe(
      "Waiting for another upload into this organization to finish processing…",
    );
    expect(progressText(scan({ status: "running", progress: { phase: "findings", rows_done: 120000, rows_total: 426700 } }))).toBe(
      "Writing findings: 120,000 / 426,700 (28%)",
    );
    expect(progressText(scan({ status: "running", progress: { phase: "saving", rows_done: 0, rows_total: 0 } }))).toBe("Saving changes…");
    expect(progressText(scan({ status: "running", progress: { phase: "preparing" } }))).toBe("Preparing inventory matches…");
  });

  it("maps imports to the pages they affect", () => {
    expect(importPages(scan({ scan_type: "asset_import" }))).toEqual(["assets"]);
    expect(importPages(scan({ scan_type: "findings_csv" }))).toEqual(["findings"]);
    expect(importPages(scan({ scan_type: "nessus" }))).toEqual(["findings"]);
    expect(importPages(scan({ scan_type: "network_scan_import" }))).toEqual(["assets", "findings"]);
  });
});
