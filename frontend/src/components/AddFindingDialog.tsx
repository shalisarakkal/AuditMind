"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { DOMAIN_LABELS, DOMAIN_ORDER, SEVERITY_ORDER } from "@/lib/domain";

const input = "mt-1 w-full rounded border border-white/20 bg-navy p-2 text-white";

export default function AddFindingDialog({ orgId, orgName, onClose, onSaved }: {
  orgId: string; orgName: string; onClose(): void; onSaved(): void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  useEffect(() => {
    const element = dialog.current!;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    return () => { element.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || uncertain) return;
    const data = new FormData(event.currentTarget);
    const description = String(data.get("description") || "").trim();
    if (!description) { setError("Enter a description."); return; }
    inFlight.current = true; setBusy(true); setError(null);
    try {
      await api.post(`/orgs/${orgId}/findings`, {
        domain: data.get("domain"), severity: data.get("severity"), description,
        category: String(data.get("category") || "").trim() || null, source: "manual",
      });
      onSaved(); onClose();
    } catch (err) {
      // Creation has no idempotency key: do not automatically retry an uncertain write.
      const unknown = !(err instanceof ApiError) || err.status >= 500;
      setUncertain(unknown);
      setError((err instanceof Error ? err.message : "Could not add finding") + (unknown ? ". Close this dialog and check the Findings list before trying again; the finding may have been created." : ""));
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <dialog ref={dialog} aria-labelledby={title} aria-modal="true"
    onCancel={event => { event.preventDefault(); if (!inFlight.current) onClose(); }}
    className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-xl overflow-y-auto rounded-xl border border-white/20 bg-navy p-5 text-white backdrop:bg-black/75">
    <header className="flex items-start justify-between gap-3"><div><h2 id={title} className="text-lg font-semibold">Add finding</h2><p className="text-sm text-white/70">{orgName}</p></div><button type="button" disabled={busy} onClick={onClose}>Close</button></header>
    <p className="my-3 text-sm text-white/70">Creates an organization-level manual finding, not an uploaded scan record. You can manage its workflow and archive it individually.</p>
    {error && <p role="alert" className="my-3 text-red-300">{error}</p>}
    <form onSubmit={save} aria-label="Add manual finding" aria-busy={busy}>
      <fieldset disabled={busy || uncertain} className="space-y-3">
        <label className="block text-sm">Domain<select name="domain" className={input}>{DOMAIN_ORDER.map(domain => <option key={domain} value={domain}>{DOMAIN_LABELS[domain]}</option>)}</select></label>
        <label className="block text-sm">Severity<select name="severity" defaultValue="medium" className={input}>{SEVERITY_ORDER.map(severity => <option key={severity} value={severity}>{severity[0].toUpperCase() + severity.slice(1)}</option>)}</select></label>
        <label className="block text-sm">Description<textarea name="description" required maxLength={2000} className={input} /></label>
        <label className="block text-sm">Category (optional)<input name="category" maxLength={255} className={input} /></label>
        <button type="submit" className="rounded bg-cyan px-4 py-2 text-navy disabled:opacity-50">{busy ? "Adding…" : "Add finding"}</button>
      </fieldset>
    </form>
  </dialog>;
}
