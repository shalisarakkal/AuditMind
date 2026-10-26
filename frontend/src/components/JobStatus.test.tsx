import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import JobStatus from "./JobStatus";
import type { ArchiveJob } from "@/lib/types";

const state = vi.hoisted(() => ({ jobs: [] as ArchiveJob[], dismissJob: vi.fn() }));
vi.mock("@/context/ImportsContext", async importOriginal => ({ ...await importOriginal<object>(), useImports: () => ({ jobs: state.jobs, dismissJob: state.dismissJob, workerDown: false }) }));
const job = (id = "j1", overrides: Partial<ArchiveJob> = {}): ArchiveJob => ({ id, org_id: "org", batch_id: "b", action: "archive", status: "completed", item_type: "upload", item_id: "s", label: `${id}.csv`, started_by: "u", started_at: "2026-10-24T00:00:00Z", completed_at: "2026-10-24T00:00:01Z", dismissed_at: null, progress: null, summary: { uploads: 1 }, ...overrides });
let intersect: (visible: boolean) => void;
beforeEach(() => {
  vi.useFakeTimers(); state.jobs = [job()]; state.dismissJob.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: (entries: {isIntersecting: boolean}[]) => void) { intersect = visible => callback([{isIntersecting: visible}]); }
    observe() {} disconnect() {}
  });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
const tick = async (ms: number) => { await act(async () => { vi.advanceTimersByTime(ms); }); };
const visible = (value = true) => act(() => intersect(value));

describe("Job-result auto dismissal", () => {
  it("dismisses routine success once after ten visible seconds, not before", async () => {
    const view = render(<JobStatus />); visible();
    await tick(9999); expect(state.dismissJob).not.toHaveBeenCalled();
    view.rerender(<JobStatus />); await tick(1);
    expect(state.dismissJob).toHaveBeenCalledExactlyOnceWith("j1", true);
    await tick(20000); expect(state.dismissJob).toHaveBeenCalledTimes(1);
  });
  it("pauses for hover, keyboard focus, hidden tabs and offscreen notices", async () => {
    render(<JobStatus />); visible(); await tick(2000);
    const notice = screen.getByRole("region"), button = screen.getByRole("button", { name: "Dismiss" });
    fireEvent.mouseEnter(notice); await tick(20000); fireEvent.mouseLeave(notice);
    fireEvent.focusIn(button); await tick(20000); fireEvent.focusOut(button, { relatedTarget: document.body });
    visible(false); await tick(20000); visible();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    fireEvent(document, new Event("visibilitychange")); await tick(20000);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    fireEvent(document, new Event("visibilitychange"));
    await tick(7999); expect(state.dismissJob).not.toHaveBeenCalled();
    await tick(1); expect(state.dismissJob).toHaveBeenCalledExactlyOnceWith("j1", true);
  });
  it.each(["failed", "pending", "running"] as const)("never auto-dismisses %s jobs", async status => {
    state.jobs = [job("j1", { status })]; render(<JobStatus />);
    await tick(30000); expect(state.dismissJob).not.toHaveBeenCalled();
  });
  it.each([{ findings_kept_with_asset: 2 }, { duplicates_purged: 2 }])("keeps warning outcomes visible: %j", async summary => {
    state.jobs = [job("j1", { action: "restore", summary })];
    render(<JobStatus />); visible(); await tick(30000);
    expect(state.dismissJob).not.toHaveBeenCalled();
  });
  it("keeps dismissal errors visible and does not retry automatically", async () => {
    state.dismissJob.mockRejectedValue(new Error("Unavailable"));
    render(<JobStatus />); visible(); await tick(10000);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't dismiss: Unavailable");
    await tick(30000); expect(state.dismissJob).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" })); await tick(0);
    expect(state.dismissJob).toHaveBeenCalledTimes(2);
  });
  it("dismisses an all-success group, but preserves mixed failed groups", async () => {
    state.jobs = [job("1"), job("2"), job("3"), job("4")];
    const view = render(<JobStatus />); visible(); await tick(10000);
    expect(state.dismissJob).toHaveBeenCalledTimes(4);
    state.dismissJob.mockClear(); state.jobs = [...state.jobs, job("5", { status: "failed", summary: { error: "Stopped" } })];
    view.rerender(<JobStatus />); await tick(30000); expect(state.dismissJob).not.toHaveBeenCalled();
  });
  it("cleans up on unmount and fails safe without visibility observation", async () => {
    const view = render(<JobStatus />); visible(); await tick(5000); view.unmount();
    await tick(20000); expect(state.dismissJob).not.toHaveBeenCalled();
    vi.stubGlobal("IntersectionObserver", undefined); render(<JobStatus />);
    await tick(20000); expect(state.dismissJob).not.toHaveBeenCalled();
  });
});
