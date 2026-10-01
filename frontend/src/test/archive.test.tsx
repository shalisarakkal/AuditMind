import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ArchivedPage from "@/app/(app)/archived/page";
import FindingsPage from "@/app/(app)/findings/page";
import UploadsPage from "@/app/(app)/uploads/page";
import ImportButton from "@/components/ImportButton";
import Sidebar from "@/components/Sidebar";
import { jobProgressText } from "@/context/ImportsContext";
import { countsText, purgeCountdown } from "@/lib/domain";
import type { ArchivedItem, ArchiveJob, FindingListItem, Upload } from "@/lib/types";
import { json, renderSignedIn, requestInit, scan } from "@/test/helpers";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  usePathname: () => "/uploads",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
  navigation.replace.mockClear();
});

type FetchMock = Awaited<ReturnType<typeof renderSignedIn>>["fetchMock"];

const page = <T,>(items: T[]) => ({ items, total: items.length });

function upload(overrides: Partial<Upload> = {}): Upload {
  return { ...scan({ filename: "findings.csv", scan_type: "findings_csv", summary: { created: 3 } }), uploaded_by: "Ann", ...overrides };
}

function job(overrides: Partial<ArchiveJob> = {}): ArchiveJob {
  return {
    id: "j1",
    org_id: "org-1",
    batch_id: "b1",
    action: "archive",
    status: "completed",
    item_type: "upload",
    item_id: "s1",
    label: "findings.csv",
    started_by: "user-1",
    started_at: "2026-09-28T10:00:00Z",
    completed_at: "2026-09-28T10:00:01Z",
    dismissed_at: null,
    progress: null,
    summary: { uploads: 1, assets: 2, findings: 1200 },
    ...overrides,
  };
}

function archived(overrides: Partial<ArchivedItem> = {}): ArchivedItem {
  return {
    id: "b1",
    item_type: "upload",
    item_id: "s1",
    label: "findings.csv",
    state: "archived",
    running: null,
    archived_at: "2026-09-28T10:00:00Z",
    archived_by: "Ann",
    purge_at: new Date(Date.now() + 172.5 * 24 * 3600 * 1000).toISOString(),
    counts: { uploads: 1, assets: 2, findings: 3 },
    ...overrides,
  };
}

/** The Archived list: the items, and how many of each type. */
function archivedPage(items: ArchivedItem[]) {
  const type_counts: Partial<Record<ArchivedItem["item_type"], number>> = {};
  for (const item of items) type_counts[item.item_type] = (type_counts[item.item_type] ?? 0) + 1;
  return { ...page(items), type_counts };
}

function gets(fetchMock: FetchMock, path: string): number {
  return fetchMock.mock.calls.filter(([url, init]) => (init?.method ?? "GET") === "GET" && String(url).includes(path)).length;
}

