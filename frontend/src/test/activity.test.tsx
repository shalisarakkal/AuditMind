import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivityPage from "@/app/(app)/activity/page";
import DashboardPage from "@/app/(app)/page";
import Sidebar from "@/components/Sidebar";
import { useApp } from "@/context/AppContext";
import { eventLabel, eventSummary, timing } from "@/lib/activity";
import type { ActivityEvent, DashboardSummary } from "@/lib/types";
import { renderSignedIn, scan } from "@/test/helpers";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => "/activity",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
});

type FetchMock = Awaited<ReturnType<typeof renderSignedIn>>["fetchMock"];

function event(overrides: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    id: "e1",
    type: "import",
    item: "endpoint_agents.csv",
    actor_id: "user-1",
    actor_label: "Ann",
    started_at: "2026-09-29T15:44:02Z",
    ended_at: "2026-09-29T15:55:43Z",
    outcome: "completed",
    criticality: "info",
    counts: { created: 500000, findings_created: 1229150 },
    details: null,
    ...overrides,
  };
}

const page = (items: ActivityEvent[]) => ({ items, total: items.length });

function lastEventsQuery(fetchMock: FetchMock) {
  const urls = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => /\/events\?/.test(u));
  return new URLSearchParams(urls.at(-1)?.split("?")[1]);
}

