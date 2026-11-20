"use client";
import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/domain";
import StatusMessage from "./StatusMessage";

type ProofRecord = { id: string; version: number; state: string; source_reference: string; observed_at: string;
  submitter_label: string; actor_label: string; created_at: string; note: string };
type Proof = { version: number; workflow_version: number; state: string; blocked_reason: string | null;
  can_submit: boolean; can_review: boolean; self_review_required: boolean; next_before: number | null; records: ProofRecord[] };
type Props = { orgId: string; findingId: string; disabled: boolean; hasWorkflowDraft?: boolean; onBusyChange(value: boolean): void };
const control = "mt-1 block w-full rounded-md border border-white/20 bg-navy p-2 text-sm";

export default function FindingRemediationProof(props: Props) {
  const [open, setOpen] = useState(false);
  return <details className="mt-5 border-t border-white/15 pt-3" onToggle={event => event.currentTarget.open && setOpen(true)}>
    <summary className="cursor-pointer font-semibold">Remediation proof</summary>
    {open && props.hasWorkflowDraft && <p role="status" className="mt-3 text-sm">Save or clear the workflow draft before submitting or reviewing remediation proof.</p>}
    {open && <ProofPanel key={`${props.orgId}:${props.findingId}`} {...props} disabled={props.disabled || !!props.hasWorkflowDraft} />}
  </details>;
}

function ProofPanel({ orgId, findingId, disabled, onBusyChange }: Props) {
  const path = `/orgs/${orgId}/findings/${findingId}/remediation-proof`;
  const [before, setBefore] = useState<number | null>(null);
  const { data, loading, error, reload } = useApi<Proof>(path + (before ? `?before=${before}` : ""));
  return <section aria-label="Remediation proof review" className="mt-3 space-y-3">
    <p className="text-sm text-white/70">Submit post-fix evidence while the finding is Open. An organization administrator reviews it. Approval records proof review; workflow closure and scoring evidence review remain separate actions.</p>
    <StatusMessage loading={loading} error={error} />
    <button type="button" disabled={disabled || loading} className="text-cyan underline" onClick={reload}>Reload remediation proof</button>
    {data && !loading && !error && <>
      <p role="status">{data.state === "pending" ? "Verification pending. The workflow remains Open." : data.state === "rejected" ? "Proof rejected. The finding remains Open; address the reviewer's reason and submit new evidence." : data.state === "approved" ? "Proof approved. Workflow closure still requires an explicit action." : data.state === "stale" ? "Proof context changed or evidence is unavailable or older than 90 days. Submit current evidence for a new review." : "No remediation proof submitted."}</p>
      {data.blocked_reason && <p>{data.blocked_reason}</p>}
      {!before && <ProofForm key={`${data.version}:${data.workflow_version}`} data={data} path={path} disabled={disabled} onBusyChange={onBusyChange} reload={reload} />}
      <h4 className="font-semibold">Remediation proof history</h4>
      {data.records.length ? <ol className="space-y-2">{data.records.map(row => <li key={row.id} className="rounded border border-white/15 p-3 text-sm">
        <p>{row.actor_label} · {formatDateTime(row.created_at)} · {row.state} · Version {row.version}</p>
        <p className="break-words">Evidence reference: {row.source_reference}</p>
        <p>Observed: {formatDateTime(row.observed_at)} · Submitted by: {row.submitter_label}</p>
        <p className="whitespace-pre-wrap break-words">{row.note}</p>
      </li>)}</ol> : <p>No retained proof decisions.</p>}
      <div className="flex gap-4">
        {data.next_before && <button type="button" disabled={disabled} className="text-cyan underline" onClick={() => setBefore(data.next_before)}>Older proof decisions</button>}
        {before && <button type="button" disabled={disabled} className="text-cyan underline" onClick={() => setBefore(null)}>Latest proof decisions</button>}
      </div>
    </>}
  </section>;
}

function ProofForm({ data, path, disabled, onBusyChange, reload }: { data: Proof; path: string; disabled: boolean; onBusyChange(value: boolean): void; reload(): void }) {
  const [mode, setMode] = useState(data.can_review ? "review" : "submit");
  const [reference, setReference] = useState("");
  const [observed, setObserved] = useState("");
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState("rejected");
  const [reviewed, setReviewed] = useState(false);
  const [selfReview, setSelfReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!data.can_submit && !data.can_review) return null;
  const reviewing = mode === "review" && data.can_review;
  async function save() {
    if (disabled || inFlight.current || conflict) return;
    inFlight.current = true; setBusy(true); onBusyChange(true); setError(null);
    try {
      await api.post(path + (reviewing ? "/review" : ""), {
        expected_version: data.version, expected_workflow_version: data.workflow_version, note,
        ...(reviewing ? { decision, evidence_reviewed: reviewed, self_review_acknowledged: selfReview }
          : { source_reference: reference, observed_at: new Date(observed).toISOString() }),
      });
      reload();
    } catch (cause) {
      const unknownOutcome = !(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500;
      setError(unknownOutcome ? "The save outcome is unknown. Reload remediation proof to check retained history before another write."
        : cause.message);
      if (unknownOutcome || (cause instanceof ApiError && cause.status === 409)) setConflict(true);
    } finally { inFlight.current = false; setBusy(false); onBusyChange(false); }
  }
  return <form onSubmit={event => { event.preventDefault(); void save(); }} className="space-y-3">
    <fieldset disabled={disabled || busy || conflict} className="space-y-3">
      <legend className="sr-only">Remediation proof action</legend>
      <label className="block text-sm">Proof action<select aria-label="Proof action" className={control} value={mode} onChange={e => setMode(e.target.value)}>
        {data.can_submit && <option value="submit">{data.version ? "Submit replacement proof" : "Submit proof"}</option>}
        {data.can_review && <option value="review">Review pending proof</option>}
      </select></label>
      {reviewing ? <>
        <label className="block text-sm">Proof decision<select aria-label="Proof decision" className={control} value={decision} onChange={e => setDecision(e.target.value)}><option value="rejected">Reject</option><option value="approved">Approve</option></select></label>
        <label className="flex gap-2"><input required type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I reviewed the referenced remediation evidence.</label>
        {data.self_review_required && <label className="flex gap-2"><input required type="checkbox" checked={selfReview} onChange={e => setSelfReview(e.target.checked)} />I acknowledge reviewing remediation proof I submitted.</label>}
      </> : <>
        <label className="block text-sm">Proof evidence reference<input aria-label="Proof evidence reference" required maxLength={2048} className={control} value={reference} onChange={e => setReference(e.target.value)} placeholder="https://... or document:version-UUID" /></label>
        <label className="block text-sm">Proof observed at<input aria-label="Proof observed at" required type="datetime-local" className={control} value={observed} onChange={e => setObserved(e.target.value)} /></label>
        <p className="text-xs text-white/60">Use an observation from the last 90 days. References are retained as text; URLs are not fetched.</p>
      </>}
      <label className="block text-sm">{reviewing ? "Proof review reason and next action" : "Proof submission note"}<textarea aria-label={reviewing ? "Proof review reason and next action" : "Proof submission note"} required maxLength={4000} className={control} value={note} onChange={e => setNote(e.target.value)} /></label>
      <button className="rounded-md bg-cyan px-3 py-2 text-navy">{busy ? "Saving proof…" : reviewing ? "Save proof decision" : "Submit remediation proof"}</button>
    </fieldset>
    <StatusMessage loading={busy} error={error} />
    {conflict && <p role="status">Reload remediation proof before retrying.</p>}
  </form>;
}
