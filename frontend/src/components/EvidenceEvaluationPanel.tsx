"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/apiClient";
import { DOMAIN_LABELS } from "@/lib/domain";
import type { Domain } from "@/lib/types";

export type EvidenceEvaluationJob = {
  id: string; status: "pending" | "running" | "completed" | "failed" | "cancelled" | "superseded";
  created_at: string; run_started_at: string | null; cancel_requested_at: string | null;
  can_cancel: boolean; is_current: boolean; error_message: string | null;
  progress: { phase: string; processed?: number; total?: number | null } | null;
  result: { evaluated_at: string; assessment_status: string; qualified_domain_count: number;
    domains: { domain: Domain; eligible: boolean; reason_code: string }[] } | null;
};
const button = "rounded-md border border-cyan px-3 py-2 text-sm text-cyan disabled:opacity-40";
const active = (job: EvidenceEvaluationJob | null) => !!job && ["pending", "running"].includes(job.status);
const words = (value: string) => value.replaceAll("_", " ");

export default function EvidenceEvaluationPanel({ orgId, disabled, refreshSignal = 0 }: { orgId: string; disabled: boolean; refreshSignal?: number }) {
  const path = `/orgs/${orgId}/scoring/evaluations`;
  const [job, setJob] = useState<EvidenceEvaluationJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [clock, setClock] = useState(Date.now);
  const [reload, setReload] = useState(0);
  const [dismissedCompletion, setDismissedCompletion] = useState("");
  const serial = useRef(0);
  const action = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      if (action.current) { timer = setTimeout(refresh, 1000); return; }
      const request = ++serial.current;
      let delay = 10000;
      try {
        const latest = await api.get<EvidenceEvaluationJob | null>(`${path}/current`, { background: true });
        if (current && request === serial.current) { setJob(latest); setError(""); setLoading(false); }
        if (active(latest)) delay = 1000;
      } catch (cause) {
        if (current && request === serial.current) { setError(cause instanceof Error ? cause.message : "Could not refresh evaluation status"); setLoading(false); }
      } finally { if (current) timer = setTimeout(refresh, delay); }
    }
    void refresh();
    return () => { current = false; mounted.current = false; serial.current++; clearTimeout(timer); };
  }, [path, reload, refreshSignal]);
  const jobStatus = job?.status;
  const completionKey = `${path}/${job?.id}`;
  useEffect(() => {
    if (jobStatus !== "completed") return;
    const timer = setTimeout(() => setDismissedCompletion(completionKey), 5000);
    return () => clearTimeout(timer);
  }, [completionKey, jobStatus]);
  useEffect(() => {
    if (jobStatus !== "pending" && jobStatus !== "running") return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [jobStatus]);
  async function submit(cancel = false) {
    const request = ++serial.current;
    action.current = true; setSubmitting(true); setError("");
    try {
      const latest = await api.post<EvidenceEvaluationJob>(cancel ? `${path}/${job!.id}/cancel` : path);
      if (mounted.current && request === serial.current) { setJob(latest); setLoading(false); }
    } catch (cause) {
      if (mounted.current && request === serial.current) setError(cause instanceof Error ? cause.message : "Evaluation request failed");
    } finally {
      action.current = false;
      if (mounted.current) { setSubmitting(false); setReload(value => value + 1); }
    }
  }
  const running = active(job);
  const progress = job?.progress;
  const elapsed = job ? Math.max(0, Math.floor((clock - new Date(job.run_started_at ?? job.created_at).getTime()) / 1000)) : 0;
  const result = !error && job?.is_current ? job.result : null;
  return <section aria-label="Organization-wide evidence evaluation" className="space-y-3 rounded-lg border border-white/15 p-4">
    <h3 className="font-medium">Organization-wide evaluation</h3>
    <p className="text-sm text-white/60">Checks all seven domains across this organization. The domain selected below does not limit this evaluation. Unsaved edits are not included. The worker continues if you leave this page; no AI calls are made.</p>
    <button className={button} type="button" disabled={disabled || loading || submitting || running} onClick={() => void submit()}>Evaluate evidence across all domains</button>
    {loading && <p role="status">Loading evaluation status…</p>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {job && (job.status !== "completed" || dismissedCompletion !== completionKey) && <div role="status" aria-label="Organization evaluation progress" className="space-y-2 text-sm">
      <p>{job.status === "completed" ? "Evaluation completed." : <>{job.cancel_requested_at && running ? "Cancellation requested" : job.status === "pending" ? "Queued — waiting for the background worker" : words(job.status)}{progress ? `: ${words(progress.phase)} · ${(progress.processed ?? 0).toLocaleString()} / ${progress.total == null ? "counting records" : progress.total.toLocaleString()} records` : ""}{running ? ` · ${elapsed}s elapsed` : ""}</>}</p>
      {progress?.total != null && progress.total > 0 && <progress aria-label="Inventory records processed" className="w-full accent-cyan" max={progress.total} value={progress.processed ?? 0} />}
      {running && <p className="text-white/60">Counts advance after completed batches. Counting and preparing the next batch may take time. Cancellation waits for the current database fetch to finish.</p>}
      {job.can_cancel && running && <button type="button" className={button} disabled={submitting || !!job.cancel_requested_at} onClick={() => void submit(true)}>Cancel operation</button>}
      {job.status === "cancelled" && <p>Evaluation cancelled. No partial result was published.</p>}
      {job.status === "superseded" && <p>Inputs changed during evaluation. The result was not published; evaluate again.</p>}
      {job.status === "failed" && <p>{job.error_message ?? "Evaluation failed. Check the worker and retry."}</p>}
    </div>}
    {job?.status === "completed" && !job.is_current && <p role="status">Evidence changed or a review expired. Evaluate again before relying on these results.</p>}
    {result ? <div className="space-y-2"><p>Coverage assessment: {words(result.assessment_status)} · {result.qualified_domain_count} of 7 domains qualified.</p>
      <p className="text-sm text-white/60">Last evaluated: {new Date(result.evaluated_at).toLocaleString()}. Only current results can authorize scores when evidence-qualified scoring is enabled.</p>
      <ul>{result.domains.map(domain => <li key={domain.domain}>{DOMAIN_LABELS[domain.domain]}: {words(domain.reason_code)}{domain.eligible ? " (eligible)" : " (not eligible)"}</li>)}</ul>
    </div> : <p className="text-sm text-white/60">{job && ["cancelled", "failed"].includes(job.status)
      ? "This job published no result. An earlier completed evaluation may still be usable if its evidence remains current."
      : "Current eligibility has not been established. A saved approval alone does not establish current coverage."}</p>}
  </section>;
}
