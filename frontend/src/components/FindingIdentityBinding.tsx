"use client";
import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY, DIALOG_SECONDARY } from "./DialogActions";
import ConfirmPanel from "./ConfirmPanel";
import FindingActionDialog from "./FindingActionDialog";

type Tool = { id: string; name: string; version: number; active: boolean };
type View = { asset_identity: { asset_id?: string; hostname?: string; ip?: string; cloud_id?: string }; identity_binding?: { version: number; state: string; current: boolean; rationale: string; tool_name: string; tool_id: string; canonical_asset_id: string; reviewed_from?: { observation_id: string; version: number } | null } | null };
export default function FindingIdentityBinding({ orgId, findingId, observationId, disabled, onBusyChange, onSaved }: {
  orgId: string; findingId: string; observationId: string; disabled: boolean;
  onBusyChange?(busy: boolean): void; onSaved(): void;
}) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false);
  const [toolId, setToolId] = useState(""), [canonical, setCanonical] = useState<string | null>(null);
  const [rationale, setRationale] = useState(""), [toolName, setToolName] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [retiring, setRetiring] = useState<Tool | null>(null);
  const [createdTool, setCreatedTool] = useState<Tool | null>(null);
  const [stale, setStale] = useState(false);
  const [offset, setOffset] = useState(0), [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const path = `/orgs/${orgId}/findings/${findingId}/observations/${observationId}/identity-binding`;
  const view = useApi<View>(open ? path : null);
  const tools = useApi<Tool[]>(open ? `/orgs/${orgId}/identity-tools?offset=${offset}` : null);
  const toolOptions = [...(tools.data || [])];
  if (createdTool && !toolOptions.some(tool => tool.id === createdTool.id)) toolOptions.push(createdTool);
  const selected = toolOptions.find(tool => tool.id === toolId);
  function beginReview() {
    setToolId(""); setCanonical(null); setRationale(""); setToolName("");
    setConfirmed(false); setRetiring(null); setStale(false); setError(null);
    setCreatedTool(null); setOffset(0); setOpen(true);
  }
  async function run(action: () => Promise<unknown>, close = false) {
    if (inFlight.current || disabled || stale) return;
    if (!rationale.trim()) { setError("Provide a review reason."); return; }
    inFlight.current = true; setBusy(true); onBusyChange?.(true); setError(null);
    try {
      await action();
      setRetiring(null);
      if (close) { setOpen(false); onSaved(); }
      else { view.reload(); tools.reload(); }
    } catch (err) { if (!(err instanceof ApiError) || err.status === 409 || err.status >= 500) setStale(true); setError(err instanceof Error ? err.message : "Identity operation failed"); }
    finally { inFlight.current = false; setBusy(false); onBusyChange?.(false); }
  }
  if (!open) return <button type="button" disabled={disabled} className="mt-2 text-cyan underline disabled:opacity-50" onClick={beginReview}>Review identity binding</button>;
  return <section aria-label="Review identity binding" className="mt-3 space-y-3 rounded border border-white/20 p-3" aria-busy={busy}>
    <p className="text-xs text-white/70">Review this observation only. Later uploads require separate review. Identity does not authorize reconciliation, suppression or score changes.</p>
    {view.loading || tools.loading ? <p role="status">Loading identity context...</p> : null}
    {view.error || tools.error ? <p role="alert">{view.error || tools.error} <button type="button" disabled={busy} onClick={() => { view.reload(); tools.reload(); }}>Reload identity context</button></p> : null}
    {view.data && <p className="break-words text-xs text-white/70">Captured source asset: {view.data.asset_identity.hostname || view.data.asset_identity.cloud_id || view.data.asset_identity.ip || "Not named"}. UUID: {view.data.asset_identity.asset_id || "Not available"}.</p>}
    {view.data?.identity_binding && <p className="text-xs">Saved binding version {view.data.identity_binding.version}: {view.data.identity_binding.current ? "Current" : "Not current"}. Tool: {view.data.identity_binding.tool_name}. Canonical asset: {view.data.identity_binding.canonical_asset_id}.</p>}
    {view.data?.identity_binding?.reviewed_from && <p className="break-words text-xs text-white/70">Independently reviewed against observation {view.data.identity_binding.reviewed_from.observation_id}, binding version {view.data.identity_binding.reviewed_from.version}.</p>}
    {error && <p role="alert" className="text-sm text-red-300">{error} <button type="button" disabled={busy} className="underline" onClick={() => { view.reload(); tools.reload(); setStale(false); setConfirmed(false); setToolId(""); setCreatedTool(null); setRetiring(null); }}>Reload identity context</button></p>}
    <form onSubmit={event => { event.preventDefault(); if (retiring) return; if (!selected || !selected.active || !confirmed) { setError("Select an active tool and confirm the mapping."); return; }
      void run(() => api.put(path, { expected_version: view.data?.identity_binding?.version || 0,
        tool_id: selected.id, expected_tool_version: selected.version,
        canonical_asset_id: canonical ?? view.data?.identity_binding?.canonical_asset_id ?? view.data?.asset_identity.asset_id,
        confirm_mapping: confirmed, rationale: rationale.trim() }), true);
    }}>
      <fieldset disabled={busy || disabled || stale || !!retiring || view.loading || tools.loading || !!view.error || !!tools.error} className="space-y-3">
        <label className="block text-sm">Registered tool instance<select className="mt-1 w-full rounded border border-white/20 bg-navy p-2" value={toolId} onChange={e => { setToolId(e.target.value); setConfirmed(false); }} required><option value="">Choose a tool instance</option>{toolOptions.filter(tool => tool.active).map(tool => <option key={tool.id} value={tool.id}>{tool.name}</option>)}</select></label>
        <div className="flex gap-3 text-xs"><button type="button" disabled={offset === 0} onClick={() => { setOffset(v => Math.max(0, v - 100)); setToolId(""); setConfirmed(false); }}>Previous tool instances</button><button type="button" disabled={(tools.data?.length || 0) < 100} onClick={() => { setOffset(v => v + 100); setToolId(""); setConfirmed(false); }}>More tool instances</button></div>
        <label className="block text-sm">Canonical asset UUID<input className="mt-1 w-full rounded border border-white/20 bg-navy p-2" value={canonical ?? view.data?.identity_binding?.canonical_asset_id ?? view.data?.asset_identity.asset_id ?? ""} onChange={e => { setCanonical(e.target.value); setConfirmed(false); }} required /></label>
        <p className="text-xs text-white/70">The default is the asset captured by this observation. Explicitly verify the asset; hostname or IP matching alone is insufficient. This does not merge asset rows.</p>
        <label className="block text-sm">Identity review reason<textarea className="mt-1 w-full rounded border border-white/20 bg-navy p-2" value={rationale} onChange={e => setRationale(e.target.value)} maxLength={2000} required /></label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} required />I verified the scanner instance and canonical asset for this observation.</label>
        <details><summary>Register a tool instance</summary>
          <p className="my-2 text-xs text-white/70">Registration saves a new Nessus namespace immediately; it does not bind this observation. Use the same instance for observations from the same scanner.</p>
          <label className="block text-sm">Tool instance name<input className="mt-1 w-full rounded border border-white/20 bg-navy p-2" maxLength={200} value={toolName} onChange={e => setToolName(e.target.value)} /></label>
          <button type="button" className={`${DIALOG_SECONDARY} mt-2`} disabled={!toolName.trim()} onClick={() => void run(async () => { const created = await api.post<Tool>(`/orgs/${orgId}/identity-tools`, { name: toolName.trim(), rationale: rationale.trim() }); setCreatedTool(created); setToolId(created.id); setConfirmed(false); setToolName(""); setOffset(0); })}>Register tool instance</button>
        </details>
        {selected && <button type="button" className="text-sm text-red-300 underline" onClick={() => setRetiring(selected)}>Retire selected tool instance</button>}
        {view.data?.identity_binding?.state === "bound" && <button type="button" className={DIALOG_SECONDARY} onClick={() => void run(() => api.post(path + "/revoke", { expected_version: view.data!.identity_binding!.version, rationale: rationale.trim() }), true)}>Revoke identity binding</button>}
      </fieldset>
      {retiring && <FindingActionDialog title="Retire identity tool" orgName={retiring.name} onClose={() => { if (!inFlight.current) setRetiring(null); }}><ConfirmPanel label="Retire identity tool" message={<>Retire <strong>{retiring.name}</strong>? All its identity bindings become unavailable. A retired namespace cannot be reused.</>} confirmLabel="Retire tool instance" danger busy={busy || disabled || stale} onCancel={() => setRetiring(null)} onConfirm={() => void run(async () => { await api.post(`/orgs/${orgId}/identity-tools/${retiring.id}/retire`, { expected_version: retiring.version, rationale: rationale.trim() }); setToolId(""); setConfirmed(false); }, true)} /></FindingActionDialog>}
      <footer className={DIALOG_FOOTER}><button type="button" disabled={busy || disabled} className={DIALOG_NEUTRAL} onClick={() => setOpen(false)}>Cancel identity review</button><button type="submit" className={DIALOG_PRIMARY} disabled={busy || disabled || stale || !!retiring || view.loading || tools.loading || !!view.error || !!tools.error}>Save identity binding</button></footer>
    </form>
  </section>;
}
