import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import OrgGate from "@/components/OrgGate";
import { AppProvider } from "@/context/AppContext";
import type { MyOrganization, UserRole } from "@/lib/types";

export const API = "http://localhost:8000/api/v1";

type Handler = (init: RequestInit) => unknown | Response | Promise<unknown | Response>;

/** Replaces fetch with handlers keyed by "METHOD /path" (path after /api/v1).
 * A handler returns a body (sent as 200 JSON) or a full Response. Returns the
 * mock so tests can inspect calls. */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? "GET"} ${url.replace(API, "")}`;
    const handler = routes[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    const result = await handler(init);
    return result instanceof Response ? result : json(result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

/** Render inside a signed-in AppProvider whose selected org has `role`,
 * and wait until the org has loaded. */
export async function renderSignedIn(ui: React.ReactElement, role: UserRole = "admin", routes: Record<string, Handler> = {}) {
  window.localStorage.setItem("auditmind_token", "test-token");
  const fetchMock = mockApi({ "GET /orgs": () => [org({ role })], ...routes });
  const result = render(
    <AppProvider>
      <OrgGate>
        <span data-testid="org-ready" />
        {ui}
      </OrgGate>
    </AppProvider>,
  );
  await screen.findByTestId("org-ready");
  return { ...result, fetchMock };
}
