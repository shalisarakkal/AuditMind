import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AssetsPage from "@/app/(app)/assets/page";
import FindingsPage from "@/app/(app)/findings/page";
import DashboardPage from "@/app/(app)/page";
import SettingsPage from "@/app/(app)/settings/page";
import type { Asset, DashboardSummary, Finding, FindingListItem } from "@/lib/types";
import { json, renderSignedIn, requestInit, scan } from "@/test/helpers";
import { BUILTIN_PROFILES } from "@/test/profiles";

// The page address: tests set `search` before rendering; lists write theirs
// back through router.replace.
const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  usePathname: () => "/assets",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
  navigation.replace.mockClear();
});

const ASSETS: Asset[] = [
  {
    id: "a1", org_id: "org-1", type: "server", hostname: "web-01.acme.io", ip: "10.0.1.10", cloud_id: null,
    environment: "production", criticality: "high", tags: ["web", "dmz"], created_at: "2026-09-27T10:00:00Z",
    subtype: null, details: {},
  },
];

const ENDPOINT_ASSET: Asset = {
  ...ASSETS[0], id: "a2", type: "workstation", subtype: "endpoint", hostname: "DEV-446", ip: null, tags: null,
  details: { endpoint_id: "EP-00000", agent_version: "v5.3", open_ports: [135, 21] },
};

const PROFILES = { "GET /orgs/org-1/import-profiles": () => BUILTIN_PROFILES };

function finding(overrides: Partial<Finding>): Finding {
  return {
    id: overrides.category ?? "f", org_id: "org-1", asset_id: "a1", scan_id: null, category: null,
    domain: "vulnerability_management", severity: "low", description: null, source: "nessus",
    created_at: "2026-09-27T10:00:00Z", ...overrides,
  };
}

const IMPORT_REPORT = {
  created: 1, updated: 0, skipped: 0, duplicates: 0, failed: 0, findings_created: 0, errors: [], warnings: [],
};

const page = <T,>(items: T[], total = items.length) => ({ items, total });

function listItem(overrides: Partial<FindingListItem>): FindingListItem {
  return { ...finding(overrides), asset_hostname: "web-01.acme.io", asset_ip: "10.0.1.10", asset_cloud_id: null, ...overrides };
}

/** The query of the last GET of `path` (e.g. "/orgs/org-1/assets"). */
function lastQuery(fetchMock: Awaited<ReturnType<typeof renderSignedIn>>["fetchMock"], path: string) {
  const urls = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes(`${path}?`));
  return new URLSearchParams(urls.at(-1)?.split("?")[1]);
}

