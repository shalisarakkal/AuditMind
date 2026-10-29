"use client";

import { useEffect, useState } from "react";

import ImportReportPanel from "@/components/ImportReportPanel";
import { importPages, importState, isInterrupted, isRunning, progressText, scanResult, useImports } from "@/context/ImportsContext";

function age(iso: string | null | undefined, now: number) {
  const stamp = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(stamp) ? Math.max(0, Math.floor((now - stamp) / 1000)) : null;
}
function duration(seconds: number) {
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}

/** A page's imports: progress while they run, then the report (for the
 * uploader) until it's dismissed. */
export default function ImportStatus({ page }: { page: "assets" | "findings" }) {
  const { scans, dismiss, retry, workerDown } = useImports();
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const mine = scans.filter((s) => importPages(s).includes(page));
  const ticking = expanded && mine.some(isRunning);
  useEffect(() => {
    if (!ticking) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [ticking]);
  if (mine.length === 0) return null;
  const running = mine.filter(isRunning);
  const counts = new Map<string, number>();
  for (const scan of mine) { const state = importState(scan, workerDown); counts.set(state, (counts.get(state) ?? 0) + 1); }
  const summary = counts.size === 1 && counts.has("completed") ? `${mine.length} import${mine.length === 1 ? "" : "s"} completed`
    : ["processing", "queued", "waiting", "interrupted", "failed", "completed"].filter(state => counts.has(state)).map(state => `${counts.get(state)} ${state}`).join(" · ");
  const needsAttention = mine.some(scan => isInterrupted(scan, workerDown) || scan.status === "failed" || (scanResult(scan).report?.failed ?? 0) > 0);

  return (
    <details key={needsAttention ? "attention" : "normal"} open={needsAttention || undefined} onToggle={event => setExpanded(event.currentTarget.open)} className="group rounded-xl border border-white/15 bg-white/5 text-sm">
      <summary className="cursor-pointer px-4 py-3 text-white">
        <span className="font-medium">{summary}</span>
        {needsAttention && <span className="ml-3 text-amber-200">Attention required</span>}
        <span className="ml-3 text-cyan group-open:hidden">{running.length ? "Show progress and reports" : "Show reports"}</span>
        <span className="ml-3 hidden text-cyan group-open:inline">{running.length ? "Hide progress and reports" : "Hide reports"}</span>
      </summary>
    <div className="space-y-3 border-t border-white/10 p-3">
      {mine.filter(isRunning).map((scan) => {
        const interrupted = isInterrupted(scan, workerDown);
        const state = importState(scan, workerDown);
        const active = state === "processing";
        const sinceUpdate = age(scan.progress?.updated_at, now);
        const sinceHeartbeat = age(scan.heartbeat_at, now);
        const elapsed = age(scan.started_at, now);
        const label = active ? "Processing" : state === "queued" ? "Queued" : state === "waiting" ? "Waiting" : "Interrupted";
        return (
          <section
            key={scan.id}
            aria-label={`${label} ${scan.filename ?? "a file"}`}
            className={interrupted ? "rounded-xl border border-violet-400/40 bg-violet-400/10 p-4 text-sm" : "rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm"}
          >
            <p className="text-white">
              <span className="font-medium">{scan.filename ?? "Upload"}</span>{" "}
              <span className="text-white/60">— {label.toLowerCase()}</span>
            </p>
            <p className={`mt-1 ${interrupted ? "text-violet-200" : "text-cyan"}`}>
              {active ? <span aria-hidden="true" className="mr-2 inline-block h-4 w-4 align-middle rounded-full border-2 border-cyan/30 border-t-cyan motion-safe:animate-spin" />
                : <span aria-hidden="true" className="mr-2">{interrupted ? "⚠" : "◷"}</span>}
              {progressText(scan, workerDown)}
            </p>
            <p className="mt-2 text-xs text-white/60">
              {elapsed !== null && <span>Since submitted: {duration(elapsed)}</span>}
              {active && sinceUpdate !== null && <span> · Progress updated {duration(sinceUpdate)} ago</span>}
            </p>
            {active && sinceUpdate !== null && sinceUpdate >= 10 && <p className="mt-1 text-xs text-white/60">
              Waiting for a progress update. {sinceHeartbeat !== null && sinceHeartbeat <= 30 ? "The worker is still checking in." : "Checking worker availability…"}
            </p>}
          </section>
        );
      })}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
      {mine
        .filter((s) => !isRunning(s))
        .map((scan) => (
          <ImportReportPanel
            key={scan.id}
            result={scanResult(scan)}
            onDismiss={() => {
              setError(null);
              dismiss(scan.id).catch((err: Error) => setError(`Couldn't dismiss the report: ${err.message}`));
            }}
            onRetry={
              scan.retryable
                ? () => {
                    setError(null);
                    retry(scan).catch((err: Error) => setError(`Couldn't retry ${scan.filename ?? "the upload"}: ${err.message}`));
                  }
                : undefined
            }
          />
        ))}
    </div>
    </details>
  );
}
