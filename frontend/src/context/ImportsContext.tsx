"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import type { ImportResult } from "@/components/ImportReportPanel";
import { useApp } from "@/context/AppContext";
import { api } from "@/lib/apiClient";
import type { ImportReport, Scan } from "@/lib/types";

const POLL_MS = 2000;
const ORIGIN_KEY = "auditmind_import_pages";

export type ImportPage = "assets" | "findings";

type ImportsContextValue = {
  /** The selected org's running imports (anyone's), and the user's finished
   * imports whose report they haven't dismissed. */
  scans: Scan[];
  /** Goes up each time an import finishes, so pages can reload their lists. */
  finishedCount: number;
  /** Start following an import just uploaded from `page`. Never throws: if
   * the import can't be fetched yet, polling picks it up. */
  track(scanId: string, page: ImportPage): Promise<void>;
  /** Hide a finished import's report for good. */
  dismiss(scanId: string): Promise<void>;
};

const ImportsContext = createContext<ImportsContextValue | null>(null);

/** Follows the selected org's imports for the whole signed-in app, so an
 * import's progress and report survive moving between pages. The server
 * keeps the list (GET /scans?tracked=true), so a refresh brings it back.
 *
 * While imports run it polls the light ?active=true list, one request at a
 * time, and fetches the full list (with reports) only when an import starts
 * or finishes. Responses are applied in the order their requests were made:
 * one that arrives after a newer one has been applied is dropped. */
export function ImportsProvider({ children, pollIntervalMs = POLL_MS }: { children: React.ReactNode; pollIntervalMs?: number }) {
  const { selectedOrg } = useApp();
  const orgId = selectedOrg?.id ?? null;
  const [scans, setScans] = useState<Scan[]>([]);
  const [awaiting, setAwaiting] = useState<string[]>([]);
  const [finishedCount, setFinishedCount] = useState(0);
  // Latest state for async callbacks, plus request ordering: `requested`
  // numbers each request, `applied` is the newest one applied.
  const current = useRef({ orgId, scans, awaiting, requested: 0, applied: 0, dismissed: new Set<string>() });

  const begin = () => ++current.current.requested;

  /** Adopt `next` as the list, if it's for the selected org and no newer
   * response has been applied; count the imports that finished meanwhile. */
  const apply = useCallback((forOrg: string, request: number, next: Scan[]) => {
    const now = current.current;
    if (now.orgId !== forOrg || request < now.applied) return;
    next = next.filter((s) => !now.dismissed.has(s.id));
    const wasRunning = now.scans.filter(isRunning).map((s) => s.id);
    const finished =
      wasRunning.filter((id) => !next.some((s) => s.id === id && isRunning(s))).length +
      // An awaited upload first seen finished (e.g. a small file).
      now.awaiting.filter((id) => next.some((s) => s.id === id && !isRunning(s))).length;
    const stillAwaiting = now.awaiting.filter((id) => !next.some((s) => s.id === id));
    current.current = { ...now, scans: next, awaiting: stillAwaiting, applied: request };
    setScans(next);
    setAwaiting(stillAwaiting);
    if (finished) setFinishedCount((count) => count + finished);
  }, []);

  const loadAll = useCallback(async () => {
    if (!orgId) return;
    const request = begin();
    try {
      apply(orgId, request, await api.get<Scan[]>(`/orgs/${orgId}/scans?tracked=true`));
    } catch {
      // Keep what we have; the next poll tries again.
    }
  }, [orgId, apply]);

  const pollOnce = useCallback(async () => {
    if (!orgId) return;
    const request = begin();
    try {
      const active = await api.get<Scan[]>(`/orgs/${orgId}/scans?active=true`);
      const { scans: known, awaiting: waiting } = current.current;
      const running = known.filter(isRunning).map((s) => s.id).sort();
      const activeIds = active.map((s) => s.id).sort();
      const changed = running.join() !== activeIds.join() || waiting.length > 0;
      if (changed) {
        // An import started or finished: fetch the reports too.
        const tracked = await api.get<Scan[]>(`/orgs/${orgId}/scans?tracked=true`);
        apply(orgId, request, tracked);
      } else {
        const byId = new Map(active.map((s) => [s.id, s]));
        apply(orgId, request, known.map((s) => byId.get(s.id) ?? s));
      }
    } catch {
      // Try again on the next tick.
    }
  }, [orgId, apply]);

  useEffect(() => {
    current.current = { ...current.current, orgId, scans: [], awaiting: [] };
    setScans([]);
    setAwaiting([]);
    void loadAll();
  }, [orgId, loadAll]);

  // One poll at a time: the next is scheduled when the previous is done.
  const shouldPoll = scans.some(isRunning) || awaiting.length > 0;
  useEffect(() => {
    if (!shouldPoll) return;
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      await pollOnce();
      if (!stopped) timer = window.setTimeout(tick, pollIntervalMs);
    };
    timer = window.setTimeout(tick, pollIntervalMs);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [shouldPoll, pollOnce, pollIntervalMs]);

  const track = useCallback(
    async (scanId: string, page: ImportPage) => {
      if (!orgId) return;
      rememberOrigin(scanId, page);
      const waiting = [...current.current.awaiting.filter((id) => id !== scanId), scanId];
      current.current = { ...current.current, awaiting: waiting };
      setAwaiting(waiting);
      const request = begin();
      try {
        const scan = await api.get<Scan>(`/orgs/${orgId}/scans/${scanId}`);
        apply(orgId, request, [scan, ...current.current.scans.filter((s) => s.id !== scanId)]);
      } catch {
        // Still awaited: polling finds it in the org's list.
      }
    },
    [orgId, apply],
  );

  const dismiss = useCallback(
    async (scanId: string) => {
      if (!orgId) return;
      const request = begin();
      await api.post<Scan>(`/orgs/${orgId}/scans/${scanId}/dismiss`);
      current.current.dismissed.add(scanId);
      apply(
        orgId,
        request,
        current.current.scans.filter((s) => s.id !== scanId),
      );
    },
    [orgId, apply],
  );

  const value = useMemo(() => ({ scans, finishedCount, track, dismiss }), [scans, finishedCount, track, dismiss]);
  return <ImportsContext.Provider value={value}>{children}</ImportsContext.Provider>;
}