describe("Activity page", () => {
  it("labels and links known finding references without treating other item IDs as findings", async () => {
    await renderSignedIn(<ActivityPage />, "viewer", {
      "GET /orgs/org-1/events": () => ({ items: [event({ type: "finding_workflow_changed", item: "f1", details: { finding_id: "f1" } }), event({ id: "e2", type: "import", item: "upload-id" })], total: 2 }),
    });
    expect(await screen.findByRole("link", { name: "Find finding f1" })).toHaveAttribute("href", "/findings/lookup?org=org-1&finding_id=f1");
    expect(screen.queryByRole("link", { name: "Find finding upload-id" })).not.toBeInTheDocument();
  });
  it("lists what happened, with who, how long it waited and took, and its criticality", async () => {
    await renderSignedIn(<ActivityPage />, "viewer", {
      "GET /orgs/org-1/events": () =>
        page([
          event({ details: { waited_seconds: 902 } }),
          event({ id: "e2", type: "purge", item: "old.csv", actor_id: null, actor_label: "System", criticality: "critical",
            counts: { uploads: 1, findings: 40 }, started_at: "2026-09-29T02:00:00Z", ended_at: "2026-09-29T02:00:00Z" }),
          event({ id: "e3", type: "login_failed", item: "ann@acme.io", actor_id: null, actor_label: "Unknown",
            criticality: "warning", counts: null }),
        ]),
    });

    const row = (await screen.findByText("endpoint_agents.csv")).closest("tr")!;
    expect(within(row).getByText("Upload")).toBeInTheDocument();
    expect(within(row).getByText("500,000 created, 1,229,150 findings created")).toBeInTheDocument();
    expect(within(row).getByText("waited 15 min 2 s, took 11 min 41 s")).toBeInTheDocument();
    expect(within(row).getByText("Ann")).toBeInTheDocument();
    expect(within(row).getByText("completed")).toBeInTheDocument();
    const purge = screen.getByText("old.csv").closest("tr")!;
    expect(within(purge).getByText("System")).toBeInTheDocument();
    expect(within(purge).getByText("critical")).toBeInTheDocument();
    expect(within(purge).queryByText(/took/)).not.toBeInTheDocument();
    expect(within(screen.getByText("ann@acme.io").closest("tr")!).getByText("Failed sign-in")).toBeInTheDocument();
    expect(screen.getByText("3 events in Acme Corp")).toBeInTheDocument();
  });

  it("filters every column its own way, and sorts", async () => {
    const { fetchMock } = await renderSignedIn(<ActivityPage />, "admin", {
      "GET /orgs/org-1/events": () => page([]),
      "GET /orgs/org-1/events/facets": () => ({ type: ["import", "purge"], result: ["completed", "failed"] }),
    });
    await screen.findByText("No events yet.");

    fireEvent.click(await screen.findByLabelText("Filter event: All"));
    fireEvent.click(within(screen.getByRole("group", { name: "event values" })).getByLabelText("Purge"));
    await waitFor(() => expect(lastEventsQuery(fetchMock).getAll("type")).toEqual(["purge"]));

    fireEvent.change(screen.getByLabelText("Filter who"), { target: { value: "system" } });
    await waitFor(() => expect(lastEventsQuery(fetchMock).get("who")).toBe("system"));
    fireEvent.change(screen.getByLabelText("Filter item"), { target: { value: ".csv" } });
    await waitFor(() => expect(lastEventsQuery(fetchMock).get("item")).toBe(".csv"));

    fireEvent.click(screen.getByLabelText("Filter result: All"));
    fireEvent.click(within(screen.getByRole("group", { name: "result values" })).getByLabelText("Failed"));
    fireEvent.click(screen.getByLabelText("Filter criticality: All"));
    fireEvent.click(within(screen.getByRole("group", { name: "criticality values" })).getByLabelText("Critical"));
    fireEvent.change(screen.getByLabelText("When from"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByLabelText("When to"), { target: { value: "2026-09-29" } });
    await waitFor(() => expect(lastEventsQuery(fetchMock).get("until")).toBe("2026-09-29"));
    const query = lastEventsQuery(fetchMock);
    expect([query.get("result"), query.get("criticality"), query.get("since")]).toEqual(["failed", "critical", "2026-09-01"]);
    expect(await screen.findByText("No events match.")).toBeInTheDocument();

    // Newest first by default; the When header turns it round.
    const when = screen.getByRole("columnheader", { name: /When/ });
    expect(when).toHaveAttribute("aria-sort", "descending");
    fireEvent.click(within(when).getByRole("button"));
    await waitFor(() => expect(lastEventsQuery(fetchMock).get("order")).toBe("asc"));
    expect(lastEventsQuery(fetchMock).get("sort")).toBe("when");
  });
});

describe("Dashboard", () => {
  it("replaces the noisy recent feed with an organization security summary", async () => {
    const summary: DashboardSummary = {
      overall_score: 90, overall_tier: "low", domains: [], top_findings: [], recent_scans: [scan()], asset_count: 1,
      findings_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
    };
    await renderSignedIn(<DashboardPage />, "viewer", {
      "GET /orgs/org-1/dashboard": () => summary,
      "GET /orgs/org-1/dashboard/security-summary": () => ({ window_start: "2026-10-19T00:00:00Z", window_end: "2026-10-26T00:00:00Z", counts: { member_added: 1, role_changed: 2, purge: 0 } }),
    });
    const recent = await screen.findByRole("region", { name: "Security summary" });
    expect(await within(recent).findByRole("link", { name: "Role changes 2" })).toBeInTheDocument();
    expect(screen.queryByText("Recent activity")).not.toBeInTheDocument();
    expect(within(recent).getByRole("link", { name: "All activity" })).toHaveAttribute("href", "/activity");
  });
});

describe("The background worker", () => {
  it("warns while something waits and the worker isn't running", async () => {
    const waiting = scan({ status: "pending", filename: "big.csv", summary: null });
    await renderSignedIn(<Sidebar />, "admin", {
      "GET /orgs/org-1/scans?tracked=true": () => [waiting],
      "GET /orgs/org-1/scans?active=true": () => [waiting],
      "GET /worker-status": () => ({ running: false, last_seen: null }),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("The background worker isn't running");
  });

  it("warns when it stopped in the middle of a job, and says the job was interrupted", async () => {
    // The worker ran it (it checked in) and then stopped: it stays "running".
    const cutOff = scan({ status: "running", filename: "big.csv", summary: null, heartbeat_at: "2026-09-30T21:08:13Z",
      progress: { phase: "reading", rows_done: 122000, rows_total: 500000 } });
    await renderSignedIn(<Sidebar />, "admin", {
      "GET /orgs/org-1/scans?tracked=true": () => [cutOff],
      "GET /orgs/org-1/scans?active=true": () => [cutOff],
      "GET /worker-status": () => ({ running: false, last_seen: "2026-09-30T21:08:13Z" }),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("The background worker isn't running");
    // The upload in the sidebar is marked interrupted (violet, a warning sign).
    const entry = within(screen.getByRole("list", { name: "Uploads in progress" })).getByRole("link");
    await waitFor(() => expect(entry).toHaveClass("text-violet-200"));
    expect(entry).toHaveTextContent("⚠");
  });

  it("isn't asked about for an upload run during its request", async () => {
    const small = scan({ status: "running", filename: "small.csv", summary: null, heartbeat_at: null });
    const { fetchMock } = await renderSignedIn(<Sidebar />, "admin", {
      "GET /orgs/org-1/scans?tracked=true": () => [small],
      "GET /orgs/org-1/scans?active=true": () => [small],
    });
    await screen.findByText(/Processing small\.csv/);
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/worker-status"))).toBe(false);
  });

  it("says nothing while the worker is running", async () => {
    const waiting = scan({ status: "pending", filename: "big.csv", summary: null });
    const { fetchMock } = await renderSignedIn(<Sidebar />, "admin", {
      "GET /orgs/org-1/scans?tracked=true": () => [waiting],
      "GET /orgs/org-1/scans?active=true": () => [waiting],
    });
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/worker-status"))).toBe(true));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("isn't asked about when nothing waits", async () => {
    const { fetchMock } = await renderSignedIn(<Sidebar />, "admin");
    await screen.findByText("Activity");
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/worker-status"))).toBe(false);
  });
});

describe("Signing out", () => {
  it("is recorded in Activity", async () => {
    let signOut: () => void = () => {};
    function LogoutButton() {
      signOut = useApp().logout;
      return null;
    }
    const { fetchMock } = await renderSignedIn(<LogoutButton />, "viewer", { "POST /auth/logout": () => new Response(null, { status: 204 }) });
    signOut();
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, init]) => String(u).endsWith("/auth/logout") && init?.method === "POST")).toBe(true));
  });
});

