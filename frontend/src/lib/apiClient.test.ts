import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, getToken, setToken } from "@/lib/apiClient";
import { json, mockApi, requestInit } from "@/test/helpers";

describe("apiClient", () => {
  const assign = vi.fn();

  beforeEach(() => {
    assign.mockReset();
    vi.stubGlobal("location", { ...window.location, assign });
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

  it("drops an expired session and sends the user to /login", async () => {
    setToken("expired");
    mockApi({ "GET /orgs": () => json({ detail: "Could not validate credentials" }, 401) });

    await expect(api.get("/orgs")).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("does not redirect on a 401 without a session (e.g. a wrong password)", async () => {
    mockApi({ "POST /auth/login": () => json({ detail: "Invalid email or password" }, 401) });

    await expect(api.post("/auth/login", {})).rejects.toThrow("Invalid email or password");
    expect(assign).not.toHaveBeenCalled();
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
