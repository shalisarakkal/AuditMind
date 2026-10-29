import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuthGuard from "@/components/AuthGuard";
import { AppProvider } from "@/context/AppContext";
import { setToken } from "@/lib/apiClient";
import { json, mockApi, org } from "@/test/helpers";

const replace = vi.fn();
let pathname = "/";
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => pathname }));

describe("AuthGuard", () => {
  beforeEach(() => {
    replace.mockReset();
    pathname = "/";
  });

  it("redirects signed-out visitors to /login without rendering the page", async () => {
    mockApi({});
    render(
      <AppProvider>
        <AuthGuard>
          <p>secret dashboard</p>
        </AuthGuard>
      </AppProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret dashboard")).not.toBeInTheDocument();
  });

  it("shows generic progress during session recovery without exposing protected content", async () => {
    let finish!: (value: Response) => void;
    mockApi({ "POST /auth/refresh": () => new Promise<Response>(resolve => { finish = resolve; }) });
    render(<AppProvider><AuthGuard><p>secret dashboard</p></AuthGuard></AppProvider>);
    expect(screen.getByRole("status")).toHaveTextContent("Opening AuditMind");
    expect(screen.queryByText("secret dashboard")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
    await act(async () => { finish(json({ detail: "No session" }, 401)); });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("renders the page for a signed-in user", async () => {
    setToken("tok");
    mockApi({ "GET /orgs": () => [org()] });
    render(
      <AppProvider>
        <AuthGuard>
          <p>secret dashboard</p>
        </AuthGuard>
      </AppProvider>,
    );

    expect(await screen.findByText("secret dashboard")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("sends a user who must change their password to Change password, and nowhere else", async () => {
    mockApi({
      "POST /auth/refresh": () => ({ access_token: "tok", token_type: "bearer", expires_in: 900, must_change_password: true }),
    });
    render(
      <AppProvider>
        <AuthGuard>
          <p>secret dashboard</p>
        </AuthGuard>
      </AppProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/change-password"));
    expect(screen.queryByText("secret dashboard")).not.toBeInTheDocument();
  });

  it("renders the Change password page itself for such a user", async () => {
    pathname = "/change-password";
    mockApi({
      "POST /auth/refresh": () => ({ access_token: "tok", token_type: "bearer", expires_in: 900, must_change_password: true }),
    });
    render(
      <AppProvider>
        <AuthGuard>
          <p>change password form</p>
        </AuthGuard>
      </AppProvider>,
    );

    expect(await screen.findByText("change password form")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