describe("Uploads page", () => {
  it("opens a past upload's full report under its row", async () => {
    await renderSignedIn(<UploadsPage />, "viewer", {
      "GET /orgs/org-1/uploads": () => page([upload()]),
      "GET /orgs/org-1/scans/s1": () =>
        scan({
          filename: "findings.csv",
          scan_type: "findings_csv",
          summary: {
            created: 3, updated: 0, skipped: 0, duplicates: 1, failed: 0, findings_created: 0, errors: [], warnings: [],
            duplicate_rows: [{ row: 4, item: "web-01: CVE-1", message: "Same as row 2 of this file" }],
          },
        }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Show report for findings.csv" }));
    const report = await screen.findByRole("region", { name: "Upload result" });
    expect(report).toHaveTextContent("Duplicates — 1");
    expect(report).toHaveTextContent("Same as row 2 of this file");
    fireEvent.click(screen.getByRole("button", { name: "Hide report for findings.csv" }));
    expect(screen.queryByRole("region", { name: "Upload result" })).not.toBeInTheDocument();
  });

  it("lists uploads and archives one after confirming, then reloads the list", async () => {
    const { fetchMock } = await renderSignedIn(<UploadsPage />, "auditor", {
      "GET /orgs/org-1/uploads": () => page([upload()]),
      "POST /orgs/org-1/scans/s1/archive": () => job(),
    });

    const row = (await screen.findByText("findings.csv")).closest("tr")!;
    expect(within(row).getByText("Findings (CSV)")).toBeInTheDocument();
    expect(within(row).getByText("Ann")).toBeInTheDocument();
    expect(within(row).getByText("3 findings created")).toBeInTheDocument();

    fireEvent.click(within(row).getByRole("button", { name: "Archive findings.csv" }));
    const confirm = screen.getByRole("group", { name: "Archive findings.csv" });
    expect(confirm).toHaveTextContent("the assets only it created");
    const before = gets(fetchMock, "/uploads?");
    fireEvent.click(within(confirm).getByRole("button", { name: "Archive" }));

    expect(await screen.findByText("Archived findings.csv: 1 upload, 2 assets, 1,200 findings.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Archive findings.csv" })).not.toBeInTheDocument();
    await waitFor(() => expect(gets(fetchMock, "/uploads?")).toBeGreaterThan(before));
  });

  it("shows Archiving… while an upload's archive runs, and Retry if it stopped", async () => {
    await renderSignedIn(<UploadsPage />, "admin", {
      "GET /orgs/org-1/uploads": () =>
        page([upload(), upload({ id: "s2", filename: "big.csv", archiving: "running" }), upload({ id: "s3", filename: "half.csv", archiving: "stopped" })]),
    });
    expect(await screen.findByRole("button", { name: "Archive findings.csv" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Archiving big.csv" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Retry archive half.csv" })).toBeEnabled();
  });

  it("undoes an archive that stopped part-way", async () => {
    let undone = false;
    await renderSignedIn(<UploadsPage />, "auditor", {
      "GET /orgs/org-1/uploads": () =>
        page([upload({ archiving: undone ? null : "stopped", archiving_batch_id: undone ? null : "b9" })]),
      "POST /orgs/org-1/archive/b9/restore": () => {
        undone = true;
        return job({ action: "restore", batch_id: "b9", summary: { findings: 40000 } });
      },
    });
    expect(await screen.findByRole("button", { name: "Retry archive findings.csv" })).toBeEnabled();
    const undo = screen.getByRole("button", { name: "Undo findings.csv" });
    expect(undo).toHaveAttribute("title", "Bring back what was archived before it stopped.");

    fireEvent.click(undo);
    const confirm = screen.getByRole("group", { name: "Undo archiving findings.csv" });
    expect(confirm).toHaveTextContent("stopped part-way. Bring back what it had archived");
    fireEvent.click(within(confirm).getByRole("button", { name: "Undo" }));

    expect(await screen.findByText("Restored findings.csv: 40,000 findings.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Archive findings.csv" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Undo findings.csv" })).not.toBeInTheDocument();
  });

  it("shows only Undoing… while Undo runs", async () => {
    await renderSignedIn(<UploadsPage />, "admin", {
      "GET /orgs/org-1/uploads": () => page([upload({ archiving: "stopped", archiving_batch_id: "b9" })]),
      "GET /orgs/org-1/archive-jobs?tracked=true": () => [
        job({ action: "restore", batch_id: "b9", status: "running", summary: null, completed_at: null }),
      ],
    });
    expect(await screen.findByRole("button", { name: "Undoing findings.csv" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Archiv/ })).not.toBeInTheDocument();
  });

  it("shows only Archiving… while Retry archive runs", async () => {
    let retried = false;
    const running = job({ status: "running", summary: null, completed_at: null });
    await renderSignedIn(<UploadsPage />, "admin", {
      // The list still says "stopped" until it reloads when the job finishes.
      "GET /orgs/org-1/uploads": () => page([upload({ archiving: "stopped", archiving_batch_id: "b1" })]),
      "POST /orgs/org-1/scans/s1/archive": () => {
        retried = true;
        return json(running, 202);
      },
      "GET /orgs/org-1/archive-jobs?tracked=true": () => (retried ? [running] : []),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Retry archive findings.csv" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Archive findings.csv" })).getByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("button", { name: "Archiving findings.csv" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Undo/ })).not.toBeInTheDocument();
  });

  it("can't archive an upload still importing", async () => {
    await renderSignedIn(<UploadsPage />, "admin", {
      "GET /orgs/org-1/uploads": () => page([upload({ status: "running" })]),
    });
    expect(await screen.findByRole("button", { name: "Archive findings.csv" })).toBeDisabled();
  });

  it("filters every column its own way, newest first by default", async () => {
    const { fetchMock } = await renderSignedIn(<UploadsPage />, "viewer", {
      "GET /orgs/org-1/uploads": () => page([upload()]),
      "GET /orgs/org-1/uploads/facets": () => ({ type: ["findings_csv", "network_scan_import"], status: ["completed", "failed"] }),
    });
    await screen.findByText("findings.csv");
    const uploaded = screen.getByRole("columnheader", { name: "Uploaded" });
    expect(uploaded).toHaveAttribute("aria-sort", "descending");

    fireEvent.change(screen.getByLabelText("Filter file"), { target: { value: "cloud" } });
    fireEvent.change(screen.getByLabelText("Filter uploaded by"), { target: { value: "ann" } });
    fireEvent.click(screen.getByLabelText("Filter type: All"));
    fireEvent.click(within(screen.getByRole("group", { name: "type values" })).getByLabelText("Network scan export"));
    fireEvent.click(screen.getByLabelText("Filter status: All"));
    fireEvent.click(within(screen.getByRole("group", { name: "status values" })).getByLabelText("Failed"));
    await waitFor(() => {
      const url = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("/uploads?")).at(-1)!;
      const query = new URLSearchParams(url.split("?")[1]);
      expect([query.get("filename"), query.get("uploaded_by"), query.get("type"), query.get("status")]).toEqual([
        "cloud", "ann", "network_scan_import", "failed",
      ]);
    });
    expect(screen.getByText("1 upload matches")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Uploaded from"), { target: { value: "2026-09-01" } });
    await waitFor(() => {
      const url = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("/uploads?")).at(-1)!;
      expect(new URLSearchParams(url.split("?")[1]).get("since")).toBe("2026-09-01");
    });
  });

  it("asks for the order an old link shows (a sort with no order)", async () => {
    navigation.search = "sort=filename";
    const { fetchMock } = await renderSignedIn(<UploadsPage />, "viewer", { "GET /orgs/org-1/uploads": () => page([upload()]) });
    await screen.findByText("findings.csv");
    expect(screen.getByRole("columnheader", { name: "File" })).toHaveAttribute("aria-sort", "ascending");
    const url = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("/uploads?")).at(-1)!;
    expect(new URLSearchParams(url.split("?")[1]).get("order")).toBe("asc");
  });

  it("has no Archive button for viewers", async () => {
    await renderSignedIn(<UploadsPage />, "viewer", { "GET /orgs/org-1/uploads": () => page([upload()]) });
    await screen.findByText("findings.csv");
    expect(screen.queryByRole("button", { name: /Archive/ })).not.toBeInTheDocument();
  });

  it("spans the empty list over the columns shown, for viewers too", async () => {
    await renderSignedIn(<UploadsPage />, "viewer", { "GET /orgs/org-1/uploads": () => page([]) });
    const empty = await screen.findByText("No uploads yet.");
    const columns = empty.closest("table")!.querySelectorAll("thead tr:first-child th").length;
    expect(empty).toHaveAttribute("colspan", String(columns));
  });

  it("retries a failed upload from its kept file, then follows the new one", async () => {
    const failed = upload({ status: "failed", summary: { error: "Cut off twice (the background worker stopped)" }, retryable: true });
    const { fetchMock } = await renderSignedIn(<UploadsPage />, "auditor", {
      "GET /orgs/org-1/uploads": () => page([failed]),
      "POST /orgs/org-1/scans/s1/retry": () => json({ scan_id: "s2", status: "pending", report: null }, 202),
      "GET /orgs/org-1/scans/s2": () => scan({ id: "s2", status: "pending", filename: "findings.csv", summary: null }),
    });
    const before = gets(fetchMock, "/uploads?");
    fireEvent.click(await screen.findByRole("button", { name: "Retry findings.csv" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/scans/s2"))).toBe(true));
    await waitFor(() => expect(gets(fetchMock, "/uploads?")).toBeGreaterThan(before));
    expect(requestInit(fetchMock, fetchMock.mock.calls.findIndex(([u]) => String(u).endsWith("/retry"))).method).toBe("POST");
  });

  it("offers Retry only where it can help, and says why it was refused", async () => {
    const rejected = upload({ id: "s3", filename: "bad.csv", status: "failed", summary: { failed: 2 }, retryable: false });
    const cutOff = upload({ status: "failed", summary: { error: "Cut off twice" }, retryable: true });
    await renderSignedIn(<UploadsPage />, "auditor", {
      "GET /orgs/org-1/uploads": () => page([cutOff, rejected]),
      "POST /orgs/org-1/scans/s1/retry": () => json({ detail: "Only the uploader or an admin can retry this" }, 403),
    });
    const badRow = (await screen.findByText("bad.csv")).closest("tr")!;
    expect(within(badRow).queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry findings.csv" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't retry findings.csv: Only the uploader or an admin");
  });

  it("has no Retry for viewers", async () => {
    await renderSignedIn(<UploadsPage />, "viewer", {
      "GET /orgs/org-1/uploads": () => page([upload({ status: "failed", summary: { error: "Cut off twice" }, retryable: true })]),
    });
    await screen.findByText("findings.csv");
    expect(screen.queryByRole("button", { name: /^Retry/ })).not.toBeInTheDocument();
  });

  it("shows why the server refused", async () => {
    await renderSignedIn(<UploadsPage />, "admin", {
      "GET /orgs/org-1/uploads": () => page([upload()]),
      "POST /orgs/org-1/scans/s1/archive": () => json({ detail: "This upload is already archived" }, 409),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Archive findings.csv" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Archive findings.csv" })).getByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This upload is already archived");
  });

  it("follows a large archive in the background, then reloads", async () => {
    let started = false;
    let status: ArchiveJob["status"] = "running";
    const current = () =>
      status === "running"
        ? job({ status, summary: null, completed_at: null, progress: { phase: "findings", rows_done: 20000, rows_total: 500000 } })
        : job();
    const { fetchMock } = await renderSignedIn(
      <>
        <Sidebar />
        <UploadsPage />
      </>,
      "admin",
      {
        "GET /orgs/org-1/uploads": () => page([upload()]),
        "POST /orgs/org-1/scans/s1/archive": () => {
          started = true;
          return json(current(), 202);
        },
        "GET /orgs/org-1/archive-jobs?tracked=true": () => (started ? [current()] : []),
      },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Archive findings.csv" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Archive findings.csv" })).getByRole("button", { name: "Archive" }));

    expect(await screen.findByText("Findings: 20,000 / 500,000 (4%)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archiving findings.csv" })).toBeDisabled();
    const sidebar = screen.getByRole("list", { name: "Archive jobs in progress" });
    expect(sidebar).toHaveTextContent("Archiving findings.csv…");
    const before = gets(fetchMock, "/uploads?");

    status = "completed";
    expect(await screen.findByText("Archived findings.csv: 1 upload, 2 assets, 1,200 findings.")).toBeInTheDocument();
    await waitFor(() => expect(gets(fetchMock, "/uploads?")).toBeGreaterThan(before));
    expect(screen.queryByRole("list", { name: "Archive jobs in progress" })).not.toBeInTheDocument();
  });
});

