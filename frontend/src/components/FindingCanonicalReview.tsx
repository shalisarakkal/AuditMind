"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { enumLabel } from "@/lib/presentation";
import { formatDateTime } from "@/lib/domain";
import { findingHref } from "./FindingReference";
import FindingActionDialog from "./FindingActionDialog";
import FindingCanonicalHistory from "./FindingCanonicalHistory";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY, DIALOG_SECONDARY } from "./DialogActions";

type Note = { text: string; actor_label?: string; created_at?: string };
type Summary = { id: string; category: string | null; description: string; severity: string;
  asset_id?: string | null; scan_id?: string | null;
  latest_observation?: { id: string; filename: string | null; source_row: number; recorded_at: string } | null;
  verification_state: string; verification_version: number;
  verification: { note: string; actor_label: string; expires_at?: string | null } | null;
  workflow: { status: string; version: number; assignee_label: string | null; assignee_id?: string | null;
    due_date?: string | null; due_expires_at?: string | null; risk_review_date?: string | null; risk_review_expires_at?: string | null;
    latest_rationale: Note | null; latest_verification: Note | null } };
export type CanonicalReceipt = { id: string; version: number; state: string; current: boolean | null; latest?: boolean;
  canonical_finding_id: string; rationale: string; actor_label: string; created_at: string;
  context: { findings: Summary[] } };
type Preview = { review_token: string; expected_version: number; context: { findings: Summary[] }; saved: CanonicalReceipt | null };

function conflictingFinding(error: unknown): string | null {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object") {
    const detail = error.detail as Record<string, unknown>;
    if (detail.code === "canonical_conflict" && typeof detail.canonical_finding_id === "string") return detail.canonical_finding_id;
  }
  return null;
}

