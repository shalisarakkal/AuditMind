"use client";

import { useEffect, useRef, useState } from "react";

import type { ImportResult } from "@/components/ImportReportPanel";
import { api } from "@/lib/apiClient";
import type { ImportReport, ImportResponse, Scan } from "@/lib/types";

type ImportButtonProps = {
  orgId: string;
  /** "assets" or "findings": posts to /orgs/{orgId}/{kind}/import. */
  kind: "assets" | "findings";
  accept: string;
  label: string;
  onComplete(result: ImportResult): void;
  pollIntervalMs?: number;
};

/** Uploads a file. Small files come back with their report at once; large ones
 * are imported in the background, so the scan is polled until it finishes. */
export default function ImportButton({ orgId, kind, accept, label, onComplete, pollIntervalMs = 1500 }: ImportButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<"idle" | "uploading" | "processing">("idle");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function waitForScan(scanId: string): Promise<Scan> {
    while (mounted.current) {
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      const scan = await api.get<Scan>(`/orgs/${orgId}/scans/${scanId}`);
      if (scan.status === "completed" || scan.status === "failed") return scan;
    }
    throw new Error("cancelled");
  }

  async function handleFile(file: File) {
    setPhase("uploading");
    try {
      const response = await api.upload<ImportResponse>(`/orgs/${orgId}/${kind}/import`, file);
      if (response.report) {
        onComplete({ status: response.status, report: response.report, filename: file.name });
        return;
      }
      setPhase("processing");
      const scan = await waitForScan(response.scan_id);
      const { error, ...report } = scan.summary ?? {};
      onComplete({
        status: scan.status,
        report: error ? null : (report as ImportReport),
        error,
        filename: file.name,
      });
    } catch (err) {
      if (mounted.current) onComplete({ status: "failed", report: null, error: (err as Error).message, filename: file.name });
    } finally {
      if (mounted.current) setPhase("idle");
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const busy = phase !== "idle";
  return (
    <div className="flex items-center gap-3">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        data-testid={`${kind}-file-input`}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className="rounded-md bg-cyan px-4 py-2 text-sm font-medium text-navy transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {label}
      </button>
      {phase === "uploading" && <span className="text-sm text-white/60">Uploading…</span>}
      {phase === "processing" && (
        <span className="text-sm text-white/60">Large file — importing in the background…</span>
      )}
    </div>
  );
}
