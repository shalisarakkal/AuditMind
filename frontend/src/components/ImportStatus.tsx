"use client";

import { useState } from "react";

import ImportReportPanel from "@/components/ImportReportPanel";
import { importPages, isInterrupted, isRunning, progressText, scanResult, useImports } from "@/context/ImportsContext";

/** A page's imports: progress while they run, then the report (for the
 * uploader) until it's dismissed. */
export default function ImportStatus({ page }: { page: "assets" | "findings" }) {
  const { scans, dismiss, retry, workerDown } = useImports();
  const [error, setError] = useState<string | null>(null);
  const mine = scans.filter((s) => importPages(s).includes(page));
  if (mine.length === 0) return null;
  const running = mine.filter(isRunning);
  const needsAttention = mine.some(scan => isInterrupted(scan, workerDown) || scan.status === "failed" || (scanResult(scan).report?.failed ?? 0) > 0);

  return (
    <details key={needsAttention ? "attention" : "normal"} open={needsAttention || undefined} className="group rounded-xl border border-white/15 bg-white/5 text-sm">
      <summary className="cursor-pointer px-4 py-3 text-white">
        <span className="font-medium">{running.length ? `${running.length} import${running.length === 1 ? "" : "s"} processing` : `${mine.length} import report${mine.length === 1 ? "" : "s"} available`}</span>
        {needsAttention && <span className="ml-3 text-amber-200">Attention required</span>}
        <span className="ml-3 text-cyan group-open:hidden">{running.length ? "Show progress and reports" : "Show reports"}</span>
        <span className="ml-3 hidden text-cyan group-open:inline">{running.length ? "Hide progress and reports" : "Hide reports"}</span>
      </summary>
    <div className="space-y-3 border-t border-white/10 p-3">
      {mine.filter(isRunning).map((scan) => {
        const interrupted = isInterrupted(scan, workerDown);
        return (
          <section
            key={scan.id}
            aria-label={`Processing ${scan.filename ?? "a file"}`}
            className={interrupted ? "rounded-xl border border-violet-400/40 bg-violet-400/10 p-4 text-sm" : "rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm"}
          >
            <p className="text-white">
              <span className="font-medium">{scan.filename ?? "Upload"}</span>{" "}
              <span className="text-white/60">— processing in the background</span>
            </p>
            <p className={`mt-1 ${interrupted ? "text-violet-200" : "text-cyan"}`}>
              {interrupted && <span aria-hidden className="mr-1">⚠</span>}
              {progressText(scan, workerDown)}
            </p>
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