export default function FindingCanonicalReview({ orgId, path, sourceId, onClose, onSaved, onBusyChange }: {
  orgId: string; path: string; sourceId: string; onClose(): void; onSaved(): void; onBusyChange?(busy: boolean): void;
}) {
  const [view, setView] = useState<Preview | null>(null), [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0), [selected, setSelected] = useState("");
  const [reason, setReason] = useState(""), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const [conflictId, setConflictId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const unchanged = !!view?.saved?.current && view.saved.canonical_finding_id === selected;
  useEffect(() => {
    let abandoned = false;
    setLoading(true); setView(null); setSelected(""); setConfirmed(false); setError(null); setConflictId(null);
    api.post<Preview>(path + "/canonical/preview", { source_observation_id: sourceId }).then(result => {
      if (!abandoned) setView(result);
    }).catch(err => { if (!abandoned) { setError(err instanceof Error ? err.message : "Canonical preview failed"); setConflictId(conflictingFinding(err)); } })
      .finally(() => { if (!abandoned) setLoading(false); });
    return () => { abandoned = true; };
  }, [path, sourceId, revision]);
  async function save() {
    if (inFlight.current || !view || !selected || !confirmed || !reason.trim() || unchanged) return;
    inFlight.current = true; setBusy(true); onBusyChange?.(true); setError(null);
    try {
      await api.post(path + "/canonical", { source_observation_id: sourceId,
        expected_version: view.expected_version, review_token: view.review_token,
        canonical_finding_id: selected, rationale: reason.trim(), confirm_histories: confirmed });
      onSaved(); onClose();
    } catch (err) {
      setView(null); setSelected(""); setConfirmed(false);
      setError(err instanceof Error ? err.message : "Canonical selection failed");
      setConflictId(conflictingFinding(err));
    } finally { inFlight.current = false; setBusy(false); onBusyChange?.(false); }
  }
  return <FindingActionDialog title="Review canonical finding" orgName="Two independent finding records" onClose={() => { if (!inFlight.current) onClose(); }}>
    <div aria-busy={busy} className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
      <p className="text-sm text-white/70">Designate the canonical finding for this reviewed pair. Both records, their complete retained histories and their independent workflow and scoring decisions remain in place. Counts are unchanged. This does not merge, archive or refresh either finding.</p>
      {loading && <p role="status">Loading both finding reviews…</p>}
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {conflictId && <FindingCanonicalHistory orgId={orgId} findingId={conflictId} canReview disabled={busy || loading} onBusyChange={onBusyChange} />}
      {view?.saved && <p className="text-sm">Recorded decision: {enumLabel(view.saved.state)} · Version {view.saved.version} · {view.saved.current ? "Current for this preview" : "Requires fresh review"}. Canonical finding: {view.saved.canonical_finding_id}.</p>}
      <fieldset disabled={loading || busy || !view} className="min-w-0 space-y-3">
        <legend className="text-sm font-semibold">Choose the canonical finding</legend>
        {view?.context.findings.map(finding => <article key={finding.id} className="min-w-0 space-y-2 rounded border border-white/20 p-3 text-sm">
          <label className="flex items-start gap-2 font-semibold"><input type="radio" name="canonical-finding" value={finding.id} checked={selected === finding.id} onChange={() => { setSelected(finding.id); setConfirmed(false); }} />{finding.category || "Finding"} · {finding.id}</label>
          <p className="whitespace-pre-wrap">{finding.description}</p>
          <p>Severity: {enumLabel(finding.severity)} · Workflow: {enumLabel(finding.workflow.status)} · Version {finding.workflow.version}</p>
          <p>Assignee: {finding.workflow.assignee_label || (finding.workflow.assignee_id ? "Former/unavailable assignee" : "Unassigned")}</p>
          <p>Due date: {finding.workflow.due_expires_at ? formatDateTime(finding.workflow.due_expires_at) : finding.workflow.due_date || "Not set"}</p>
          <p>Risk review date: {finding.workflow.risk_review_expires_at ? formatDateTime(finding.workflow.risk_review_expires_at) : finding.workflow.risk_review_date || "Not set"}</p>
          <details><summary>Observation and source IDs</summary>
            <p>Asset: {finding.asset_id || "Not available"} · Upload: {finding.scan_id || "Not available"}</p>
            {finding.latest_observation && <p>Latest retained observation: {finding.latest_observation.id} · {finding.latest_observation.filename || "Imported file"} · Row {finding.latest_observation.source_row} · {formatDateTime(finding.latest_observation.recorded_at)}</p>}
          </details>
          <p>Latest rationale: {finding.workflow.latest_rationale?.text || "Not recorded"}</p>
          {finding.workflow.latest_rationale?.actor_label && <p className="text-xs text-white/70">{finding.workflow.latest_rationale.actor_label}{finding.workflow.latest_rationale.created_at ? ` · ${formatDateTime(finding.workflow.latest_rationale.created_at)}` : ""}</p>}
          <p>Latest verification note: {finding.workflow.latest_verification?.text || "Not recorded"}</p>
          {finding.workflow.latest_verification?.actor_label && <p className="text-xs text-white/70">{finding.workflow.latest_verification.actor_label}{finding.workflow.latest_verification.created_at ? ` · ${formatDateTime(finding.workflow.latest_verification.created_at)}` : ""}</p>}
          <p>Recorded scoring review: {enumLabel(finding.verification_state)} · Version {finding.verification_version}</p>
          {finding.verification && <p>{finding.verification.note} · {finding.verification.actor_label}</p>}
          {finding.verification?.expires_at && <p>Recorded scoring review expiry: {formatDateTime(finding.verification.expires_at)}</p>}
          <a href={findingHref(orgId, finding.id)} target="_blank" rel="noreferrer" className="text-cyan underline">Open this finding and its retained histories in a new tab</a>
        </article>)}
        <label className="block text-sm">Canonical selection reason<textarea maxLength={2000} className="mt-1 w-full rounded border border-white/20 bg-navy p-2" value={reason} onChange={e => setReason(e.target.value)} /></label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I reviewed both independent histories and understand that counts and workflow decisions remain unchanged.</label>
      </fieldset>
      {!loading && !view && <button type="button" className={DIALOG_SECONDARY} disabled={busy} onClick={() => setRevision(v => v + 1)}>Reload canonical context</button>}
      <footer className={DIALOG_FOOTER}>
        <button type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={busy} onClick={onClose}>Cancel</button>
        <button type="button" className={DIALOG_PRIMARY} disabled={busy || loading || !view || !selected || !confirmed || !reason.trim() || unchanged} onClick={() => void save()}>Save canonical selection</button>
      </footer>
    </div>
  </FindingActionDialog>;
}
