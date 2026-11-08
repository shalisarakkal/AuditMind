"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/domain";
import { enumLabel } from "@/lib/presentation";
import type { CanonicalReceipt } from "./FindingCanonicalReview";
import FindingActionDialog from "./FindingActionDialog";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY } from "./DialogActions";

export default function FindingCanonicalHistory({orgId, findingId, canReview, disabled, onBusyChange}: {
  orgId: string; findingId: string; canReview: boolean; disabled: boolean; onBusyChange?(busy: boolean): void;
}) {
  const [open, setOpen] = useState(false), [offset, setOffset] = useState(0);
  const [target, setTarget] = useState<CanonicalReceipt | null>(null), [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const rows = useApi<CanonicalReceipt[]>(open ? `/orgs/${orgId}/findings/${findingId}/canonical-decisions?offset=${offset}` : null);
  async function revoke() {
    if (pending.current || disabled || !target || !reason.trim() || error) return;
    pending.current = true; setBusy(true); onBusyChange?.(true);
    try {
      await api.post(`/orgs/${orgId}/canonical-decisions/${target.id}/revoke`, {expected_version: target.version, rationale: reason.trim()});
      setTarget(null); setReason(""); rows.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "Canonical revocation failed"); }
    finally { pending.current = false; setBusy(false); onBusyChange?.(false); }
  }
  return <section className="mt-4 min-w-0 border-t border-white/15 pt-3" aria-label="Canonical selection history">
    <button type="button" className="text-cyan underline" disabled={busy} aria-expanded={open} onClick={() => setOpen(v => !v)}>{open ? "Hide canonical selection history" : "Show canonical selection history"}</button>
    {open && <div className="mt-3 space-y-3 text-sm [overflow-wrap:anywhere]">
      <p className="text-xs text-white/70">Recorded selections preserve independent histories. They do not merge findings or change counts. Current eligibility must be rechecked through the pair preview.</p>
      {rows.loading ? <p role="status">Loading canonical decisions…</p> : rows.error ? <p role="alert">{rows.error} <button type="button" onClick={rows.reload}>Retry canonical history</button></p> : !rows.data?.length ? <p>No canonical selections recorded.</p> : rows.data.map(row => <article key={row.id} className="rounded border border-white/15 p-3">
        <p>{enumLabel(row.state)} · Version {row.version} · {row.actor_label} · {formatDateTime(row.created_at)}</p>
        <p>Canonical finding: {row.canonical_finding_id}</p><p className="whitespace-pre-wrap">{row.rationale}</p>
        <details><summary>Recorded review of both findings</summary>{row.context.findings.map(finding => <p key={finding.id} className="mt-2">{finding.id} · {finding.description} · Workflow: {enumLabel(finding.workflow.status)} (version {finding.workflow.version}) · Recorded scoring review: {enumLabel(finding.verification_state)} (version {finding.verification_version})</p>)}</details>
        {canReview && row.latest && row.state === "selected" && <button type="button" disabled={disabled} className="mt-2 text-cyan underline disabled:opacity-50" onClick={() => {setTarget(row); setReason(""); setError(null);}}>Revoke canonical selection</button>}
      </article>)}
      <div className="flex gap-3"><button type="button" disabled={rows.loading || offset === 0} onClick={() => setOffset(v => Math.max(0,v-20))}>Newer canonical decisions</button><button type="button" disabled={rows.loading || !!rows.error || (rows.data?.length || 0) < 20} onClick={() => setOffset(v => v+20)}>Older canonical decisions</button></div>
    </div>}
    {target && <FindingActionDialog title="Revoke canonical selection" orgName={target.canonical_finding_id} onClose={() => {if (!pending.current) setTarget(null);}}>
      <div aria-busy={busy} className="space-y-3 [overflow-wrap:anywhere]">
        <p>Withdraw recorded canonical selection version {target.version}? Both finding records and all retained histories remain unchanged.</p>
        <label className="block text-sm">Revocation reason<textarea maxLength={2000} disabled={busy || !!error} className="mt-1 w-full rounded border border-white/20 bg-navy p-2" value={reason} onChange={e => setReason(e.target.value)} /></label>
        {error && <p role="alert" className="text-sm text-red-300">{error} <button type="button" disabled={busy} className="underline" onClick={() => {setTarget(null); setError(null); rows.reload();}}>Reload canonical decisions</button></p>}
        <footer className={DIALOG_FOOTER}><button type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={busy} onClick={() => setTarget(null)}>Cancel</button><button type="button" className={DIALOG_PRIMARY} disabled={busy || !reason.trim() || !!error || disabled} onClick={() => void revoke()}>Revoke selection</button></footer>
      </div>
    </FindingActionDialog>}
  </section>;
}
