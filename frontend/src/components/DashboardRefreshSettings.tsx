"use client";

import { useState } from "react";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import StatusMessage from "./StatusMessage";

type Settings = { enabled: boolean; platform_refresh_interval_seconds: number; refresh_interval_seconds: number;
  refresh_interval_override_seconds: number | null; version: number };
const intervalLabel = (seconds: number) => `${seconds / 60} ${seconds === 60 ? "minute" : "minutes"}`;

export default function DashboardRefreshSettings({ orgId, editable }: { orgId: string; editable: boolean }) {
  const path = `/orgs/${orgId}/dashboard/settings`;
  const { data, loading, error, reload } = useApi<Settings>(path);
  const [notice, setNotice] = useState(false);
  return <section className="space-y-3 rounded-xl border border-white/10 p-5" aria-label="Dashboard refresh settings">
    <h2 className="text-lg font-semibold">Dashboard refresh</h2>
    <StatusMessage loading={loading} error={error} />
    <button type="button" onClick={() => { setNotice(false); reload(); }} className="text-sm text-cyan underline">Reload saved settings</button>
    {notice && <p role="status">Dashboard refresh interval saved.</p>}
    {data && <><p className="text-sm text-white/70">Platform default: {intervalLabel(data.platform_refresh_interval_seconds)}. Effective interval: {intervalLabel(data.refresh_interval_seconds)} ({data.refresh_interval_override_seconds === null ? "inherited" : "organization override"}).</p>
      {!data.enabled && <p className="text-sm text-white/60">Stored snapshots are disabled at Platform level. This interval will apply when enabled.</p>}
      {editable ? <IntervalForm key={`${data.version}:${data.platform_refresh_interval_seconds}`} saved={data} path={path} onSaved={() => { setNotice(true); reload(); }} />
        : <p className="text-sm text-white/60">Read-only: an organization administrator can change this interval.</p>}</>}
  </section>;
}

function IntervalForm({ saved, path, onSaved }: { saved: Settings; path: string; onSaved(): void }) {
  const [inherit, setInherit] = useState(saved.refresh_interval_override_seconds === null);
  const [minutes, setMinutes] = useState(String(saved.refresh_interval_seconds / 60));
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    if (busy || conflict) return;
    setBusy(true); setError(null);
    try {
      await api.patch(path, { expected_version: saved.version,
        refresh_interval_override_seconds: inherit ? null : Number(minutes) * 60 });
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save Dashboard refresh interval");
      if (typeof cause === "object" && cause !== null && "status" in cause && cause.status === 409) setConflict(true);
    } finally { setBusy(false); }
  }
  return <form className="space-y-3" onSubmit={event => { event.preventDefault(); void save(); }}>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={busy || conflict} checked={inherit} onChange={event => setInherit(event.target.checked)} />Inherit Platform refresh interval</label>
    {!inherit && <label className="block text-sm">Organization refresh interval (minutes)
      <input type="number" required min="1" max="1440" step="1" value={minutes} disabled={busy || conflict} onChange={event => setMinutes(event.target.value)} className="mt-1 block w-32 max-w-full rounded border border-white/20 bg-navy p-2" />
    </label>}
    <p className="text-xs text-white/60">Shorter intervals increase database work. Refresh dashboard remains available on demand. Scheduled work is staggered; interval changes do not cancel active jobs.</p>
    <StatusMessage loading={busy} error={error} />
    {conflict && <p role="status">Reload saved settings before retrying.</p>}
    <div className="flex flex-wrap gap-3">
      <button disabled={busy || conflict} className="rounded-md bg-cyan px-3 py-2 text-sm text-navy disabled:opacity-60">Save refresh interval</button>
    </div>
  </form>;
}
