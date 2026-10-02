"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import type { ImportResult } from "@/components/ImportReportPanel";
import { useApp } from "@/context/AppContext";
import { api } from "@/lib/apiClient";
import { countsText } from "@/lib/domain";
import type { ArchiveAction, ArchiveItemType, ArchiveJob, BulkResult, ImportReport, Scan, WorkerStatus } from "@/lib/types";

// The polling here is the app checking, not the person doing something: it
// mustn't keep an idle session signed in (apiClient's background requests).
const BACKGROUND = { background: true };

const POLL_MS = 2000;
const WORKER_CHECK_MS = 15000;
// How long a row's button says "Archived" (or "Restored", "Purged") after a
// small job, while its list reloads.
const DONE_MS = 60000;
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
  /** Run a failed large upload again from its kept file (scan.retryable): a
   * new upload, followed like one just made; the failed one's report goes.
   * Throws if the server refuses. */
  retry(scan: Scan): Promise<void>;
  /** Archive, restore and purge jobs, tracked the same way: the org's running
   * ones, and the user's finished ones not yet dismissed. */
  jobs: ArchiveJob[];
  /** POST `path` (an archive, restore or purge endpoint) and follow the job it
   * starts. Throws if the server refuses. */
  startJob(path: string): Promise<ArchiveJob>;
  dismissJob(jobId: string): Promise<void>;
  /** Archive (`itemType` items), restore or purge (archived entries) several
   * at once: a job each, queued for the background worker, followed like
   * the others. Throws if the server refuses the whole request. */
  startBulk(action: ArchiveAction, ids: string[], itemType?: ArchiveItemType): Promise<BulkResult>;
  /** Jobs this browser just asked for, by endpoint path: "starting" while
   * the request runs (small jobs run during it), then "done" for a short
   * while if it finished then, until the lists have reloaded. */
  requested: Record<string, "starting" | "done">;
  /** True while something waits for (or is run by) the background worker
   * and the worker hasn't checked in lately (it isn't running). */
  workerDown: boolean;
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
      const active = await api.get<Scan[]>(`/orgs/${orgId}/scans?active=true`, BACKGROUND);
      const { scans: known, awaiting: waiting } = current.current;
      const running = known.filter(isRunning).map((s) => s.id).sort();
      const activeIds = active.map((s) => s.id).sort();
      const changed = running.join() !== activeIds.join() || waiting.length > 0;
      if (changed) {
        // An import started or finished: fetch the reports too.
        const tracked = await api.get<Scan[]>(`/orgs/${orgId}/scans?tracked=true`, BACKGROUND);
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

  usePolling(scans.some(isRunning) || awaiting.length > 0, pollOnce, pollIntervalMs);

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

  const retry = useCallback(
    async (scan: Scan) => {
      if (!orgId) return;
      const { scan_id } = await api.post<{ scan_id: string }>(`/orgs/${orgId}/scans/${scan.id}/retry`);
      current.current.dismissed.add(scan.id);
      apply(orgId, begin(), current.current.scans.filter((s) => s.id !== scan.id));
      await track(scan_id, importHome(scan));
    },
    [orgId, apply, track],
  );

  const onJobsFinished = useCallback((count: number) => setFinishedCount((c) => c + count), []);
  const { jobs, startJob, startBulk, dismissJob, requested } = useArchiveJobs(orgId, pollIntervalMs, onJobsFinished);

  // Waiting for the worker, or being run by it (a job it was running when it
  // stopped stays "running" until it's back).
  const needsWorker = (item: Scan | ArchiveJob) => item.status === "pending" || runByWorker(item);
  const waiting = scans.some(needsWorker) || jobs.some(needsWorker);
  const workerDown = useWorkerDown(waiting, WORKER_CHECK_MS);

  const value = useMemo(
    () => ({ scans, finishedCount, track, dismiss, retry, jobs, startJob, startBulk, dismissJob, requested, workerDown }),
    [scans, finishedCount, track, dismiss, retry, jobs, startJob, startBulk, dismissJob, requested, workerDown],
  );
  return <ImportsContext.Provider value={value}>{children}</ImportsContext.Provider>;
}

/** The org's tracked archive jobs (GET /archive-jobs?tracked=true), polled
 * one request at a time while any runs; a response for another org, or older
 * than one already applied, is dropped. `onFinished` is told how many jobs
 * finished (including one that finished during its own request). */
