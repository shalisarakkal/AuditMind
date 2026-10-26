import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import BulkConfirm from "./BulkConfirm";
import type { Selection } from "@/lib/useSelection";

const mocks = vi.hoisted(() => ({ startBulk: vi.fn() }));
vi.mock("@/context/ImportsContext", () => ({ useImports: () => mocks }));
beforeEach(() => mocks.startBulk.mockReset());

it("submits the original targets even when the parent selection changes", async () => {
  mocks.startBulk.mockResolvedValue({ jobs: [], refused: [] });
  const clear = vi.fn(), close = vi.fn();
  const selection = (ids: string[]): Selection => ({ ids, count: ids.length,
    names: picked => picked, clear, metadata: () => undefined,
    has: id => ids.includes(id), full: false, maximum: 500, set: vi.fn() });
  const request = { action: "restore" as const, label: "Restore selected", message: "Restore original target?", confirmLabel: "Restore" };
  const view = render(<BulkConfirm request={request} selection={selection(["original"])} onClose={close} />);
  view.rerender(<BulkConfirm request={request} selection={selection(["different"])} onClose={close} />);
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(mocks.startBulk).toHaveBeenCalledWith("restore", ["original"], undefined);
  expect(clear).toHaveBeenCalledOnce();
});