describe("Assets page", () => {
  it("lists the org's assets and imports a file for admins", async () => {
    let assets: Asset[] = [];
    await renderSignedIn(<AssetsPage />, "admin", {
      ...PROFILES,
      "GET /orgs/org-1/assets": () => page(assets),
      "POST /orgs/org-1/assets/import": () => {
        assets = ASSETS;
        return json({ scan_id: "s1", status: "completed", report: IMPORT_REPORT }, 201);
      },
      "GET /orgs/org-1/scans/s1": () => scan({ summary: IMPORT_REPORT }),
    });
    expect(await screen.findByText("No assets yet.")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("assets-file-input"), {
      target: { files: [new File(["type,hostname\nserver,web-01\n"], "assets.csv")] },
    });
    expect(await screen.findByLabelText("Source")).toHaveValue("generic_assets");
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByText("web-01.acme.io")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Import result" })).toHaveTextContent("Created 1");
    const row = screen.getByText("web-01.acme.io").closest("tr")!;
    expect(row).toHaveTextContent("10.0.1.10");
    expect(row).toHaveTextContent("webdmz");
  });

  it("imports a tool export with its detected profile", async () => {
    const report = { ...IMPORT_REPORT, created: 7, findings_created: 8, warnings: [{ row: 9, message: "odd value" }] };
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "auditor", {
      ...PROFILES,
      "GET /orgs/org-1/assets": () => page([]),
      "POST /orgs/org-1/imports": () => json({ scan_id: "s1", status: "completed", report }, 201),
      "GET /orgs/org-1/scans/s1": () => scan({ scan_type: "endpoint_agent_import", filename: "edr.csv", summary: report }),
    });
    await screen.findByText("No assets yet.");

    const csv = "EndPointID,DeviceName,LastHeartbeat,ThreatsDetected,ComplianceStatus\nEP-1,DEV-1,x,0,ok\n";
    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File([csv], "edr.csv")] } });
    expect(await screen.findByLabelText("Source")).toHaveValue("endpoint_agent");
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    const panel = await screen.findByRole("region", { name: "Import result" });
    expect(panel).toHaveTextContent("Assets created 7");
    expect(panel).toHaveTextContent("Findings created 8");
    expect(panel).toHaveTextContent("Warnings 1");
    const upload = fetchMock.mock.calls.findIndex(([url]) => String(url).endsWith("/imports"));
    expect((requestInit(fetchMock, upload).body as FormData).get("profile")).toBe("endpoint_agent");
  });

  it("shows type, subtype and expandable details", async () => {
    await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page([...ASSETS, ENDPOINT_ASSET]) });

    const row = (await screen.findByText("DEV-446")).closest("tr")!;
    expect(row).toHaveTextContent("Workstation");
    expect(row).toHaveTextContent("endpoint");
    expect(screen.getByText("web-01.acme.io").closest("tr")).toHaveTextContent("Server");
    // Only assets with details get the toggle.
    expect(screen.getAllByRole("button", { name: /details/ })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Show details for DEV-446" }));
    const details = row.nextElementSibling as HTMLElement;
    expect(details).toHaveTextContent("Endpoint IDEP-00000");
    expect(details).toHaveTextContent("Agent versionv5.3");
    expect(details).toHaveTextContent("Open ports135, 21");
    fireEvent.click(screen.getByRole("button", { name: "Hide details for DEV-446" }));
    expect(screen.queryByText("EP-00000")).not.toBeInTheDocument();
  });

  it("hides the import button from viewers", async () => {
    // Viewers don't load import profiles either (no route mocked for them).
    await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS) });

    expect(await screen.findByText("web-01.acme.io")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import data" })).not.toBeInTheDocument();
  });

  it("searches and pages through the assets", async () => {
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", {
      "GET /orgs/org-1/assets": () => page(ASSETS, 250),
    });
    expect(await screen.findByText("Showing 1–100 of 250")).toBeInTheDocument();
    expect(screen.getByText("250 assets in Acme Corp")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("offset")).toBe("100"));
    expect(await screen.findByText("Showing 101–200 of 250")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: " web " } });
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("q")).toBe("web"));
    // A new search starts from the first page.
    expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("offset")).toBe("0");
  });

  it("sorts by a column: ascending, descending, then the default order", async () => {
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS) });
    const header = () => screen.getByRole("columnheader", { name: /Hostname/ });
    await screen.findByText("web-01.acme.io");
    expect(header()).toHaveAttribute("aria-sort", "none");

    fireEvent.click(within(header()).getByRole("button"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("sort")).toBe("hostname"));
    expect(header()).toHaveAttribute("aria-sort", "ascending");
    // The address also names the org the view belongs to.
    expect(navigation.replace).toHaveBeenLastCalledWith("/assets?sort=hostname&org=org-1", { scroll: false });

    fireEvent.click(within(header()).getByRole("button"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("order")).toBe("desc"));
    expect(header()).toHaveAttribute("aria-sort", "descending");

    fireEvent.click(within(header()).getByRole("button"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("sort")).toBeNull());
    expect(navigation.replace).toHaveBeenLastCalledWith("/assets", { scroll: false });
  });

  it("filters by column: pick-lists from the org's values, contains boxes for text", async () => {
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", {
      "GET /orgs/org-1/assets": () => page(ASSETS),
      "GET /orgs/org-1/assets/facets": () => ({ type: ["server", "workstation"], subtype: [], environment: ["", "prod"], criticality: [] }),
    });
    await screen.findByText("web-01.acme.io");

    const environment = within(await screen.findByRole("group", { name: "environment values" }));
    expect(environment.getAllByRole("checkbox").map((c) => c.parentElement!.textContent)).toEqual(["(blank)", "prod"]);
    fireEvent.click(environment.getByLabelText("prod"));
    fireEvent.click(environment.getByLabelText("(blank)"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").getAll("environment")).toEqual(["prod", ""]));
    expect(screen.getByLabelText("Filter environment: prod +1")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter hostname"), { target: { value: "web" } });
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("hostname")).toBe("web"));
    expect(screen.queryByText(/assets in Acme Corp/)).not.toBeInTheDocument(); // the count is of all assets

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").toString()).toBe("limit=100&offset=0"));
    expect(screen.getByLabelText("Filter hostname")).toHaveValue("");
  });

  it("opens with the sort and filters in the page address", async () => {
    navigation.search = "sort=ip&order=desc&type=server&hostname=web&offset=100";
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS, 150) });
    await screen.findByText("web-01.acme.io");

    const query = lastQuery(fetchMock, "/orgs/org-1/assets");
    expect(Object.fromEntries(query)).toEqual({ sort: "ip", order: "desc", type: "server", hostname: "web", offset: "100", limit: "100" });
    expect(screen.getByLabelText("Filter hostname")).toHaveValue("web");
    expect(screen.getByRole("columnheader", { name: /^IP/ })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByText("Showing 101–150 of 150")).toBeInTheDocument();
    // An address naming no org yet (an older link) gets this one's.
    expect(navigation.replace).toHaveBeenCalledWith(
      "/assets?sort=ip&order=desc&type=server&hostname=web&offset=100&org=org-1",
      { scroll: false },
    );
  });

  it("starts clean when the address holds another org's view", async () => {
    navigation.search = "org=org-9&type=server&hostname=web&offset=100";
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS) });
    await screen.findByText("web-01.acme.io");

    expect(lastQuery(fetchMock, "/orgs/org-1/assets").toString()).toBe("limit=100&offset=0");
    expect(navigation.replace).toHaveBeenCalledWith("/assets", { scroll: false });
    expect(screen.getByLabelText("Filter hostname")).toHaveValue("");
  });

  it("keeps a view that belongs to this org", async () => {
    navigation.search = "org=org-1&type=server";
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS) });
    await screen.findByText("web-01.acme.io");

    expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("type")).toBe("server");
  });

  it("clears typing that hasn't been applied yet along with the filters", async () => {
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS) });
    await screen.findByText("web-01.acme.io");
    fireEvent.change(screen.getByLabelText("Filter hostname"), { target: { value: "web" } });
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("hostname")).toBe("web"));

    // Typed, and cleared before it was applied.
    fireEvent.change(screen.getByLabelText("Filter IP"), { target: { value: "10.0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(lastQuery(fetchMock, "/orgs/org-1/assets").toString()).toBe("limit=100&offset=0");
    expect(screen.getByLabelText("Filter IP")).toHaveValue("");
    expect(screen.getByLabelText("Filter hostname")).toHaveValue("");
  });

  it("moves to the last page when the page asked for no longer exists", async () => {
    navigation.search = "org=org-1&offset=300";
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page(ASSETS, 150) });

    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("offset")).toBe("100"));
    expect(await screen.findByText("Showing 101–150 of 150")).toBeInTheDocument();
    expect(screen.queryByText(/Showing 301/)).not.toBeInTheDocument();
  });

  it("shows a cloud resource's cloud ID, which can be sorted and filtered", async () => {
    const lambda: Asset = {
      ...ASSETS[0], id: "a3", type: "cloud_resource", subtype: "Lambda", hostname: null, ip: null,
      cloud_id: "arn:aws:lambda:us-east-1:111:function:billing", tags: null,
    };
    const { fetchMock } = await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => page([lambda]) });

    const cell = await screen.findByText("arn:aws:lambda:us-east-1:111:function:billing");
    expect(cell).toHaveAttribute("title", "arn:aws:lambda:us-east-1:111:function:billing"); // shortened on screen
    fireEvent.click(within(screen.getByRole("columnheader", { name: /^Cloud ID/ })).getByRole("button"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("sort")).toBe("cloud_id"));
    fireEvent.change(screen.getByLabelText("Filter cloud ID"), { target: { value: "lambda" } });
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/assets").get("cloud_id")).toBe("lambda"));
  });

  it("shows a load error", async () => {
    await renderSignedIn(<AssetsPage />, "admin", {
      "GET /orgs/org-1/assets": () => json({ detail: "Cross-organization access denied" }, 403),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Cross-organization access denied");
  });
});