function useArchiveJobs(orgId: string | null, pollIntervalMs: number, onFinished: (count: number) => void) {
  const [jobs, setJobs] = useState<ArchiveJob[]>([]);
  const [requested, setRequested] = useState<Record<string, "starting" | "done">>({});
  const current = useRef({ orgId, jobs, requested: 0, applied: 0 });

  const apply = useCallback(
    (forOrg: string, request: number, next: ArchiveJob[], alsoFinished = 0) => {
      const now = current.current;
      if (now.orgId !== forOrg || request < now.applied) return;
      const finished = now.jobs.filter((j) => isRunning(j) && !next.some((n) => n.id === j.id && isRunning(n))).length;
      current.current = { ...now, jobs: next, applied: request };
      setJobs(next);
      if (finished + alsoFinished) onFinished(finished + alsoFinished);
    },
    [onFinished],
  );

  const load = useCallback(async () => {
    if (!orgId) return;
    const request = ++current.current.requested;
    try {
      apply(orgId, request, await api.get<ArchiveJob[]>(`/orgs/${orgId}/archive-jobs?tracked=true`, BACKGROUND));
    } catch {
      // Keep what we have; the next poll tries again.
    }
  }, [orgId, apply]);

  useEffect(() => {
    current.current = { ...current.current, orgId, jobs: [] };
    setJobs([]);
    setRequested({});
    void load();
  }, [orgId, load]);

  usePolling(jobs.some(isRunning), load, pollIntervalMs);

  const startJob = useCallback(
    async (path: string) => {
      if (!orgId) throw new Error("No organization selected");
      const mark = (state: "starting" | "done" | null) =>
        setRequested((before) => {
          const next = { ...before };
          if (state) next[path] = state;
          else delete next[path];
          return next;
        });
      mark("starting");
      let job: ArchiveJob;
      try {
        job = await api.post<ArchiveJob>(path);
      } catch (err) {
        mark(null);
        throw err;
      }
      // A large job is followed from the jobs list; a small one is done, and
      // its row goes when the list reloads.
      if (isRunning(job)) mark(null);
      else {
        mark("done");
        setTimeout(() => mark(null), DONE_MS);
      }
      // Numbered once the answer is in, unlike the imports' track(): it's the
      // newest word on this job, and polling may not run to pick it up later
      // (nothing else running). Applied at once, so still in order.
      const request = ++current.current.requested;
      const others = current.current.jobs.filter((j) => j.id !== job.id);
      // Small jobs finish during the request: lists reload straight away.
      apply(orgId, request, [job, ...others], isRunning(job) ? 0 : 1);
      return job;
    },
    [orgId, apply],
  );

  const startBulk = useCallback(
    async (action: ArchiveAction, ids: string[], itemType?: ArchiveItemType) => {
      if (!orgId) throw new Error("No organization selected");
      const result = await api.post<BulkResult>(`/orgs/${orgId}/archive-jobs/bulk`, { action, item_type: itemType ?? null, ids });
      const request = ++current.current.requested;
      const started = new Set(result.jobs.map((j) => j.id));
      apply(orgId, request, [...result.jobs, ...current.current.jobs.filter((j) => !started.has(j.id))]);
      return result;
    },
    [orgId, apply],
  );

  const dismissJob = useCallback(
    async (jobId: string) => {
      if (!orgId) return;
      await api.post<ArchiveJob>(`/orgs/${orgId}/archive-jobs/${jobId}/dismiss`);
      const request = ++current.current.requested;
      apply(orgId, request, current.current.jobs.filter((j) => j.id !== jobId));
    },
    [orgId, apply],
  );

  return { jobs, startJob, startBulk, dismissJob, requested };
}

/** While `waiting` (something waits for the background worker): whether the
 * worker hasn't checked in lately (GET /worker-status, every `intervalMs`). */
function useWorkerDown(waiting: boolean, intervalMs: number): boolean {
  const [running, setRunning] = useState<boolean | null>(null);
  const check = useCallback(async () => {
    try {
      setRunning((await api.get<WorkerStatus>("/worker-status", BACKGROUND)).running);
    } catch {
      // Unknown: keep the last answer.
    }
  }, []);
  useEffect(() => {
    if (waiting) void check();
  }, [waiting, check]);
  usePolling(waiting, check, intervalMs);
  return waiting && running === false;
}

/** Call `poll` every `intervalMs` while `active`, one call at a time: the
 * next is scheduled when the previous is done. */
