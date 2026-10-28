import { api } from "./apiClient";

export type EvidenceProgress = { phase: string; processed?: number; total?: number | null; elapsed_seconds?: number };

export async function evidenceOperation<T>(path: string, signal: AbortSignal, progress: (value: EvidenceProgress) => void): Promise<T> {
  const response = await api.stream(path, signal);
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Progress stream is unavailable. Please retry.");
  const decoder = new TextDecoder();
  let pending = "";
  let complete = false;
  let result: T | undefined;
  function consume(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "error") throw new Error(event.message);
    if (event.type === "progress") progress(event);
    if (event.type === "result") { result = event.data; complete = true; }
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split("\n"); pending = lines.pop() ?? "";
      for (const line of lines) consume(line);
      if (done) { consume(pending); break; }
    }
    if (!complete) throw new Error("The evidence connection ended before completion. Please retry.");
    return result as T;
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
