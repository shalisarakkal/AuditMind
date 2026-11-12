"use client";

import { useEffect, useId, useRef, useState } from "react";
import FindingActionDialog from "@/components/FindingActionDialog";
import FindingReference from "@/components/FindingReference";
import { DIALOG_NEUTRAL, DIALOG_PRIMARY, DIALOG_SECONDARY } from "@/components/DialogActions";
import { api, ApiError } from "@/lib/apiClient";
import { WORKFLOW_LABELS, type WorkflowStatus } from "@/lib/findingWorkflow";

export type SuppressionTarget = { action: "suppress" | "clear"; finding_id?: string; suppression_id?: string };
type Preview = { label: string; finding_id: string; review_token: string; expected_version: number;
  lifecycle: "retained" | "archived" | "purged"; finding_status: string | null;
  identity: { tool_name: string; candidate_key: string; source_material: { plugin_id: string; port: number; protocol: string } } };
type Write = SuppressionTarget & { request_id: string; review_token: string; expected_version: number; rationale: string; confirm: boolean };

export default function FindingSuppressionDialog({ orgId, orgName, target, onClose, onSaved }: {
  orgId: string; orgName: string; target: SuppressionTarget; onClose(): void; onSaved(): void;
}) {
  const { action, finding_id, suppression_id } = target;
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [version, setVersion] = useState(0);
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const sent = useRef<Write | null>(null);
  const reasonId = useId();
  const confirmId = useId();
  const title = action === "suppress" ? "Suppress finding" : "Clear suppression";

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setLoading(true); setError(null); setPreview(null); setStale(false); setConfirmed(false); sent.current = null;
    api.post<Preview>(`/orgs/${orgId}/finding-suppressions/preview`, { action, finding_id, suppression_id }, { signal: controller.signal })
      .then(value => { if (current) setPreview(value); })
      .catch((failure: Error) => { if (current) setError(failure.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [orgId, action, finding_id, suppression_id, version]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busyRef.current || !preview || stale || (!uncertain && (!confirmed || !rationale.trim()))) return;
    const payload = sent.current ?? { action, finding_id, suppression_id, request_id: crypto.randomUUID(),
      review_token: preview.review_token, expected_version: preview.expected_version, rationale: rationale.trim(), confirm: confirmed };
    sent.current = payload; busyRef.current = true; setBusy(true); setError(null);
    try {
      await api.post(`/orgs/${orgId}/finding-suppressions/decisions`, payload);
      if (alive.current) onSaved();
    } catch (failure) {
      if (!alive.current) return;
      const known = failure instanceof ApiError && failure.status >= 400 && failure.status < 500;
      setError(failure instanceof Error ? failure.message : "The request failed.");
      setStale(known); setUncertain(!known);
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return <FindingActionDialog title={title} orgName={orgName} onClose={() => { if (!busyRef.current) onClose(); }}>
    <form aria-busy={busy} onSubmit={save} className="min-w-0 space-y-4">
      {loading && <p role="status">Reviewing current identity and finding context...</p>}
      {preview && <section aria-label="Reviewed suppression target" className="min-w-0 space-y-2 rounded-lg border border-white/15 p-3 text-sm">
        <p className="break-words font-semibold">{preview.label}</p>
        <FindingReference orgId={orgId} id={preview.finding_id} />
        <p>Current workflow status: {preview.finding_status ? WORKFLOW_LABELS[preview.finding_status as WorkflowStatus] ?? "Unavailable" : "Unavailable"}.</p>
        <p className="break-words">Scanner: {preview.identity.tool_name}. Plugin: {preview.identity.source_material?.plugin_id ?? "Unavailable"}; service: {preview.identity.source_material?.port ?? "Unavailable"}/{preview.identity.source_material?.protocol ?? "Unavailable"}.</p>
        {action === "suppress" ? <p>This finding will leave active lists and new risk calculations. Workflow status and saved reports remain unchanged. Suppression is not proof of remediation.</p>
          : <p>Clear this standing suppression. {preview.lifecycle === "purged" ? "The original payload was purged and cannot be restored. Future eligible observations may be visible." : preview.lifecycle === "archived" ? "The payload remains archived; restore its upload or asset separately." : "The retained finding will return to active lists under its existing workflow and scoring policy."}</p>}
        <p className="text-xs text-white/70">New uploads require their own identity review. Ambiguous reappearances remain visible for review.</p>
      </section>}
      {error && <p role="alert" className="break-words text-sm text-red-300">{error}</p>}
      {uncertain && <p role="status" className="text-sm text-amber-200">The outcome is unknown. Retry the same request to confirm it. Closing does not undo a decision that may have completed.</p>}
      {!loading && !uncertain && <button type="button" className={DIALOG_SECONDARY} disabled={busy} onClick={() => setVersion(value => value + 1)}>Reload preview</button>}
      {preview && <>
        <label htmlFor={reasonId} className="block text-sm">Rationale</label>
        <textarea id={reasonId} required maxLength={2000} value={rationale} disabled={busy || uncertain || stale}
          onChange={event => setRationale(event.target.value)} className="w-full rounded-md border border-white/20 bg-navy p-2" />
        <label htmlFor={confirmId} className="flex items-start gap-2 text-sm"><input id={confirmId} type="checkbox" checked={confirmed} disabled={busy || uncertain || stale}
          onChange={event => setConfirmed(event.target.checked)} className="mt-1 accent-cyan" />I reviewed this exact target and the visibility consequences.</label>
      </>}
      <footer className="flex flex-col gap-3 border-t border-white/15 pt-4 sm:flex-row sm:justify-end">
        <button type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={busy} onClick={() => { if (!busyRef.current) onClose(); }}>Cancel</button>
        {preview && <button type="submit" className={DIALOG_PRIMARY} disabled={loading || busy || stale || (!uncertain && (!confirmed || !rationale.trim()))}>
          {busy ? "Saving..." : uncertain ? "Retry same request" : title}</button>}
      </footer>
    </form>
  </FindingActionDialog>;
}
