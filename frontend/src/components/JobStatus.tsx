"use client";

import { useState } from "react";

import { isRunning, jobProgressText, jobResultText, jobTitle, useImports } from "@/context/ImportsContext";

/** Archive, restore and purge jobs: progress while they run, then the
 * outcome (for whoever started it) until it's dismissed. */
export default function JobStatus() {
  const { jobs, dismissJob } = useImports();
  const [error, setError] = useState<string | null>(null);
  if (jobs.length === 0) return null;

  return (
    <div className="space-y-3">
      {jobs.filter(isRunning).map((job) => (
        <section key={job.id} aria-label={jobTitle(job)} className="rounded-xl border border-cyan/30 bg-cyan/5 p-4 text-sm">
          <p className="text-white">
            <span className="font-medium">{jobTitle(job)}</span>{" "}
            <span className="text-white/60">— in the background</span>
          </p>
          <p className="mt-1 text-cyan">{jobProgressText(job)}</p>
        </section>
      ))}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          Couldn&apos;t dismiss: {error}
        </p>
      )}
      {jobs
        .filter((job) => !isRunning(job))
        .map((job) => (
          <section
            key={job.id}
            aria-label={`${jobTitle(job)} result`}
            className={`flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4 text-sm ${
              job.status === "failed" ? "border-red-400/30 bg-red-400/5 text-red-200" : "border-white/10 bg-white/5 text-white"
            }`}
          >
            <p>{jobResultText(job)}</p>
            <button
              type="button"
              onClick={() => {
                setError(null);
                dismissJob(job.id).catch((err: Error) => setError(err.message));
              }}
              className="text-xs text-white/60 hover:text-white"
            >
              Dismiss
            </button>
          </section>
        ))}
    </div>
  );
}
