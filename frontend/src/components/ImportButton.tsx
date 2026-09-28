"use client";

import { useEffect, useRef, useState } from "react";

import type { ImportResult } from "@/components/ImportReportPanel";
import { api } from "@/lib/apiClient";
import {
  GENERIC_ASSETS,
  GENERIC_FINDINGS,
  fileExtension,
  importTarget,
  readColumns,
  suggestProfile,
} from "@/lib/importProfiles";
import type { ImportProfile, ImportReport, ImportResponse, Scan } from "@/lib/types";

type ImportButtonProps = {
  orgId: string;
  /** Which page it's on: sets the default source (the generic asset list or
   * generic findings). */
  kind: "assets" | "findings";
  accept: string;
  label: string;
  onComplete(result: ImportResult): void;
  /** Import profiles to choose from. Without them, a picked file is uploaded
   * straight away with the page's generic source. */
  profiles?: ImportProfile[] | null;
  pollIntervalMs?: number;
};

type Pending = { file: File; detected: string | null };

/** Uploads a file. With profiles, the user confirms the file's source first
 * (pre-selected when the file's columns match a profile). Small files come back
 * with their report at once; large ones are imported in the background, so the
 * scan is polled until it finishes. */
export default function ImportButton({
  orgId,
  kind,
  accept,
  label,
  onComplete,
  profiles,
  pollIntervalMs = 1500,
}: ImportButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<"idle" | "uploading" | "processing">("idle");
  const [pending, setPending] = useState<Pending | null>(null);
  const [source, setSource] = useState(kind === "assets" ? GENERIC_ASSETS : GENERIC_FINDINGS);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const pageDefault = kind === "assets" ? GENERIC_ASSETS : GENERIC_FINDINGS;

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

  async function upload(file: File, profileKey: string) {
    // A second click that lands before the re-render hides the confirm
    // button must not upload the file again.
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(null);
    setPhase("uploading");
    try {
      const { path, fields } = importTarget(orgId, profileKey);
      const response = await api.upload<ImportResponse>(path, file, fields);
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
      inFlight.current = false;
      if (mounted.current) setPhase("idle");
    }
  }

  async function handleFile(file: File) {
    if (inputRef.current) inputRef.current.value = "";
    if (!profiles?.length) {
      await upload(file, pageDefault);
      return;
    }
    if (fileExtension(file.name) === ".nessus") {
      setSource(GENERIC_FINDINGS);
      setPending({ file, detected: null });
      return;
    }
    const detected = suggestProfile(await readColumns(file), profiles);
    if (!mounted.current) return;
    setSource(detected?.key ?? pageDefault);
    setPending({ file, detected: detected?.key ?? null });
  }

  const busy = phase !== "idle";
  const nessus = pending !== null && fileExtension(pending.file.name) === ".nessus";
  const choices = nessus ? (profiles ?? []).filter((p) => p.key === GENERIC_FINDINGS) : sortedChoices(profiles ?? [], pageDefault);

  return (
    <div className="flex flex-col items-end gap-2">
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
        {phase === "uploading" && <span className="text-sm text-white/60">Uploading…</span>}
        {phase === "processing" && (
          <span className="text-sm text-white/60">Large file — importing in the background…</span>
        )}
        <button
          type="button"
          disabled={busy || pending !== null}
          onClick={() => inputRef.current?.click()}
          className="rounded-md bg-cyan px-4 py-2 text-sm font-medium text-navy transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {label}
        </button>
      </div>

      {pending && (
        <div
          role="group"
          aria-label="Import options"
          className="flex flex-wrap items-center justify-end gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm"
        >
          <span className="max-w-56 truncate font-medium text-white" title={pending.file.name}>
            {pending.file.name}
          </span>
          <label htmlFor={`${kind}-import-source`} className="text-white/60">
            Source
          </label>
          <select
            id={`${kind}-import-source`}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="max-w-64 rounded-md border border-white/15 bg-navy px-2 py-1 text-sm text-white focus:border-cyan focus:outline-none"
          >
            {choices.map((p) => (
              <option key={p.key} value={p.key}>
                {p.builtin ? p.name : `${p.name} (${p.family_label})`}
              </option>
            ))}
          </select>
          {pending.detected && source === pending.detected && (
            <span className="text-xs text-emerald-300">Detected from the file&apos;s columns</span>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => void upload(pending.file, source)}
            className="rounded-md bg-cyan px-3 py-1 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-60"
          >
            Import
          </button>
          <button type="button" onClick={() => setPending(null)} className="px-1 text-xs text-white/60 hover:text-white">
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

/** The page's generic source first, then the other built-ins, then the org's own. */
function sortedChoices(profiles: ImportProfile[], first: string): ImportProfile[] {
  const rank = (p: ImportProfile) => (p.key === first ? 0 : p.builtin ? 1 : 2);
  return [...profiles].sort((a, b) => rank(a) - rank(b));
}