describe("Findings page", () => {
  it("lists findings as the server orders them, with their asset and domain", async () => {
    await renderSignedIn(<FindingsPage />, "auditor", {
      ...PROFILES,
      "GET /orgs/org-1/findings": () => ({
        ...page([
          listItem({ category: "CRIT-ONE", description: "Remote code execution", severity: "critical" }),
          listItem({ category: "MFA", description: "MFA off", domain: "identity_access", severity: "high", asset_hostname: null, asset_ip: null }),
          listItem({ category: "LOW-ONE", description: "Minor issue", severity: "low" }),
        ]),
        domain_counts: { vulnerability_management: 2, identity_access: 1 },
      }),
    });

    const rows = (await screen.findAllByRole("row")).slice(2); // titles, then filters
    expect(rows.map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual([
      "Remote code executionCRIT-ONE",
      "MFA offMFA",
      "Minor issueLOW-ONE",
    ]);
    expect(rows[0]).toHaveTextContent("web-01.acme.io");
    expect(rows[0]).toHaveTextContent("Vulnerability Mgmt");
    expect(rows[1]).toHaveTextContent("Identity & Access");
    expect(screen.getByRole("button", { name: "Import data" })).toBeInTheDocument();
  });

  it("names a finding's cloud resource by its cloud ID when it has no hostname or IP", async () => {
    await renderSignedIn(<FindingsPage />, "viewer", {
      "GET /orgs/org-1/findings": () => ({
        ...page([listItem({ category: "S3-PUBLIC", asset_hostname: null, asset_ip: null, asset_cloud_id: "arn:aws:s3:::acme-backups" })]),
        domain_counts: { backup_recovery: 1 },
      }),
    });

    const row = (await screen.findByText("S3-PUBLIC")).closest("tr")!;
    expect(row).toHaveTextContent("arn:aws:s3:::acme-backups");
  });

  it("filters by domain, showing each domain's count", async () => {
    const { fetchMock } = await renderSignedIn(<FindingsPage />, "viewer", {
      "GET /orgs/org-1/findings": () => ({
        ...page([listItem({ category: "C1" })], 4210),
        domain_counts: { vulnerability_management: 4210, identity_access: 12 },
      }),
    });

    const domains = await screen.findByRole("group", { name: "Domain" });
    expect(within(domains).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "All (4,222)",
      "Identity & Access (12)",
      "Vulnerability Mgmt (4,210)",
    ]);

    fireEvent.click(within(domains).getByRole("button", { name: "Identity & Access (12)" }));

    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/findings").get("domain")).toBe("identity_access"));
    expect(within(domains).getByRole("button", { name: "Identity & Access (12)" })).toHaveAttribute("aria-pressed", "true");
  });

  it("sorts most severe first by default, and by any column on request", async () => {
    const { fetchMock } = await renderSignedIn(<FindingsPage />, "viewer", {
      "GET /orgs/org-1/findings": () => ({ ...page([listItem({ category: "C1" })]), domain_counts: { vulnerability_management: 1 } }),
    });
    const severity = await screen.findByRole("columnheader", { name: /Severity/ });
    expect(severity).toHaveAttribute("aria-sort", "ascending"); // the default order
    expect(lastQuery(fetchMock, "/orgs/org-1/findings").get("sort")).toBeNull();

    fireEvent.click(within(screen.getByRole("columnheader", { name: /Asset/ })).getByRole("button"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/findings").get("sort")).toBe("asset"));
    expect(screen.getByRole("columnheader", { name: /Severity/ })).toHaveAttribute("aria-sort", "none");

    fireEvent.click(within(screen.getByRole("group", { name: "severity values" })).getByLabelText("Critical"));
    await waitFor(() => expect(lastQuery(fetchMock, "/orgs/org-1/findings").getAll("severity")).toEqual(["critical"]));
    // Filtering keeps the sort.
    expect(lastQuery(fetchMock, "/orgs/org-1/findings").get("sort")).toBe("asset");
  });

  it("hides the upload button from viewers", async () => {
    await renderSignedIn(<FindingsPage />, "viewer", {
      "GET /orgs/org-1/findings": () => ({ ...page([]), domain_counts: {} }),
    });
    expect(await screen.findByText("No findings yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import data" })).not.toBeInTheDocument();
  });
});

describe("Dashboard page", () => {
  const summary: DashboardSummary = {
    overall_score: 87.35,
    overall_tier: "low",
    domains: [
      { domain: "network_config", score: 93, tier: "low", justification: "1 low finding(s)" },
      { domain: "identity_access", score: 55, tier: "high", justification: "2 critical finding(s)" },
    ],
    top_findings: [finding({ category: "CVE-1", description: "Unpatched RCE", severity: "critical" })],
    recent_scans: [scan({ scan_type: "nessus", filename: "weekly.nessus", summary: IMPORT_REPORT })],
    asset_count: 12,
    findings_by_severity: { critical: 1, high: 0, medium: 3, low: 5 },
  };

  it("shows live scores, top issues and recent imports", async () => {
    await renderSignedIn(<DashboardPage />, "viewer", { "GET /orgs/org-1/dashboard": () => summary });

    expect(await screen.findByTestId("overall-score")).toHaveTextContent("87");
    expect(screen.getByText("low risk tier")).toBeInTheDocument();
    expect(screen.getByText("12 assets · 9 findings")).toBeInTheDocument();
    // Domain cards follow the canonical order, not the API's.
    const labels = screen.getAllByText(/^(Identity & Access|Network & Config)$/).map((el) => el.textContent);
    expect(labels).toEqual(["Identity & Access", "Network & Config"]);
    expect(screen.getByTitle("2 critical finding(s)")).toHaveTextContent("55");
    expect(screen.getByText("Unpatched RCE")).toBeInTheDocument();
    expect(screen.getByText("weekly.nessus")).toBeInTheDocument();
  });

  it("guides an empty org to upload findings", async () => {
    await renderSignedIn(<DashboardPage />, "admin", {
      "GET /orgs/org-1/dashboard": () => ({ ...summary, top_findings: [], recent_scans: [] }),
    });
    expect(await screen.findByRole("link", { name: "Upload findings" })).toHaveAttribute("href", "/findings");
    expect(screen.getByText("Nothing imported yet.")).toBeInTheDocument();
  });
});

describe("Settings page", () => {
  it("shows the ingestion settings and import profiles to non-admins read-only", async () => {
    await renderSignedIn(<SettingsPage />, "auditor", {
      ...PROFILES,
      "GET /orgs/org-1/settings": () => ({
        import_partial_success: true, asset_existing_strategy: "update", nessus_info_severity: "skip",
        nessus_domain_map: {}, nessus_default_domain: "vulnerability_management", overridden: [],
        nessus_domain_map_override: {}, asset_type_aliases: { laptop: "workstation" }, asset_type_aliases_override: {},
      }),
    });

    await waitFor(() => expect(screen.getByLabelText("Nessus Info items")).toBeDisabled());
    expect(screen.getByText("Only organization admins can change these settings.")).toBeInTheDocument();
    expect(screen.getByText("laptop → Workstation")).toBeInTheDocument();
    expect(await screen.findByText("Endpoint agent export")).toBeInTheDocument();
    expect(screen.getByText("Only organization admins can change import profiles.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(Copy|Edit|Delete) / })).not.toBeInTheDocument();
  });
});