describe("Archived page", () => {
  it("shows each archived item with its countdown, and restores one", async () => {
    const item = archived();
    const { fetchMock } = await renderSignedIn(<ArchivedPage />, "auditor", {
      "GET /orgs/org-1/archive": () => archivedPage([item]),
      "POST /orgs/org-1/archive/b1/restore": () => job({ action: "restore", summary: { uploads: 1, assets: 2, findings: 2, duplicates_purged: 1 } }),
    });

    const row = (await screen.findByText("findings.csv")).closest("tr")!;
    expect(within(row).getByText("1 upload, 2 assets, 3 findings")).toBeInTheDocument();
    expect(within(row).getByText("Deleted in 173 days")).toBeInTheDocument();
    // And when, to the second, like the Archived column.
    const purgeAt = (await screen.findByText("Deleted in 173 days")).nextElementSibling!;
    expect(purgeAt.textContent).toBe(new Date(item.purge_at).toLocaleString());
    expect(within(row).getByText("Ann")).toBeInTheDocument();
    // Auditors restore; only admins purge.
    expect(within(row).queryByRole("button", { name: "Purge findings.csv" })).not.toBeInTheDocument();

    fireEvent.click(within(row).getByRole("button", { name: "Restore findings.csv" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Restore findings.csv" })).getByRole("button", { name: "Restore" }));
    expect(
      await screen.findByText(
        "Restored findings.csv: 1 upload, 2 assets, 2 findings. 1 finding already recorded again since was purged instead.",
      ),
    ).toBeInTheDocument();
    expect(requestInit(fetchMock, fetchMock.mock.calls.findIndex(([u]) => String(u).endsWith("/restore"))).method).toBe("POST");
  });

  it("opens an archived upload's report for every member, read-only", async () => {
    await renderSignedIn(<ArchivedPage />, "viewer", {
      "GET /orgs/org-1/archive": () =>
        archivedPage([archived(), archived({ id: "b2", item_type: "asset", item_id: "a1", label: "web-01", counts: { assets: 1 } })]),
      "GET /orgs/org-1/archive/b1/report": () =>
        scan({ status: "completed", filename: "findings.csv", scan_type: "findings_csv", summary: { created: 3, errors: [], warnings: [] } }),
    });
    const assetRow = (await screen.findByText("web-01")).closest("tr")!;
    expect(within(assetRow).queryByRole("button", { name: /report/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show report for findings.csv" }));
    const report = await screen.findByRole("region", { name: "Upload result" });
    expect(report).toHaveTextContent(/created\s*3/i);
    expect(within(report).queryByRole("button", { name: /Retry|Dismiss/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide report for findings.csv" }));
    expect(screen.queryByRole("region", { name: "Upload result" })).not.toBeInTheDocument();
  });

  it("says how many findings stayed archived with their asset", async () => {
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => archivedPage([archived()]),
      "POST /orgs/org-1/archive/b1/restore": () =>
        job({ action: "restore", summary: { uploads: 1, findings: 40, findings_kept_with_asset: 2 } }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Restore findings.csv" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Restore findings.csv" })).getByRole("button", { name: "Restore" }));
    expect(
      await screen.findByText(
        "Restored findings.csv: 1 upload, 40 findings. 2 findings stayed archived with their asset, archived separately: restore the asset to bring them back.",
      ),
    ).toBeInTheDocument();
  });

  it("purges for admins after a warning that it can't be undone", async () => {
    const { fetchMock } = await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => archivedPage([archived()]),
      "POST /orgs/org-1/archive/b1/purge": () => job({ action: "purge" }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Purge findings.csv" }));
    const confirm = screen.getByRole("group", { name: "Purge findings.csv" });
    expect(confirm).toHaveTextContent("This can't be undone.");
    fireEvent.click(within(confirm).getByRole("button", { name: "Purge for good" }));
    expect(await screen.findByText("Purged findings.csv: 1 upload, 2 assets, 1,200 findings.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/archive/b1/purge"))).toBe(true);
  });

  it("lists every type under All, with a chip per type; viewers only look", async () => {
    const { fetchMock } = await renderSignedIn(<ArchivedPage />, "viewer", {
      "GET /orgs/org-1/archive": () =>
        archivedPage([archived(), archived({ id: "b2", item_type: "asset", item_id: "a1", label: "web-01" })]),
    });
    const row = (await screen.findByText("web-01")).closest("tr")!;
    expect(within(row).getByText("Asset")).toBeInTheDocument();
    expect(within(screen.getByText("findings.csv").closest("tr")!).getByText("Upload")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Restore/ })).not.toBeInTheDocument();

    const chips = screen.getByRole("group", { name: "Type" });
    expect(within(chips).getByRole("button", { name: "All (2)" })).toHaveAttribute("aria-pressed", "true");
    // Only the types there are.
    expect(within(chips).queryByRole("button", { name: /Findings/ })).not.toBeInTheDocument();
    fireEvent.click(within(chips).getByRole("button", { name: "Assets (1)" }));
    await waitFor(() => {
      const url = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("/archive?")).at(-1)!;
      expect(new URLSearchParams(url.split("?")[1]).getAll("type")).toEqual(["asset"]);
    });
  });

  it("says what's archived when there's nothing", async () => {
    await renderSignedIn(<ArchivedPage />, "viewer", { "GET /orgs/org-1/archive": () => archivedPage([]) });
    expect(await screen.findByText("No archived items yet.")).toBeInTheDocument();
  });

  it("labels the buttons with the job running on an item", async () => {
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => archivedPage([archived({ state: "purging", running: "purge" })]),
    });
    expect(await screen.findByRole("button", { name: "Purging findings.csv" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Restor/ })).not.toBeInTheDocument();
  });

  it("offers Retry when a restore stopped part-way, and nothing else", async () => {
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => archivedPage([archived({ state: "restoring" })]),
    });
    const retry = await screen.findByRole("button", { name: "Retry restore findings.csv" });
    expect(retry).toBeEnabled();
    expect(retry).toHaveAttribute("title", "Stopped part-way. Click to finish from where it stopped.");
    expect(screen.queryByRole("button", { name: /Purge findings/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Being restored/)).not.toBeInTheDocument();
  });

  it("disables Purge while a restore it started is running", async () => {
    let started = false;
    const restoring = job({ action: "restore", status: "running", summary: null, completed_at: null });
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => archivedPage([archived()]),
      "POST /orgs/org-1/archive/b1/restore": () => {
        started = true;
        return json(restoring, 202);
      },
      "GET /orgs/org-1/archive-jobs?tracked=true": () => (started ? [restoring] : []),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Restore findings.csv" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Restore findings.csv" })).getByRole("button", { name: "Restore" }));
    expect(await screen.findByRole("button", { name: "Restoring findings.csv" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Purge findings.csv" })).toBeDisabled();
  });
});

