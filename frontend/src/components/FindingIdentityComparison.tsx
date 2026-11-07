"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/apiClient";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY, DIALOG_SECONDARY } from "./DialogActions";

type Comparison = {
  review_token: string; source_observation_id: string; target_version: number;
  source_finding_id: string; target_finding_id: string;
  tool_name: string; canonical_asset_id: string; target_asset_id: string;
  result: "same_finding" | "canonical_conflict"; already_reviewed: boolean;
  source_material: { plugin_id: string; port: number; protocol: string };
};

export default function FindingIdentityComparison({ orgId, findingId, observationId, disabled, onBusyChange, onSaved }: {
  orgId: string; findingId: string; observationId: string; disabled: boolean;
  onBusyChange?(busy: boolean): void; onSaved(): void;
}) {
  const [open, setOpen] = useState(false), [reference, setReference] = useState("");
  const [preview, setPreview] = useState<Comparison | null>(null), [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const path = `/orgs/${orgId}/findings/${findingId}/observations/${observationId}/identity-binding`;
  async function run(save: boolean) {
    if (inFlight.current || disabled) return;
    if (save && (!preview || !confirmed || !reason.trim())) return;
    inFlight.current = true; setBusy(true); onBusyChange?.(true); setError(null);
    try {
      if (save && preview) {
        await api.post(path + "/carry-forward", { source_observation_id: preview.source_observation_id,
          expected_version: preview.target_version, review_token: preview.review_token,
          confirm_mapping: confirmed, rationale: reason.trim() });
        setOpen(false); onSaved();
      } else {
        setPreview(null); setConfirmed(false);
        setPreview(await api.post<Comparison>(path + "/compare", { source_observation_id: reference.trim() }));
      }
    } catch (err) {
      // Any failed/uncertain write requires a fresh preview, never a blind retry.
      setPreview(null); setConfirmed(false);
      setError(err instanceof Error ? err.message : "Identity comparison failed");
    } finally { inFlight.current = false; setBusy(false); onBusyChange?.(false); }
  }
  if (!open) return <button type="button" disabled={disabled} className="mt-2 block text-cyan underline disabled:opacity-50" onClick={() => {
    setReference(""); setPreview(null); setReason(""); setConfirmed(false); setError(null); setOpen(true);
  }}>Review against an earlier observation</button>;
  return <section aria-label="Cross-import identity review" aria-busy={busy} className="mt-3 min-w-0 space-y-3 rounded border border-white/20 p-3">
    <p className="text-xs text-white/70">Compare one earlier, reviewed native Nessus observation. Independently verify the scanner and canonical host for this later upload. This does not merge findings, refresh their details or change workflow, scores or scan coverage.</p>
    <fieldset disabled={disabled || busy} className="min-w-0 space-y-3">
      <label className="block text-sm">Earlier observation UUID<input className="mt-1 w-full rounded border border-white/20 bg-navy p-2" value={reference} onChange={e => {
        setReference(e.target.value); setPreview(null); setConfirmed(false);
      }} /></label>
      <button type="button" className={DIALOG_SECONDARY} disabled={!reference.trim()} onClick={() => void run(false)}>{busy ? "Checking identity…" : "Compare identity"}</button>
      {preview && <div className="space-y-2 break-words text-sm [overflow-wrap:anywhere]" role="status">
        <p>Scanner: {preview.tool_name}</p>
        <p>Canonical asset: {preview.canonical_asset_id}</p>
        <p>Captured target asset: {preview.target_asset_id}</p>
        <p>Native plugin: {preview.source_material.plugin_id} · Port: {preview.source_material.port} · Protocol: {preview.source_material.protocol}</p>
        <p>Reference finding: {preview.source_finding_id}</p>
        {preview.result === "canonical_conflict"
          ? <p className="text-amber-300">Matching identity points to separate findings. Canonical conflict resolution is required; nothing will be merged or carried forward.</p>
          : preview.already_reviewed ? <p>This observation already has the same current reviewed identity. No new review is needed.</p>
          : <><p>The native identity matches within the same finding. Verify that this upload came from the same scanner and represents the same canonical host.</p>
            <label className="block">Carry-forward review reason<textarea className="mt-1 w-full rounded border border-white/20 bg-navy p-2" maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} /></label>
            <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I independently verified this upload&apos;s scanner and canonical host.</label>
          </>}
      </div>}
    </fieldset>
    {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    <footer className={DIALOG_FOOTER}>
      <button type="button" className={DIALOG_NEUTRAL} disabled={disabled || busy} onClick={() => setOpen(false)}>Cancel comparison</button>
      {preview?.result === "same_finding" && !preview.already_reviewed && <button type="button" className={DIALOG_PRIMARY} disabled={disabled || busy || !confirmed || !reason.trim()} onClick={() => void run(true)}>Save reviewed mapping</button>}
    </footer>
  </section>;
}
