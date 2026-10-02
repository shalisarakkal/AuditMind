import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FindingsPage from "@/app/(app)/findings/page";
import ImportButton from "@/components/ImportButton";
import ImportProfileEditor from "@/components/ImportProfileEditor";
import { importCountsText } from "@/lib/importCounts";
import type { FindingListItem, ImportProfile } from "@/lib/types";
import { mockApi, renderSignedIn, requestBody, requestInit, scan } from "@/test/helpers";
import { AZURE_PROFILE, BUILTIN_PROFILES } from "@/test/profiles";

const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => "/findings",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
});

const ACTIVITY_LOG = JSON.stringify([
  { operation_id: "AZ-1", time: "2026-06-01 10:00:00", operation_name: "x/roleAssignments/write", subscription_id: "s",
    resource_group: "r", resource_type: "v", status: "Succeeded", caller: "u" },
]);

describe("event logs", () => {
  it("are detected from their columns and uploaded with their source", async () => {
    const { fetchMock } = await renderSignedIn(
      <ImportButton orgId="org-1" kind="findings" accept=".csv,.json" label="Upload file" profiles={[...BUILTIN_PROFILES, AZURE_PROFILE]} />,
      "admin",
      { "POST /orgs/org-1/imports": () => ({ scan_id: "s1", status: "pending" }), "GET /orgs/org-1/scans/s1": () => scan() },
    );
    fireEvent.change(screen.getByTestId("findings-file-input"), { target: { files: [new File([ACTIVITY_LOG], "activity.json")] } });

    expect(await screen.findByLabelText("Source")).toHaveValue("azure_activity");
    expect(screen.queryByRole("note")).not.toBeInTheDocument(); // no host needed
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.findIndex(([, init]) => init?.method === "POST");
    expect((requestInit(fetchMock, post).body as FormData).get("profile")).toBe("azure_activity");
  });

  it("count their findings as findings, not assets", () => {
    expect(importCountsText("azure_activity_import", { created: 3 })).toBe("3 findings created");
  });

  it("let an org's copy turn rules off or change their severity", async () => {
    const copy: ImportProfile = { ...AZURE_PROFILE, key: "copy-1", name: "Our Azure", builtin: false };
    const fetchMock = mockApi({ "PATCH /orgs/org-1/import-profiles/copy-1": () => copy });
    render(<ImportProfileEditor orgId="org-1" profile={copy} onSaved={() => undefined} onCancel={() => undefined} />);

    expect(screen.queryByText("Type names")).not.toBeInTheDocument(); // no assets
    expect(screen.getByText(/from 10 events/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Failed operations"));
    fireEvent.change(screen.getByLabelText("Severity for Role assignment created"), { target: { value: "critical" } });
    expect(screen.getByLabelText("Severity for Failed operations")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(1));
    expect((requestBody(fetchMock) as { params: { rules: unknown } }).params.rules).toEqual({
      role_assignment_created: { severity: "critical" },
      failed_operations: { enabled: false },
    });
  });
});

const EVENT_FINDING: FindingListItem = {
  id: "f1", org_id: "org-1", asset_id: null, scan_id: "s1", category: "Role assignment created (2026-06-01 to 2026-06-04)",
  domain: "identity_access", severity: "high", description: "Role assignment created: 3 events by 2 callers in 1 subscription.",
  source: "azure_activity", created_at: "2026-10-02T10:00:00Z", asset_hostname: null, asset_ip: null, asset_cloud_id: null,
  event_count: 3, first_seen: "2026-06-01T10:00:00Z", last_seen: "2026-06-04T10:00:00Z",
  details: {
    rule: "role_assignment_created",
    actors: { distinct: "2", top: [{ value: "ann@acme.io", events: 2 }, { value: "bob@acme.io", events: 1 }] },
    scopes: { name: "subscriptions", distinct: "1", top: [{ value: "sub-1", events: 3 }] },
    examples: [{ caller: "ann@acme.io", status: "Succeeded" }],
  },
};

describe("an event log's finding", () => {
  it("shows its events, and its details on demand", async () => {
    await renderSignedIn(<FindingsPage />, "viewer", {
      "GET /orgs/org-1/findings": () => ({ items: [EVENT_FINDING], total: 1, domain_counts: { identity_access: 1 } }),
      "GET /orgs/org-1/findings/facets": () => ({ source: ["azure_activity"] }),
    });
    const row = (await screen.findByText(EVENT_FINDING.description!)).closest("tr")!;
    expect(row).toHaveTextContent("3 events");
    expect(within(row).getByText("—")).toBeInTheDocument(); // no asset

    fireEvent.click(within(row).getByRole("button", { name: "Details" }));
    const details = screen.getByRole("region", { name: "Event details" });
    expect(details).toHaveTextContent("Most frequent actors (2 in all)");
    const ann = within(details).getByText("ann@acme.io").closest("li")!;
    expect(ann).toHaveTextContent("2");
    expect(details).toHaveTextContent("Most frequent subscriptions (1 in all)");
    expect(details).toHaveTextContent('"status":"Succeeded"');
    fireEvent.click(within(row).getByRole("button", { name: "Hide details" }));
    expect(screen.queryByRole("region", { name: "Event details" })).not.toBeInTheDocument();
  });
});
