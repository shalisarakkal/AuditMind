import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockApi, json, callsTo } from "@/test/helpers";
import PlatformControlCatalog from "./PlatformControlCatalog";

describe("Platform catalog installation", () => {
  it("installs only after an explicit click and blocks duplicate submission", async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>(resolve => { finish = resolve; });
    const calls = mockApi({ "GET /platform/control-catalogs": () => ({ available: true, items: [] }), "POST /platform/control-catalogs/baseline": () => pending });
    render(<PlatformControlCatalog />);
    const button = screen.getByRole("button", { name: "Install verified NIST baseline" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(callsTo(calls, "POST /platform/control-catalogs/baseline")).toHaveLength(0);
    await userEvent.click(button);
    expect(screen.getByRole("button", { name: "Installing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reload catalog releases" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Leaving this page does not cancel");
    finish(json({}));
    await waitFor(() => expect(screen.getByRole("button", { name: "Install verified NIST baseline" })).toBeEnabled());
    expect(callsTo(calls, "POST /platform/control-catalogs/baseline")).toHaveLength(1);
  });
  it("does not call a refused request an unknown successful installation", async () => {
    mockApi({ "GET /platform/control-catalogs": () => ({ available: true, items: [] }), "POST /platform/control-catalogs/baseline": () => json({ detail: "Platform role changed" }, 403) });
    render(<PlatformControlCatalog />);
    const button = screen.getByRole("button", { name: "Install verified NIST baseline" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("may have finished");
    expect(alert).toHaveTextContent("Platform role changed");
  });
});