function usePolling(active: boolean, poll: () => Promise<void>, intervalMs: number) {
  useEffect(() => {
    if (!active) return;
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      await poll();
      if (!stopped) timer = window.setTimeout(tick, intervalMs);
    };
    timer = window.setTimeout(tick, intervalMs);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [active, poll, intervalMs]);
}

export function useImports(): ImportsContextValue {
  const ctx = useContext(ImportsContext);
  if (!ctx) throw new Error("useImports must be used inside <ImportsProvider>");
  return ctx;
}

export function isRunning(item: Scan | ArchiveJob): boolean {
  return item.status === "pending" || item.status === "running";
}

const JOB_VERBS = { archive: "Archiving", restore: "Restoring", purge: "Purging" } as const;
const JOB_DONE = { archive: "Archived", restore: "Restored", purge: "Purged" } as const;
const JOB_PHASES: Record<string, string> = { findings: "Findings", assets: "Assets", saving: "Saving" };

/** What a job is doing, e.g. "Archiving findings.csv". */
export function jobTitle(job: ArchiveJob): string {
  return `${JOB_VERBS[job.action]} ${job.label}`;
}

/** Where a running job is, e.g. "Findings: 120,000 / 500,000 (24%)". */
export function jobProgressText(job: ArchiveJob, workerDown = false): string {
  if (workerDown && job.status === "pending") return `${STOPPED} This starts when it's back.`;
  if (job.status === "pending") return WAITING;
  if (workerDown && runByWorker(job)) return `${STOPPED} This carries on where it left off when it's back.`;
  const phase = job.progress?.phase ?? "";
  const label = JOB_PHASES[phase] ?? "Working";
  return counted(label, job.progress?.rows_done, job.progress?.rows_total) ?? `${label}…`;
}

/** A finished job's outcome, e.g. "Archived findings.csv: 1 upload, 3 assets,
 * 1,200 findings." */
export function jobResultText(job: ArchiveJob): string {
  const summary = job.summary ?? {};
  if (job.status === "failed") return `${jobTitle(job)} stopped: ${summary.error ?? "unexpected error"}`;
  let text = `${JOB_DONE[job.action]} ${job.label}: ${countsText(summary)}.`;
  if (summary.findings_kept_with_asset) {
    const n = summary.findings_kept_with_asset;
    text += ` ${n.toLocaleString("en-US")} finding${n === 1 ? "" : "s"} stayed archived with ${n === 1 ? "its" : "their"} asset, archived separately: restore the asset to bring ${n === 1 ? "it" : "them"} back.`;
  }
  if (summary.duplicates_purged) {
    const n = summary.duplicates_purged;
    text += ` ${n.toLocaleString("en-US")} finding${n === 1 ? "" : "s"} already recorded again since ${n === 1 ? "was" : "were"} purged instead.`;
  }
  return text;
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

// A large import or archive job not yet taken by the background worker.
const WAITING = "Waiting for the background worker…";
// The worker isn't checking in: what waits for it, or what it was running,
// goes on when it's back (an import from the start: imports are all-or-nothing).
const STOPPED = "Interrupted: the background worker stopped.";

/** Waiting for the background worker, or cut off by it, while it's down:
 * shown as a warning (the user should know). */
export function isInterrupted(item: Scan | ArchiveJob, workerDown: boolean): boolean {
  return workerDown && (item.status === "pending" || runByWorker(item));
}

/** Whether the background worker runs it (not the request that started it). */
export function runByWorker(item: Scan | ArchiveJob): boolean {
  return item.status === "running" && item.heartbeat_at != null;
}

/** Where a running import is, e.g. "Writing rows: 120,000 / 500,000 (24%)";
 * `workerDown`: the background worker isn't checking in. */
export function progressText(scan: Scan, workerDown = false): string {
  const progress = scan.progress;
  if (workerDown && scan.status === "pending") return `${STOPPED} This upload starts when it's back.`;
  if (scan.status === "pending") return WAITING;
  // The worker keeps what it has read and checked (Phase 2f): it carries on
  // from there; one cut off while writing writes again, nothing half-written.
  if (workerDown && runByWorker(scan)) {
    return `${STOPPED} This upload carries on from where it got to when it's back.`;
  }
  switch (progress?.phase) {
    case "waiting":
      return "Waiting for another upload into this organization to finish processing…";
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
    filename: scan.filename ?? "Upload",
    scanType: scan.scan_type,
  };
}
