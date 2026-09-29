"use client";

import { useState } from "react";

import ImportReportPanel from "@/components/ImportReportPanel";
import { importPages, isRunning, progressText, scanResult, useImports } from "@/context/ImportsContext";

/** A page's imports: progress while they run, then the report (for the
 * uploader) until it's dismissed. */
export default function ImportStatus({ page }: { page: "assets" | "findings" }) {
  const { scans, dismiss } = useImports();
  const [error, setError] = useState<string | null>(null);
  const mine = scans.filter((s) => importPages(s).includes(page));
  if (mine.length === 0) return null;

  return (
    <div className="space-y-3">
      {mine.filter(isRunning).map((scan) => (
        <section
          key={scan.id}
          aria-label={`Importing ${scan.filename ?? "a file"}`}
          className="rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm"
        >
          <p className="text-white">
            <span className="font-medium">{scan.filename ?? "Import"}</span>{" "}
            <span className="text-white/60">— importing in the background</span>
          </p>
          <p className="mt-1 text-cyan">{progressText(scan)}</p>
        </section>
      ))}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          Couldn&apos;t dismiss the report: {error}
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
              dismiss(scan.id).catch((err: Error) => setError(err.message));
            }}
          />
        ))}
    </div>
  );
}
