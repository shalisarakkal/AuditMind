"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/domain";
import StatusMessage from "./StatusMessage";

type Review = { version: number; workflow_version: number; workflow_status: string; state: string;
  eligible_for_exclusion: boolean; can_review: boolean; self_review_required: boolean;
  records: { id: string; state: string; actor_label: string; note: string; source_reference: string; created_at: string; expires_at: string | null }[] };
const control = "mt-1 block w-full rounded-md border border-white/20 bg-navy p-2 text-sm";

export default function FindingRiskVerification({ orgId, findingId, role, disabled, onBusyChange }: { orgId: string; findingId: string; role: string; disabled: boolean; onBusyChange(value: boolean): void }) {
  const [open, setOpen] = useState(false);
  return <details className="mt-5 border-t border-white/15 pt-3" onToggle={event => event.currentTarget.open && setOpen(true)}>
    <summary className="cursor-pointer font-semibold">Scoring evidence review</summary>
    {open && <ReviewPanel orgId={orgId} findingId={findingId} role={role} disabled={disabled} onBusyChange={onBusyChange} />}
  </details>;
}

function ReviewPanel({ orgId, findingId, role, disabled, onBusyChange }: { orgId: string; findingId: string; role: string; disabled: boolean; onBusyChange(value: boolean): void }) {
  const path = `/orgs/${orgId}/findings/${findingId}/risk-verification`;
  const { data, loading, error, reload } = useApi<Review>(path);
  return <section className="mt-3 space-y-3" aria-label="Scoring evidence review">
    <p className="text-sm text-white/70">Verification notes do not authorize scoring exclusions. Submit current retest evidence for an organization administrator to review. Mitigated retains full risk even after review.</p>
    <StatusMessage loading={loading} error={error} />
    <button type="button" disabled={disabled} className="text-cyan underline" onClick={reload}>Reload evidence review</button>
    {data && <><p>Review status: {data.state.replaceAll("_", " ")}. {data.eligible_for_exclusion ? "Current evidence qualifies for exclusion when status-aware scoring is On." : "Finding retains its full risk contribution."}</p>
      <ReviewForm key={`${data.version}:${data.workflow_version}`} data={data} role={role} path={path} disabled={disabled} onBusyChange={onBusyChange} reload={reload} />
      <h4 className="font-semibold">Evidence review history</h4>
      {data.records.length ? <ol className="space-y-2">{data.records.map(record => <li key={record.id} className="rounded border border-white/15 p-3 text-sm">
        <p>{record.actor_label} · {formatDateTime(record.created_at)} · {record.state}</p>
        <p className="break-words">Evidence reference: {record.source_reference}</p>
        <p className="whitespace-pre-wrap break-words">{record.note}</p>
        {record.expires_at && <p>Expires: {formatDateTime(record.expires_at)}</p>}
      </li>)}</ol> : <p>No scoring evidence submitted.</p>}
      {data.records.length === 20 && <p className="text-xs text-white/60">Showing the latest 20 decisions.</p>}</>}
  </section>;
}

function ReviewForm({ data, role, path, disabled, reload, onBusyChange }: { data: Review; role: string; path: string; disabled: boolean; reload(): void; onBusyChange(value: boolean): void }) {
  const [reference, setReference] = useState("");
  const [observed, setObserved] = useState("");
  const [expires, setExpires] = useState("");
  const [note, setNote] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [selfReview, setSelfReview] = useState(false);
  const [decision, setDecision] = useState("approved");
  const [mode, setMode] = useState(["admin", "auditor"].includes(role) && ["resolved", "false_positive", "mitigated"].includes(data.workflow_status) ? "submit" : "review");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = ["admin", "auditor"].includes(role) && ["resolved", "false_positive", "mitigated"].includes(data.workflow_status);
  const canReview = data.can_review && ["pending", "approved"].includes(data.state);
  if (!canSubmit && !canReview) return <p className="text-sm text-white/60">Evidence can be submitted by organization admins and auditors for Resolved, False positive or Mitigated findings.</p>;
  const reviewing = mode === "review" && canReview;
  const action = data.state === "approved" ? "revoked" : decision;
  async function save() {
    setBusy(true); onBusyChange(true); setError(null);
    try {
      const payload = { expected_version: data.version, expected_workflow_version: data.workflow_version, note,
        ...(reviewing ? { decision: action, evidence_reviewed: reviewed, self_review_acknowledged: selfReview,
          expires_at: action === "approved" ? new Date(expires).toISOString() : null }
          : { source_reference: reference, observed_at: new Date(observed).toISOString() }) };
      await api.post(path + (reviewing ? "/review" : ""), payload); reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save evidence review");
      if (cause instanceof ApiError && cause.status === 409) setConflict(true);
    } finally { setBusy(false); onBusyChange(false); }
  }
  return <form onSubmit={event => { event.preventDefault(); void save(); }} className="space-y-3">
    <fieldset disabled={disabled || busy || conflict} className="space-y-3">
      <legend className="sr-only">Scoring evidence action</legend>
      <label className="block text-sm">Action<select aria-label="Action" className={control} value={mode} onChange={event => setMode(event.target.value)}>
        {canSubmit && <option value="submit">Submit evidence</option>}{canReview && <option value="review">Review evidence</option>}
      </select></label>
      {!reviewing ? <><label className="block text-sm">Evidence reference<input required maxLength={2048} className={control} value={reference} onChange={event => setReference(event.target.value)} placeholder="https://... or document:version-UUID" /></label>
        <label className="block text-sm">Observed at<input required type="datetime-local" className={control} value={observed} onChange={event => setObserved(event.target.value)} /></label></>
        : <>{data.state === "pending" ? <label className="block text-sm">Decision<select aria-label="Decision" className={control} value={decision} onChange={event => setDecision(event.target.value)}><option value="approved">Approve</option><option value="rejected">Reject</option></select></label> : <p>Revoke the current approval.</p>}
          {action === "approved" && <><label className="block text-sm">Approval expires at<input required type="datetime-local" className={control} value={expires} onChange={event => setExpires(event.target.value)} /></label>
            <p className="text-xs text-white/60">Expiry must be within 90 days of observation and review.</p>
            <label className="flex gap-2"><input required type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the referenced evidence.</label>
            {data.self_review_required && <label className="flex gap-2"><input required type="checkbox" checked={selfReview} onChange={event => setSelfReview(event.target.checked)} />I acknowledge reviewing evidence I submitted.</label>}</>}
        </>}
      <label className="block text-sm">Review rationale<textarea required maxLength={4000} className={control} value={note} onChange={event => setNote(event.target.value)} /></label>
      <button className="rounded-md bg-cyan px-3 py-2 text-navy">{busy ? "Saving…" : reviewing ? "Save evidence decision" : "Submit evidence"}</button>
    </fieldset>
    <StatusMessage loading={busy} error={error} />
    {conflict && <p role="status">Reload evidence review before retrying.</p>}
  </form>;
}
