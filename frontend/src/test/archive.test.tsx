import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ArchivedPage from "@/app/(app)/archived/page";
import FindingsPage from "@/app/(app)/findings/page";
import ImportsPage from "@/app/(app)/imports/page";
import ImportButton from "@/components/ImportButton";
import PurgeLogPanel from "@/components/PurgeLogPanel";
import Sidebar from "@/components/Sidebar";
import { countsText, purgeCountdown } from "@/lib/domain";
import type { ArchivedItem, ArchiveJob, FindingListItem, Upload } from "@/lib/types";
import { json, renderSignedIn, requestInit, scan } from "@/test/helpers";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  usePathname: () => "/imports",
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

function gets(fetchMock: FetchMock, path: string): number {
  return fetchMock.mock.calls.filter(([url, init]) => (init?.method ?? "GET") === "GET" && String(url).includes(path)).length;
}

describe("Imports page", () => {
  it("lists uploads and archives one after confirming, then reloads the list", async () => {
    const { fetchMock } = await renderSignedIn(<ImportsPage />, "auditor", {
      "GET /orgs/org-1/uploads": () => page([upload()]),
      "POST /orgs/org-1/scans/s1/archive": () => job(),
    });

    const row = (await screen.findByText("findings.csv")).closest("tr")!;
    expect(within(row).getByText("Findings (CSV)")).toBeInTheDocument();
    expect(within(row).getByText("Ann")).toBeInTheDocument();
    expect(within(row).getByText("3 created")).toBeInTheDocument();

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
    await renderSignedIn(<ImportsPage />, "admin", {
      "GET /orgs/org-1/uploads": () =>
        page([upload(), upload({ id: "s2", filename: "big.csv", archiving: "running" }), upload({ id: "s3", filename: "half.csv", archiving: "stopped" })]),
    });
    expect(await screen.findByRole("button", { name: "Archive findings.csv" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Archiving big.csv" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Retry archive half.csv" })).toBeEnabled();
  });

  it("undoes an archive that stopped part-way", async () => {
    let undone = false;
    await renderSignedIn(<ImportsPage />, "auditor", {
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
    await renderSignedIn(<ImportsPage />, "admin", {
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
    await renderSignedIn(<ImportsPage />, "admin", {
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
    await renderSignedIn(<ImportsPage />, "admin", {
      "GET /orgs/org-1/uploads": () => page([upload({ status: "running" })]),
    });
    expect(await screen.findByRole("button", { name: "Archive findings.csv" })).toBeDisabled();
  });

  it("has no Archive button for viewers", async () => {
    await renderSignedIn(<ImportsPage />, "viewer", { "GET /orgs/org-1/uploads": () => page([upload()]) });
    await screen.findByText("findings.csv");
    expect(screen.queryByRole("button", { name: /Archive/ })).not.toBeInTheDocument();
  });

  it("spans the empty list over the columns shown, for viewers too", async () => {
    await renderSignedIn(<ImportsPage />, "viewer", { "GET /orgs/org-1/uploads": () => page([]) });
    const empty = await screen.findByText("No uploads yet.");
    const columns = empty.closest("table")!.querySelectorAll("thead tr:first-child th").length;
    expect(empty).toHaveAttribute("colspan", String(columns));
  });

  it("shows why the server refused", async () => {
    await renderSignedIn(<ImportsPage />, "admin", {
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
        <ImportsPage />
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
    const { fetchMock } = await renderSignedIn(<ArchivedPage />, "auditor", {
      "GET /orgs/org-1/archive": () => page([archived()]),
      "POST /orgs/org-1/archive/b1/restore": () => job({ action: "restore", summary: { uploads: 1, assets: 2, findings: 2, duplicates_purged: 1 } }),
    });

    const row = (await screen.findByText("findings.csv")).closest("tr")!;
    expect(within(row).getByText("1 upload, 2 assets, 3 findings")).toBeInTheDocument();
    expect(within(row).getByText("Deleted in 173 days")).toBeInTheDocument();
    expect(within(row).getByText("by Ann")).toBeInTheDocument();
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

  it("says how many findings stayed archived with their asset", async () => {
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => page([archived()]),
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
      "GET /orgs/org-1/archive": () => page([archived()]),
      "POST /orgs/org-1/archive/b1/purge": () => job({ action: "purge" }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Purge findings.csv" }));
    const confirm = screen.getByRole("group", { name: "Purge findings.csv" });
    expect(confirm).toHaveTextContent("This can't be undone.");
    fireEvent.click(within(confirm).getByRole("button", { name: "Purge for good" }));
    expect(await screen.findByText("Purged findings.csv: 1 upload, 2 assets, 1,200 findings.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/archive/b1/purge"))).toBe(true);
  });

  it("switches tabs by item type; viewers only look", async () => {
    const { fetchMock } = await renderSignedIn(<ArchivedPage />, "viewer", {
      "GET /orgs/org-1/archive": () => page([]),
    });
    expect(await screen.findByText("No archived uploads.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Assets" }));
    expect(await screen.findByText("No archived assets.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/archive?item_type=asset"))).toBe(true);
  });

  it("labels the buttons with the job running on an item", async () => {
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => page([archived({ state: "purging", running: "purge" })]),
    });
    expect(await screen.findByRole("button", { name: "Purging findings.csv" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Restor/ })).not.toBeInTheDocument();
  });

  it("offers Retry when a restore stopped part-way, and nothing else", async () => {
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => page([archived({ state: "restoring" })]),
    });
    const retry = await screen.findByRole("button", { name: "Retry restore findings.csv" });
    expect(retry).toBeEnabled();
    expect(retry).toHaveAttribute("title", "Stopped part-way. Click to finish from where it stopped.");
    expect(screen.queryByRole("button", { name: /Purge/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Being restored/)).not.toBeInTheDocument();
  });

  it("disables Purge while a restore it started is running", async () => {
    let started = false;
    const restoring = job({ action: "restore", status: "running", summary: null, completed_at: null });
    await renderSignedIn(<ArchivedPage />, "admin", {
      "GET /orgs/org-1/archive": () => page([archived()]),
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

describe("Importing a file already imported", () => {
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
                    message: "This exact file was already imported on 28 Sep 2026 10:00 UTC by Ann.",
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

    const ask = await screen.findByRole("group", { name: "Already imported" });
    expect(ask).toHaveTextContent("f.csv: this exact file was already imported on");
    expect(ask).toHaveTextContent("by Ann. Import it again?");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeDisabled();

    fireEvent.click(within(ask).getByRole("button", { name: "Import anyway" }));
    await waitFor(() => expect(attempts).toBe(2));
    const second = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/findings/import"))[1][1]!;
    expect((second.body as FormData).get("confirm")).toBe("true");
    await waitFor(() => expect(screen.queryByRole("group", { name: "Already imported" })).not.toBeInTheDocument());
  });

  it("drops the file on Cancel", async () => {
    await renderSignedIn(<ImportButton orgId="org-1" kind="findings" accept=".csv" label="Upload findings" />, "admin", {
      "POST /orgs/org-1/findings/import": () =>
        json({ detail: { message: "Already imported.", imported_at: null, imported_by: "Ann" } }, 409),
    });
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File(["x"], "f.csv")] } });
    const ask = await screen.findByRole("group", { name: "Already imported" });
    expect(ask).toHaveTextContent("f.csv: this exact file was already imported by Ann.");
    fireEvent.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("group", { name: "Already imported" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeEnabled();
  });
});

describe("Purge log", () => {
  it("lists what was purged, by whom and why", async () => {
    await renderSignedIn(<PurgeLogPanel orgId="org-1" />, "admin", {
      "GET /orgs/org-1/purge-log": () =>
        page([
          {
            id: "p1", item_type: "upload", label: "old.csv", archived_at: "2026-03-01T10:00:00Z",
            purged_at: "2026-09-28T02:00:00Z", purged_by: null, reason: "auto", counts: { uploads: 1, findings: 40 },
          },
        ]),
    });
    const row = (await screen.findByText("old.csv")).closest("tr")!;
    expect(within(row).getByText("by the daily auto-purge")).toBeInTheDocument();
    expect(within(row).getByText("1 upload, 40 findings")).toBeInTheDocument();
    expect(within(row).getByText("Retention period over")).toBeInTheDocument();
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