describe("Archiving a manual finding", () => {
  it("offers Archive only on findings added by hand", async () => {
    const item = (id: string, scan_id: string | null): FindingListItem => ({
      id, org_id: "org-1", asset_id: null, scan_id, category: id, domain: "incident_response", severity: "low",
      description: null, source: null, created_at: "2026-09-27T10:00:00Z", asset_hostname: null, asset_ip: null,
      asset_cloud_id: null,
    });
    await renderSignedIn(<FindingsPage />, "admin", {
      "GET /orgs/org-1/findings": () => ({ ...page([item("manual", null), item("imported", "s1")]), domain_counts: {} }),
      "GET /orgs/org-1/import-profiles": () => [],
    });
    expect(await screen.findByRole("button", { name: "Archive manual" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive imported" })).not.toBeInTheDocument();
  });
});

describe("Uploading a file already uploaded", () => {
  it("asks first, then imports it anyway", async () => {
    let attempts = 0;
    const { fetchMock } = await renderSignedIn(
      <ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload findings" />,
      "admin",
      {
        "POST /orgs/org-1/findings/import": () =>
          ++attempts === 1
            ? json(
                {
                  detail: {
                    message: "This exact file was already uploaded on 28 Sep 2026 10:00 UTC by Ann.",
                    imported_at: "2026-09-28T10:00:00+00:00",
                    imported_by: "Ann",
                  },
                },
                409,
              )
            : json({ scan_id: "s1", status: "completed", report: null }, 201),
        "GET /orgs/org-1/scans/s1": () => scan(),
      },
    );
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File(["x"], "f.csv")] } });

    const ask = await screen.findByRole("group", { name: "Already uploaded" });
    expect(ask).toHaveTextContent("f.csv: this exact file was already uploaded on");
    expect(ask).toHaveTextContent("by Ann. Upload it again?");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeDisabled();

    fireEvent.click(within(ask).getByRole("button", { name: "Upload anyway" }));
    await waitFor(() => expect(attempts).toBe(2));
    const second = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/findings/import"))[1][1]!;
    expect((second.body as FormData).get("confirm")).toBe("true");
    await waitFor(() => expect(screen.queryByRole("group", { name: "Already uploaded" })).not.toBeInTheDocument());
  });

  it("drops the file on Cancel", async () => {
    await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload findings" />, "admin", {
      "POST /orgs/org-1/findings/import": () =>
        json({ detail: { message: "Already uploaded.", imported_at: null, imported_by: "Ann" } }, 409),
    });
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File(["x"], "f.csv")] } });
    const ask = await screen.findByRole("group", { name: "Already uploaded" });
    expect(ask).toHaveTextContent("f.csv: this exact file was already uploaded by Ann.");
    fireEvent.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("group", { name: "Already uploaded" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeEnabled();
  });
});

