"use client";

import { useState } from "react";

import { isRunning, jobProgressText, jobResultText, jobTitle, useImports } from "@/context/ImportsContext";
import type { ArchiveJob } from "@/lib/types";

// Past this many, jobs are summed up rather than shown one by one (e.g.
// several selected rows archived at once).
const ONE_BY_ONE = 3;

const DONE = { archive: "Archived", restore: "Restored", purge: "Purged" } as const;

/** Archive, restore and purge jobs: progress while they run, then the
 * outcome (for whoever started it) until it's dismissed. Many at once are
 * summed up: the one running, how many wait their turn, and one result. */
export default function JobStatus() {
  const { jobs, dismissJob } = useImports();
  const [error, setError] = useState<string | null>(null);
  if (jobs.length === 0) return null;

  const running = jobs.filter(isRunning);
  const shown = running.length > ONE_BY_ONE ? running.filter((job) => job.status === "running") : running;
  const queued = running.length - shown.length;
  const finished = jobs.filter((job) => !isRunning(job));
  const dismiss = (ids: string[]) => {
    setError(null);
    Promise.all(ids.map((id) => dismissJob(id))).catch((err: Error) => setError(err.message));
  };

  return (
    <div className="space-y-3">
      {shown.map((job) => (
        <section key={job.id} aria-label={jobTitle(job)} className="rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm">
          <p className="text-white">
            <span className="font-medium">{jobTitle(job)}</span>{" "}
            <span className="text-white/60">— in the background</span>
          </p>
          <p className="mt-1 text-cyan">{jobProgressText(job)}</p>
        </section>
      ))}
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
        <Result failed={finished.some((job) => job.status === "failed")} onDismiss={() => dismiss(finished.map((j) => j.id))} label="Job results" dismissLabel="Dismiss all">
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
          <Result key={job.id} failed={job.status === "failed"} onDismiss={() => dismiss([job.id])} label={`${jobTitle(job)} result`}>
            <p>{jobResultText(job)}</p>
          </Result>
        ))
      )}
    </div>
  );
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
  failed,
  onDismiss,
  label,
  dismissLabel = "Dismiss",
  children,
}: {
  failed: boolean;
  onDismiss(): void;
  label: string;
  dismissLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={label}
      className={`flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4 text-sm ${
        failed ? "border-red-400/30 bg-red-400/5 text-red-200" : "border-white/10 bg-white/5 text-white"
      }`}
    >
      <div>{children}</div>
      <button type="button" onClick={onDismiss} className="text-xs text-white/60 hover:text-white">
        {dismissLabel}
      </button>
    </section>
  );
}