describe("helpers", () => {
  it("name, time and sum up events", () => {
    expect(eventLabel(event({ type: "restore", details: { undo: true } }))).toBe("Undo archive");
    expect(eventLabel(event({ type: "something_new" }))).toBe("something_new");
    expect(eventLabel(event({ type: "document_uploaded" }))).toBe("Document uploaded");
    expect(eventLabel(event({ type: "document_retired" }))).toBe("Document version retired");
    expect(eventSummary(event({ type: "document_uploaded", counts: {}, details: { version: 2, content_kind: "organization_policy" } }))).toBe(
      "version 2 · organization policy",
    );
    expect(eventSummary(event({ type: "knowledge_consent_changed", counts: {}, details: { to: true, target: "anthropic:model" } }))).toBe(
      "approved for anthropic:model",
    );
    expect(timing(event({ started_at: "2026-09-29T10:00:00Z", ended_at: "2026-09-29T12:05:00Z" }))).toBe("took 2 h 5 min");
    expect(timing(event({ started_at: "2026-09-29T10:00:00Z", ended_at: "2026-09-29T10:00:42Z" }))).toBe("took 42 s");
    expect(timing(event({ started_at: "2026-09-29T10:00:00Z", ended_at: "2026-09-29T10:00:00Z", details: { waited_seconds: 90 } }))).toBe(
      "waited 1 min 30 s",
    );
    // Events carried over from before kept every count, zeros included.
    expect(eventSummary(event({ counts: { failed: 0, assets_created: 66306, warnings_total: 0 } }))).toBe("66,306 assets created");
    expect(eventSummary(event({ counts: { assets_created: 900, assets_updated: 9100, findings_created: 2792, duplicate_findings: 4990 } }))).toBe(
      "900 assets created, 9,100 existing assets updated, 2,792 findings created, 4,990 duplicate findings skipped",
    );
    expect(
      eventSummary(event({ type: "settings_changed", counts: null, details: { archive_retention_days: { from: null, to: 30 } } })),
    ).toBe("archive retention days: default → 30");
    expect(eventSummary(event({ outcome: "failed", counts: null, details: { error: "Invalid JSON", retried: "Cut off" } }))).toBe(
      "Invalid JSON, Cut off",
    );
  });
});
