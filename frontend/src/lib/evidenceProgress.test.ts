import { expect, it, vi } from "vitest";
import { api } from "./apiClient";
import { evidenceOperation } from "./evidenceProgress";

it("parses progress across network chunk boundaries without accepting partial results", async () => {
  const encoder = new TextEncoder();
  vi.spyOn(api, "stream").mockResolvedValue(new Response(new ReadableStream({ start(controller) {
    for (const part of ['{"type":"pro', 'gress","phase":"assets","processed":5}\n{"type":"result",', '"data":{"ok":true}}\n']) controller.enqueue(encoder.encode(part));
    controller.close();
  } })));
  const progress = vi.fn();
  expect(await evidenceOperation("/test", new AbortController().signal, progress)).toEqual({ ok: true });
  expect(progress).toHaveBeenCalledWith({ type: "progress", phase: "assets", processed: 5 });
});
it.each([
  ['{"type":"progress","phase":"assets"}\n', "before completion"],
  ['{"type":"error","message":"Scan failed"}\n', "Scan failed"],
  ['not json\n', "JSON"],
])("rejects incomplete or failed streams", async (body, message) => {
  vi.spyOn(api, "stream").mockResolvedValue(new Response(body));
  await expect(evidenceOperation("/test", new AbortController().signal, vi.fn())).rejects.toThrow(message);
});

it("passes cancellation through and does not return a partial result", async () => {
  const controller = new AbortController();
  vi.spyOn(api, "stream").mockImplementation(async (_, signal) => new Response(new ReadableStream({
    start(stream) {
      stream.enqueue(new TextEncoder().encode('{"type":"progress","phase":"assets","processed":5}\n'));
      signal?.addEventListener("abort", () => stream.error(new DOMException("Cancelled", "AbortError")));
    },
  })));
  const update = vi.fn(() => controller.abort());
  await expect(evidenceOperation("/test", controller.signal, update)).rejects.toThrow("Cancelled");
  expect(update).toHaveBeenCalledOnce();
});
