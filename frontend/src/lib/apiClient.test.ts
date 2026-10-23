import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, getToken, refreshAccessToken, setSessionHandlers, setToken } from "@/lib/apiClient";
import { callsTo, json, mockApi, requestInit } from "@/test/helpers";

const TOKEN = { token_type: "bearer", expires_in: 900, must_change_password: false };

describe("apiClient", () => {
  const assign = vi.fn();

  beforeEach(() => {
    assign.mockReset();
    vi.stubGlobal("location", { ...window.location, assign });
    setSessionHandlers(null);
  });

  it("sends the bearer token when signed in, and none when not", async () => {
    const fetchMock = mockApi({ "GET /orgs": () => [] });

    await api.get("/orgs");
    setToken("abc");
    await api.get("/orgs");

    const headers = (i: number) => requestInit(fetchMock, i).headers as Record<string, string>;
    expect(headers(0).Authorization).toBeUndefined();
    expect(headers(1).Authorization).toBe("Bearer abc");
  });

  it("reaches the API through this site, with the app's header", async () => {
    const fetchMock = mockApi({ "GET /orgs": () => [] });

    await api.get("/orgs");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/orgs");
    const init = requestInit(fetchMock);
    expect((init.headers as Record<string, string>)["X-Requested-With"]).toBe("AuditMind");
    expect(init.credentials).toBe("same-origin");
  });

  it("keeps the token in memory only", async () => {
    window.localStorage.setItem("auditmind_token", "left-over");
    vi.resetModules();
    const fresh = await import("@/lib/apiClient");
    expect(window.localStorage.getItem("auditmind_token")).toBeNull();

    fresh.setToken("abc");
    expect(fresh.getToken()).toBe("abc");
    expect(Object.values({ ...window.localStorage })).not.toContain("abc");
  });

  it("marks the app's own polling as background", async () => {
    const fetchMock = mockApi({ "GET /worker-status": () => ({ running: true }) });

    await api.get("/worker-status", { background: true });
    await api.get("/worker-status");

    const headers = (i: number) => requestInit(fetchMock, i).headers as Record<string, string>;
    expect(headers(0)["X-Activity"]).toBe("background");
    expect(headers(1)["X-Activity"]).toBeUndefined();
  });

  it("sends JSON bodies with a JSON content type", async () => {
    const fetchMock = mockApi({ "POST /orgs": () => ({ id: "1" }) });

    await api.post("/orgs", { name: "Acme" });

    const init = requestInit(fetchMock);
    expect(init.body).toBe('{"name":"Acme"}');
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("uploads files as multipart form data without forcing a content type", async () => {
    const fetchMock = mockApi({ "POST /orgs/o/assets/import": () => ({}) });

    await api.upload("/orgs/o/assets/import", new File(["type\n"], "a.csv"));

    const init = requestInit(fetchMock);
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("renews a run-out token from the session cookie and tries again", async () => {
    setToken("old");
    const fetchMock = mockApi({
      "GET /orgs": (init) =>
        (init.headers as Record<string, string>).Authorization === "Bearer new" ? [{ id: "o" }] : json({ detail: {} }, 401),
      "POST /auth/refresh": () => ({ access_token: "new", ...TOKEN }),
    });

    await expect(api.get("/orgs")).resolves.toEqual([{ id: "o" }]);
    expect(getToken()).toBe("new");
    expect(callsTo(fetchMock, "GET /orgs")).toHaveLength(2);
    expect(assign).not.toHaveBeenCalled();
  });

  it("renews once for several requests refused at the same time", async () => {
    setToken("old");
    const fetchMock = mockApi({
      "GET /orgs": (init) =>
        (init.headers as Record<string, string>).Authorization === "Bearer new" ? [] : json({ detail: {} }, 401),
      "POST /auth/refresh": () => ({ access_token: "new", ...TOKEN }),
    });

    await Promise.all([api.get("/orgs"), api.get("/orgs"), api.get("/orgs")]);

    expect(callsTo(fetchMock, "POST /auth/refresh")).toHaveLength(1);
  });

  it.each(["/auth/me?v=3", "/auth/sessions", "/auth/change-password"])("renews protected account request %s", async (path) => {
    setToken("old");
    const fetchMock = mockApi({
      [`GET ${path}`]: init => (init.headers as Record<string, string>).Authorization === "Bearer new"
        ? { ok: true } : json({ detail: "Expired token" }, 401),
      "POST /auth/refresh": () => ({ access_token: "new", ...TOKEN }),
    });
    await expect(api.get(path)).resolves.toEqual({ ok: true });
    expect(callsTo(fetchMock, "POST /auth/refresh")).toHaveLength(1);
    expect(callsTo(fetchMock, `GET ${path}`)).toHaveLength(2);
  });

  it.each(["/auth/login?source=test", "/auth/register", "/auth/refresh", "/auth/logout"])("does not renew session endpoint %s", async path => {
    setToken("old");
    const fetchMock = mockApi({ [`POST ${path}`]: () => json({ detail: "Refused" }, 401) });
    await expect(api.post(path)).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getToken()).toBe("old");
  });

  it("signs out on repeated protected account refusal without a retry loop", async () => {
    setToken("old");
    const onSessionEnded = vi.fn();
    setSessionHandlers({ onSessionEnded, onPasswordChangeRequired: vi.fn() });
    const fetchMock = mockApi({
      "GET /auth/me": () => json({ detail: "Session ended" }, 401),
      "POST /auth/refresh": () => ({ access_token: "new", ...TOKEN }),
    });
    await expect(api.get("/auth/me")).rejects.toMatchObject({ status: 401 });
    expect(callsTo(fetchMock, "GET /auth/me")).toHaveLength(2);
    expect(callsTo(fetchMock, "POST /auth/refresh")).toHaveLength(1);
    expect(onSessionEnded).toHaveBeenCalledTimes(1);
    expect(getToken()).toBeNull();
  });

  it("an ended session signs the app out, saying why", async () => {
    setToken("old");
    const onSessionEnded = vi.fn();
    setSessionHandlers({ onSessionEnded, onPasswordChangeRequired: vi.fn() });
    const idle = { code: "session_ended", message: "You were signed out after a period of inactivity." };
    mockApi({ "GET /orgs": () => json({ detail: idle }, 401) });

    await expect(api.get("/orgs")).rejects.toMatchObject({ status: 401, message: idle.message });
    expect(getToken()).toBeNull();
    expect(onSessionEnded).toHaveBeenCalledWith(idle.message);
  });

  it.each([
    ["is restarting (502)", () => json({ detail: "Bad gateway" }, 502)],
    ["can't be reached", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("doesn't sign out when the server %s while renewing", async (_, refresh) => {
    setToken("old");
    const onSessionEnded = vi.fn();
    setSessionHandlers({ onSessionEnded, onPasswordChangeRequired: vi.fn() });
    mockApi({ "GET /orgs": () => json({ detail: {} }, 401), "POST /auth/refresh": refresh });

    await expect(api.get("/orgs")).rejects.toThrow("Cannot reach the AuditMind API");
    expect(onSessionEnded).not.toHaveBeenCalled();
    expect(getToken()).toBe("old");
  });

  it("without the app's handlers, an ended session goes to /login", async () => {
    setToken("expired");
    mockApi({ "GET /orgs": () => json({ detail: "Could not validate credentials" }, 401) });

    await expect(api.get("/orgs")).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("does not renew or redirect on a 401 from sign-in itself (a wrong password)", async () => {
    setToken("tok");
    const fetchMock = mockApi({ "POST /auth/login": () => json({ detail: "Invalid email or password" }, 401) });

    await expect(api.post("/auth/login", {})).rejects.toThrow("Invalid email or password");
    expect(callsTo(fetchMock, "POST /auth/refresh")).toHaveLength(0);
    expect(assign).not.toHaveBeenCalled();
  });

  it("a required password change is passed to the app", async () => {
    setToken("tok");
    const onPasswordChangeRequired = vi.fn();
    setSessionHandlers({ onSessionEnded: vi.fn(), onPasswordChangeRequired });
    mockApi({
      "GET /orgs": () =>
        json({ detail: { code: "password_change_required", message: "Change your password to continue." } }, 403),
    });

    await expect(api.get("/orgs")).rejects.toMatchObject({ status: 403 });
    expect(onPasswordChangeRequired).toHaveBeenCalled();
  });

  it("refreshAccessToken gives null when there's no session", async () => {
    mockApi({});
    await expect(refreshAccessToken()).resolves.toBeNull();
  });

  it("turns FastAPI validation errors into a readable message", async () => {
    mockApi({
      "PATCH /orgs/o/settings": () =>
        json({ detail: [{ loc: ["body", "asset_existing_strategy"], msg: "Input should be 'update'" }] }, 422),
    });

    await expect(api.patch("/orgs/o/settings", {})).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "asset_existing_strategy: Input should be 'update'",
    });
  });

  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(api.get("/orgs")).rejects.toThrow("Cannot reach the AuditMind API");
  });
});
