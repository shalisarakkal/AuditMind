import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuthGuard from "@/components/AuthGuard";
import { AppProvider } from "@/context/AppContext";
import { mockApi, org } from "@/test/helpers";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

describe("AuthGuard", () => {
  beforeEach(() => replace.mockReset());

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

  it("renders the page for a signed-in user", async () => {
    window.localStorage.setItem("auditmind_token", "tok");
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
});
