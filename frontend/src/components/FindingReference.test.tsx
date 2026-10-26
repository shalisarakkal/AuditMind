import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FindingReference, { findingHref } from "./FindingReference";

describe("Finding references", () => {
  afterEach(() => vi.useRealTimers());
  it("hides success after three seconds and restarts the timer on another successful copy", async () => {
    vi.useFakeTimers();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
    render(<FindingReference orgId="org-1" id="finding-1" copy />);
    await act(async () => { fireEvent.click(screen.getByRole("button")); });
    act(() => vi.advanceTimersByTime(2999));
    expect(screen.getByRole("status")).toHaveTextContent("Finding ID copied.");
    await act(async () => { fireEvent.click(screen.getByRole("button")); });
    act(() => vi.advanceTimersByTime(2999));
    expect(screen.getByRole("status")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it("keeps copy errors visible and cancels an earlier success timeout", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<FindingReference orgId="org-1" id="finding-1" copy />);
    await act(async () => { fireEvent.click(screen.getByRole("button")); });
    act(() => vi.advanceTimersByTime(1000));
    await act(async () => { fireEvent.click(screen.getByRole("button")); });
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.getByRole("status")).toHaveTextContent("Could not copy.");
  });
  it("cleans up its success timer when removed", async () => {
    vi.useFakeTimers();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
    const view = render(<FindingReference orgId="org-1" id="finding-1" copy />);
    await act(async () => { fireEvent.click(screen.getByRole("button")); });
    expect(vi.getTimerCount()).toBe(1);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("encodes organization-scoped finding links and copies the exact identifier", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<FindingReference orgId="org-1" id="finding-1" copy />);
    expect(screen.getByRole("link")).toHaveAttribute("href", findingHref("org-1", "finding-1"));
    fireEvent.click(screen.getByRole("button", { name: "Copy finding ID finding-1" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Finding ID copied.");
    expect(writeText).toHaveBeenCalledWith("finding-1");
  });
  it("reports clipboard refusal without claiming a copy succeeded", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    render(<FindingReference orgId="org-1" id="finding-1" copy />);
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("status")).toHaveTextContent("Could not copy.");
  });
});
