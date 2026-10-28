import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import OrgGate from "@/components/OrgGate";
import { AppProvider } from "@/context/AppContext";
import { ImportsProvider } from "@/context/ImportsContext";
import { setToken } from "@/lib/apiClient";
import type { MyOrganization, Scan, UserRole } from "@/lib/types";

export const API = "/api/v1";

type Handler = (init: RequestInit) => unknown | Response | Promise<unknown | Response>;

/** Replaces fetch with handlers keyed by "METHOD /path" (path after /api/v1).
 * A key with a query string matches only that query; one without matches the
 * path with any query. A handler returns a body (sent as 200 JSON) or a full
 * Response. Returns the mock so tests can inspect calls. Unless routes say
 * otherwise, there's no session cookie: POST /auth/refresh is refused. */
export function mockApi(routes: Record<string, Handler>) {
  const all: Record<string, Handler> = { "POST /auth/refresh": () => json({ detail: NO_SESSION }, 401), ...routes };
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? "GET"} ${url.replace(API, "")}`;
    const handler = all[key] ?? all[key.split("?")[0]];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    const result = await handler(init);
    return result instanceof Response ? result : json(result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const NO_SESSION = { code: "session_ended", message: "Please sign in again." };

/** The fetch calls made to "METHOD /path" (in order), as [url, init]. */
export function callsTo(fetchMock: ReturnType<typeof mockApi>, key: string): [string, RequestInit][] {
  return (fetchMock.mock.calls as [string, RequestInit][]).filter(
    ([url, init]) => `${init?.method ?? "GET"} ${url.replace(API, "")}` === key,
  );
}

/** The RequestInit of the index-th fetch call. */
export function requestInit(fetchMock: ReturnType<typeof mockApi>, index = 0): RequestInit {
  return fetchMock.mock.calls[index]?.[1] ?? {};
}

/** The parsed JSON body of the index-th fetch call. */
export function requestBody(fetchMock: ReturnType<typeof mockApi>, index = 0): unknown {
  return JSON.parse(String(requestInit(fetchMock, index).body));
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function org(overrides: Partial<MyOrganization> = {}): MyOrganization {
  return {
    id: "org-1",
    name: "Acme Corp",
    industry: null,
    size: null,
    created_at: "2026-09-27T10:00:00Z",
    role: "admin",
    ...overrides,
  };
}

/** A scan (an import), completed by default. */
export function scan(overrides: Partial<Scan> = {}): Scan {
  return {
    id: "s1",
    org_id: "org-1",
    scan_type: "asset_import",
    scope: null,
    status: "completed",
    started_at: "2026-09-27T10:00:00Z",
    completed_at: "2026-09-27T10:01:00Z",
    source: "upload",
    filename: "assets.csv",
    summary: null,
    profile: null,
    started_by: "user-1",
    dismissed_at: null,
    progress: null,
    ...overrides,
  };
}

/** Render inside a signed-in AppProvider whose selected org has `role`, with
 * the app's import tracker (no imports unless routes say otherwise), and wait
 * until the org has loaded. */
export async function renderSignedIn(
  ui: React.ReactElement,
  role: UserRole = "admin",
  routes: Record<string, Handler> = {},
  pollIntervalMs = 10,
) {
  setToken("test-token");
  const fetchMock = mockApi({
    "GET /orgs": () => [org({ role })],
    "GET /orgs/org-1/scans?tracked=true": () => [],
    "GET /orgs/org-1/scans?active=true": () => [],
    "GET /orgs/org-1/archive-jobs?tracked=true": () => [],
    "GET /orgs/org-1/events": () => ({ items: [], total: 0 }),
    "GET /orgs/org-1/dashboard/security-summary": () => ({ window_start: "2026-10-19T00:00:00Z", window_end: "2026-10-26T00:00:00Z", counts: { member_added: 0, role_changed: 0, purge: 0 } }),
    "GET /orgs/org-1/scoring/dashboard-state": () => ({ scoring_mode: "findings_based", settings_version: 0, evidence_revision: 0, evaluation_id: null }),
    "GET /orgs/org-1/events/facets": () => ({ type: [], actor: [] }),
    "GET /worker-status": () => ({ running: true, last_seen: "2026-09-29T10:00:00Z" }),
    "GET /orgs/org-1/assets/facets": () => ({ type: [], subtype: [], environment: [], criticality: [] }),
    "GET /orgs/org-1/findings/facets": () => ({ source: [] }),
    "GET /orgs/org-1/reports/facets": () => ({ status: [], frameworks: [] }),
    "GET /orgs/org-1/reports/capabilities": () => ({ rule_based_test_enabled: false }),
    "GET /orgs/org-1/documents/settings": () => ({ report_granted: true, report_target: "anthropic:test-model:test-prompt" }),
    ...routes,
  });
  const result = render(
    <AppProvider>
      <ImportsProvider pollIntervalMs={pollIntervalMs}>
        <OrgGate>
          <span data-testid="org-ready" />
          {ui}
        </OrgGate>
      </ImportsProvider>
    </AppProvider>,
  );
  await screen.findByTestId("org-ready");
  return { ...result, fetchMock };
}
