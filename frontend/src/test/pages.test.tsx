import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AssetsPage from "@/app/(app)/assets/page";
import FindingsPage from "@/app/(app)/findings/page";
import DashboardPage from "@/app/(app)/page";
import SettingsPage from "@/app/(app)/settings/page";
import type { Asset, DashboardSummary, Finding } from "@/lib/types";
import { json, renderSignedIn } from "@/test/helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/" }));

const ASSETS: Asset[] = [
  {
    id: "a1", org_id: "org-1", type: "server", hostname: "web-01.acme.io", ip: "10.0.1.10", cloud_id: null,
    environment: "production", criticality: "high", tags: ["web", "dmz"], created_at: "2026-09-27T10:00:00Z",
  },
];

function finding(overrides: Partial<Finding>): Finding {
  return {
    id: overrides.category ?? "f", org_id: "org-1", asset_id: "a1", scan_id: null, category: null,
    domain: "vulnerability_management", severity: "low", description: null, source: "nessus",
    created_at: "2026-09-27T10:00:00Z", ...overrides,
  };
}

const IMPORT_REPORT = { created: 1, updated: 0, skipped: 0, duplicates: 0, failed: 0, errors: [] };

describe("Assets page", () => {
  it("lists the org's assets and imports a file for admins", async () => {
    let assets: Asset[] = [];
    await renderSignedIn(<AssetsPage />, "admin", {
      "GET /orgs/org-1/assets": () => assets,
      "POST /orgs/org-1/assets/import": () => {
        assets = ASSETS;
        return json({ scan_id: "s1", status: "completed", report: IMPORT_REPORT }, 201);
      },
    });
    expect(await screen.findByText("No assets yet.")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("assets-file-input"), { target: { files: [new File(["x"], "assets.csv")] } });

    expect(await screen.findByText("web-01.acme.io")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Import result" })).toHaveTextContent("Created 1");
    const row = screen.getByText("web-01.acme.io").closest("tr")!;
    expect(row).toHaveTextContent("10.0.1.10");
    expect(row).toHaveTextContent("webdmz");
  });

  it("hides the import button from viewers", async () => {
    await renderSignedIn(<AssetsPage />, "viewer", { "GET /orgs/org-1/assets": () => ASSETS });

    expect(await screen.findByText("web-01.acme.io")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import assets" })).not.toBeInTheDocument();
  });

  it("shows a load error", async () => {
    await renderSignedIn(<AssetsPage />, "admin", {
      "GET /orgs/org-1/assets": () => json({ detail: "Cross-organization access denied" }, 403),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Cross-organization access denied");
  });
});

describe("Findings page", () => {
  it("groups findings by domain, most severe first, with their asset", async () => {
    await renderSignedIn(<FindingsPage />, "auditor", {
      "GET /orgs/org-1/assets": () => ASSETS,
      "GET /orgs/org-1/findings": () => [
        finding({ category: "LOW-ONE", description: "Minor issue", severity: "low" }),
        finding({ category: "CRIT-ONE", description: "Remote code execution", severity: "critical" }),
        finding({ category: "MFA", description: "MFA off", domain: "identity_access", severity: "high", asset_id: null }),
      ],
    });

    const vuln = await screen.findByRole("region", { name: "Vulnerability Mgmt" });
    const rows = within(vuln).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual([
      "Remote code executionCRIT-ONE",
      "Minor issueLOW-ONE",
    ]);
    expect(rows[0]).toHaveTextContent("web-01.acme.io");
    expect(screen.getByRole("region", { name: "Identity & Access" })).toHaveTextContent("MFA off");
    expect(screen.queryByRole("region", { name: "Backup & Recovery" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload findings" })).toBeInTheDocument();
  });

  it("hides the upload button from viewers", async () => {
    await renderSignedIn(<FindingsPage />, "viewer", {
      "GET /orgs/org-1/assets": () => [],
      "GET /orgs/org-1/findings": () => [],
    });
    expect(await screen.findByText("No findings yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload findings" })).not.toBeInTheDocument();
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
    recent_scans: [
      {
        id: "s1", org_id: "org-1", scan_type: "nessus", scope: null, status: "completed",
        started_at: "2026-09-27T10:00:00Z", completed_at: "2026-09-27T10:01:00Z", source: "upload",
        filename: "weekly.nessus", summary: IMPORT_REPORT,
      },
    ],
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
  it("shows the ingestion settings to non-admins read-only", async () => {
    await renderSignedIn(<SettingsPage />, "auditor", {
      "GET /orgs/org-1/settings": () => ({
        import_partial_success: true, asset_existing_strategy: "update", nessus_info_severity: "skip",
        nessus_domain_map: {}, nessus_default_domain: "vulnerability_management", overridden: [],
        nessus_domain_map_override: {},
      }),
    });

    await waitFor(() => expect(screen.getByLabelText("Nessus Info items")).toBeDisabled());
    expect(screen.getByText("Only organization admins can change these settings.")).toBeInTheDocument();
  });
});