export function useImports(): ImportsContextValue {
  const ctx = useContext(ImportsContext);
  if (!ctx) throw new Error("useImports must be used inside <ImportsProvider>");
  return ctx;
}

export function isRunning(scan: Scan): boolean {
  return scan.status === "pending" || scan.status === "running";
}

const FINDINGS_SCAN_TYPES = new Set(["findings_csv", "findings_json", "nessus"]);

/** The pages an import's progress and report show on: a tool export (an
 * import profile) records assets and findings, so it shows on both. */
export function importPages(scan: Scan): ImportPage[] {
  if (scan.scan_type === "asset_import") return ["assets"];
  if (FINDINGS_SCAN_TYPES.has(scan.scan_type)) return ["findings"];
  return ["assets", "findings"];
}

/** The page to link an import to: the one it was started from in this tab,
 * if known, else the first page it affects. */
export function importHome(scan: Scan): ImportPage {
  const origin = readOrigins()[scan.id];
  return origin && importPages(scan).includes(origin) ? origin : importPages(scan)[0];
}

// Where each import was started, per browser tab (sessionStorage), so the
// sidebar can link back to it after navigation or a refresh.
function readOrigins(): Record<string, ImportPage> {
  try {
    return JSON.parse(window.sessionStorage.getItem(ORIGIN_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function rememberOrigin(scanId: string, page: ImportPage) {
  try {
    window.sessionStorage.setItem(ORIGIN_KEY, JSON.stringify({ ...readOrigins(), [scanId]: page }));
  } catch {
    // Storage unavailable: links fall back to the first page.
  }
}

/** Where a running import is, e.g. "Writing rows: 120,000 / 500,000 (24%)". */
export function progressText(scan: Scan): string {
  const progress = scan.progress;
  if (scan.status === "pending") return "Waiting to start…";
  switch (progress?.phase) {
    case "waiting":
      return "Waiting for another import into this organization to finish…";
    case "writing":
      return counted("Writing rows", progress.rows_done, progress.rows_total) ?? "Writing rows…";
    case "findings":
      return counted("Writing findings", progress.rows_done, progress.rows_total) ?? "Writing findings…";
    case "saving":
      return "Saving…";
    default:
      return counted("Reading file", progress?.rows_done, progress?.rows_total, " rows") ?? "Reading file…";
  }
}

function counted(label: string, done = 0, total = 0, unit = ""): string | null {
  if (!total) return null;
  const percent = Math.floor((done * 100) / total);
  return `${label}: ${done.toLocaleString("en-US")} / ${total.toLocaleString("en-US")}${unit} (${percent}%)`;
}

/** A finished import's report, as ImportReportPanel shows it. */
export function scanResult(scan: Scan): ImportResult {
  const { error, ...report } = scan.summary ?? {};
  return {
    status: scan.status,
    report: error || !scan.summary ? null : (report as ImportReport),
    error,
    filename: scan.filename ?? "Import",
  };
}
