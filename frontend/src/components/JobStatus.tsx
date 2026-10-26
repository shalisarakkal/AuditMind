"use client";

import { useState } from "react";

import { isInterrupted, isRunning, jobProgressText, jobResultText, jobTitle, useImports } from "@/context/ImportsContext";
import type { ArchiveJob } from "@/lib/types";
import { useVisibleAutoDismiss } from "@/lib/useVisibleAutoDismiss";

// Past this many, jobs are summed up rather than shown one by one (e.g.
// several selected rows archived at once).
const ONE_BY_ONE = 3;

const DONE = { archive: "Archived", restore: "Restored", purge: "Purged" } as const;

/** Archive, restore and purge jobs: progress while they run, then the
 * outcome (for whoever started it); routine success auto-dismisses. Many at once are
 * summed up: the one running, how many wait their turn, and one result. */
export default function JobStatus() {
  const { jobs, dismissJob, workerDown } = useImports();
  const [error, setError] = useState<string | null>(null);
  if (jobs.length === 0) return null;

  const running = jobs.filter(isRunning);
  const shown = running.length > ONE_BY_ONE ? running.filter((job) => job.status === "running") : running;
  const queued = running.length - shown.length;
  const finished = jobs.filter((job) => !isRunning(job));
  const dismiss = (ids: string[], background = false) => {
    setError(null);
    Promise.all(ids.map((id) => dismissJob(id, background))).catch((err: Error) => setError(err.message));
  };

  return (
    <div className="space-y-3">
      {shown.map((job) => {
        const interrupted = isInterrupted(job, workerDown);
        return (
          <section key={job.id} aria-label={jobTitle(job)} className={interrupted ? "rounded-xl border border-violet-400/40 bg-violet-400/10 p-4 text-sm" : "rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm"}>
            <p className="text-white">
              <span className="font-medium">{jobTitle(job)}</span>{" "}
              <span className="text-white/60">— in the background</span>
            </p>
            <p className={`mt-1 ${interrupted ? "text-violet-200" : "text-cyan"}`}>
              {interrupted && <span aria-hidden className="mr-1">⚠</span>}
              {jobProgressText(job, workerDown)}
            </p>
          </section>
        );
      })}
      {queued > 0 && (
        <section aria-label="Queued jobs" className="rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm text-white">
          {queued.toLocaleString("en-US")} {shown.length ? "more " : ""}
          {queued === 1 ? "job" : "jobs"} queued for the background worker, one at a time.
        </section>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          Couldn&apos;t dismiss: {error}
        </p>
      )}
      {finished.length > ONE_BY_ONE ? (
        <Result identity={finished.map(job => job.id).sort().join(":")} autoDismiss={finished.every(routineSuccess)} failed={finished.some((job) => job.status === "failed")} onDismiss={background => dismiss(finished.map((j) => j.id), background)} label="Job results" dismissLabel="Dismiss all">
          <p>{summary(finished)}</p>
          {finished
            .filter((job) => job.status === "failed")
            .slice(0, 10)
            .map((job) => (
              <p key={job.id} className="mt-1 text-xs">
                {jobResultText(job)}
              </p>
            ))}
        </Result>
      ) : (
        finished.map((job) => (
          <Result key={job.id} identity={job.id} autoDismiss={routineSuccess(job)} failed={job.status === "failed"} onDismiss={background => dismiss([job.id], background)} label={`${jobTitle(job)} result`}>
            <p>{jobResultText(job)}</p>
          </Result>
        ))
      )}
    </div>
  );
}

function routineSuccess(job: ArchiveJob) {
  return job.status === "completed" && !job.summary?.error && !job.summary?.findings_kept_with_asset && !job.summary?.duplicates_purged;
}

/** "Archived 38 items, restored 2; 1 stopped." */
function summary(jobs: ArchiveJob[]): string {
  const parts = (["archive", "restore", "purge"] as const)
    .map((action) => {
      const n = jobs.filter((job) => job.action === action && job.status !== "failed").length;
      return n ? `${DONE[action]} ${n.toLocaleString("en-US")} ${n === 1 ? "item" : "items"}` : "";
    })
    .filter(Boolean);
  const failed = jobs.filter((job) => job.status === "failed").length;
  const text = parts.map((part, i) => (i ? part[0].toLowerCase() + part.slice(1) : part)).join(", ");
  return `${text}${failed ? `${text ? "; " : ""}${failed.toLocaleString("en-US")} stopped:` : "."}`;
}

function Result({
  identity,
  autoDismiss,
  failed,
  onDismiss,
  label,
  dismissLabel = "Dismiss",
  children,
}: {
  identity: string;
  autoDismiss: boolean;
  failed: boolean;
  onDismiss(background?: boolean): void;
  label: string;
  dismissLabel?: string;
  children: React.ReactNode;
}) {
  const notice = useVisibleAutoDismiss(autoDismiss, identity, () => onDismiss(true));
  return (
    <section
      ref={notice}
      aria-label={label}
      className={`flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4 text-sm ${
        failed ? "border-red-400/30 bg-red-400/5 text-red-200" : "border-white/10 bg-white/5 text-white"
      }`}
    >
      <div>{children}</div>
      <button type="button" onClick={() => onDismiss(false)} className="text-xs text-white/60 hover:text-white">
        {dismissLabel}
      </button>
    </section>
  );
}
