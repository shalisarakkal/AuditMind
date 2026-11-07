"use client";

import { useState } from "react";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import StatusMessage from "./StatusMessage";

type Policy = { enabled: boolean; platform_enabled: boolean; enabled_override: boolean | null;
  version: number; platform_version: number };

export default function StatusScoringSettings({ orgId, editable }: { orgId?: string; editable: boolean }) {
  const path = orgId ? `/orgs/${orgId}/status-scoring` : "/platform/status-scoring";
  const { data, loading, error, reload } = useApi<Policy>(path);
  return <section className="min-w-0 space-y-3 rounded-xl border border-white/10 p-5" aria-label="Status-aware scoring">
    <h2 className="text-lg font-semibold">Status-aware scoring</h2>
    <p className="text-sm text-white/70">Only Resolved and False positive findings with current, administrator-approved evidence can be excluded from current risk. Open, Accepted risk and Mitigated retain full risk. Workflow notes alone do not authorize exclusions.</p>
    <StatusMessage loading={loading} error={error} />
    <button type="button" className="text-sm text-cyan underline" onClick={reload}>Reload saved policy</button>
    {data && <><p>Effective policy: {data.enabled ? "On" : "Off"}{orgId ? ` (Platform default: ${data.platform_enabled ? "On" : "Off"})` : ""}.</p>
      {editable ? <PolicyForm key={`${data.version}:${data.platform_version}`} path={path} saved={data} organization={!!orgId} onSaved={reload} />
        : <p className="text-sm text-white/60">Read-only: an administrator manages this policy.</p>}</>}
    <p className="text-xs text-white/60">This policy is separate from evidence-qualified scoring. Source severity, recorded totals and saved reports remain historical records.</p>
  </section>;
}

function PolicyForm({ path, saved, organization, onSaved }: { path: string; saved: Policy; organization: boolean; onSaved(): void }) {
  const [value, setValue] = useState(organization && saved.enabled_override === null ? "inherit" : (organization ? saved.enabled_override : saved.enabled) ? "on" : "off");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState(false);
  async function save() {
    setBusy(true); setError(null); setNotice(false);
    try {
      await api.patch(path, { expected_version: saved.version, ...(organization ? { enabled_override: value === "inherit" ? null : value === "on" } : { enabled: value === "on" }) });
      setNotice(true); onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save scoring policy");
      if (typeof cause === "object" && cause !== null && "status" in cause && cause.status === 409) setConflict(true);
    } finally { setBusy(false); }
  }
  return <form className="space-y-3" onSubmit={event => { event.preventDefault(); void save(); }}>
    <label className="block text-sm">{organization ? "Organization policy" : "Platform default"}
      <select aria-label={organization ? "Organization policy" : "Platform default"} className="mt-1 block w-full min-w-0 max-w-full rounded border border-white/20 bg-navy p-2" value={value} onChange={event => setValue(event.target.value)} disabled={busy || conflict}>
        {organization && <option value="inherit">Inherit Platform default</option>}<option value="on">On</option><option value="off">Off</option>
      </select></label>
    <StatusMessage loading={busy} error={error} />
    {conflict && <p role="status">Reload saved policy before retrying.</p>}
    {notice && <p role="status">Scoring policy saved.</p>}
    <button disabled={busy || conflict} className="rounded-md bg-cyan px-3 py-2 text-sm text-navy disabled:opacity-60">Save scoring policy</button>
  </form>;
}