describe("helpers", () => {
  it("count what was archived together", () => {
    expect(countsText({ uploads: 1, assets: 0, findings: 1200 })).toBe("1 upload, 1,200 findings");
    expect(countsText({})).toBe("nothing");
  });

  it("count down to the purge", () => {
    const now = Date.parse("2026-09-28T10:00:00Z");
    expect(purgeCountdown("2027-03-27T10:00:00Z", now)).toBe("Deleted in 180 days");
    expect(purgeCountdown("2026-09-29T09:00:00Z", now)).toBe("Deleted tomorrow");
    expect(purgeCountdown("2026-09-27T09:00:00Z", now)).toBe("Deleted at the next daily purge");
  });
});

describe("Several at once", () => {
  const uploads = (from: number, count: number) =>
    Array.from({ length: count }, (_, i) => upload({ id: `s${from + i}`, filename: `f${from + i}.csv` }));

  it("keeps what's selected across pages, then queues a job for each", async () => {
    let second = false;
    let queued: ArchiveJob[] = [];
    const { fetchMock } = await renderSignedIn(<UploadsPage />, "auditor", {
      "GET /orgs/org-1/uploads": () => ({ items: second ? uploads(101, 2) : uploads(1, 100), total: 102 }),
      "POST /orgs/org-1/archive-jobs/bulk": () => {
        queued = ["s1", "s2", "s101"].map((id, i) =>
          job({ id: `j${i}`, item_id: id, label: `f${id.slice(1)}.csv`, status: i ? "pending" : "running", summary: null, completed_at: null }),
        );
        return json({ jobs: queued, refused: [{ id: "s102", detail: "This upload is already archived" }] }, 202);
      },
      "GET /orgs/org-1/archive-jobs?tracked=true": () => queued,
    });
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select f1.csv" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select f2.csv" }));
    expect(screen.getByRole("group", { name: "Selected" })).toHaveTextContent("2 selected");

    second = true;
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("f101.csv");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all on this page" }));
    expect(screen.getByRole("group", { name: "Selected" })).toHaveTextContent("4 selected");

    fireEvent.click(screen.getByRole("button", { name: "Archive selected" }));
    const confirm = screen.getByRole("group", { name: "Archive selected uploads" });
    expect(confirm).toHaveTextContent("Archive 4 uploads?");
    fireEvent.click(within(confirm).getByRole("button", { name: "Archive" }));

    // Each row says where its own job stands; the one that couldn't start says why.
    expect(await screen.findByRole("alert")).toHaveTextContent("f102.csv: This upload is already archived");
    expect(screen.getByRole("button", { name: "Queued f101.csv" })).toBeDisabled();
    expect(screen.queryByRole("group", { name: "Selected" })).not.toBeInTheDocument();
    const body = JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/bulk"))![1]!.body));
    expect(body).toEqual({ action: "archive", item_type: "upload", ids: ["s1", "s2", "s101", "s102"] });
  });

  it("starts over when the filters change", async () => {
    await renderSignedIn(<UploadsPage />, "auditor", { "GET /orgs/org-1/uploads": () => page(uploads(1, 3)) });
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select f1.csv" }));
    expect(screen.getByRole("group", { name: "Selected" })).toHaveTextContent("1 selected");
    fireEvent.change(screen.getByLabelText("Filter file"), { target: { value: "f2" } });
    await waitFor(() => expect(screen.queryByRole("group", { name: "Selected" })).not.toBeInTheDocument());
  });

  it("sums up many jobs: the one running, how many queued, then one result", async () => {
    let done = false;
    const many = () =>
      ["a", "b", "c", "d", "e"].map((id, i) =>
        done
          ? job({ id, label: id, action: "restore", status: i === 4 ? "failed" : "completed", summary: i === 4 ? { error: "gone" } : { assets: 1 } })
          : job({ id, label: id, action: "restore", status: i ? "pending" : "running", summary: null, completed_at: null }),
      );
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => archivedPage([]),
      "GET /orgs/org-1/archive-jobs?tracked=true": () => many(),
    });
    expect(await screen.findByRole("region", { name: "Restoring a" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Queued jobs" })).toHaveTextContent("4 more jobs queued");
    done = true;
    const results = await screen.findByRole("region", { name: "Job results" }, { timeout: 5000 });
    expect(results).toHaveTextContent("Restored 4 items; 1 stopped:");
    expect(results).toHaveTextContent("Restoring e stopped: gone");
  });

  it("has no checkboxes for viewers", async () => {
    await renderSignedIn(<ArchivedPage />, "viewer", { "GET /orgs/org-1/archive": () => archivedPage([archived()]) });
    await screen.findByText("findings.csv");
    expect(screen.queryByRole("checkbox", { name: /^Select/ })).not.toBeInTheDocument();
  });
});

describe("An archive job the worker was running when it stopped", () => {
  it("says it was interrupted and will carry on", () => {
    const running = job({ status: "running", heartbeat_at: "2026-09-30T21:08:13Z", progress: { phase: "findings", rows_done: 1, rows_total: 4 } });
    expect(jobProgressText(running, true)).toMatch(/^Interrupted: the background worker stopped\. This carries on where it left off/);
    expect(jobProgressText(running, false)).toBe("Findings: 1 / 4 (25%)");
    expect(jobProgressText({ ...running, heartbeat_at: null }, true)).toBe("Findings: 1 / 4 (25%)");
    expect(jobProgressText(job({ status: "pending" }), true)).toBe("Interrupted: the background worker stopped. This starts when it's back.");
    expect(jobProgressText(job({ status: "pending" }), false)).toBe("Waiting for the background worker…");
  });
});
