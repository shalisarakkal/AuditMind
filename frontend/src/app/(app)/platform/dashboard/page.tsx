"use client";

import { useState } from "react";
import { SysadminOnly } from "@/components/SysadminOnly";
import StatusMessage from "@/components/StatusMessage";
import { useApi } from "@/lib/useApi";
import { api } from "@/lib/apiClient";

type Settings = { enabled: boolean; refresh_interval_seconds: number; version: number };

export default function DashboardSettingsPage() {
  return <SysadminOnly><DashboardSettings /></SysadminOnly>;
}

function DashboardSettings() {
  const [notice, setNotice] = useState(false);
  const { data, error, loading, reload } = useApi<Settings>("/platform/dashboard-settings");
  return <div className="min-w-0 space-y-6">
    <h1 className="text-2xl font-semibold">Dashboard settings</h1>
    <p className="text-sm text-white/70">Store Dashboard snapshots and refresh them in the background. Members can request a refresh; each organization shares one job. Evidence validity is still checked on every read.</p>
    <StatusMessage loading={loading} error={error} />
    <button type="button" onClick={reload} className="text-sm text-cyan underline">Reload settings</button>
    {notice && <p role="status">Dashboard settings saved.</p>}
    {data && <SettingsForm key={data.version} saved={data} reload={() => { setNotice(true); reload(); }} />}
  </div>;
}

function SettingsForm({ saved, reload }: { saved: Settings; reload(): void }) {
  const [enabled, setEnabled] = useState(saved.enabled);
  const [interval, setIntervalValue] = useState(String(saved.refresh_interval_seconds / 60));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  return <form className="space-y-4 rounded-xl border border-white/10 p-5" onSubmit={async event => {
    event.preventDefault(); if (busy || conflict) return;
    setBusy(true); setError(null);
    try {
      await api.patch("/platform/dashboard-settings", { enabled, refresh_interval_seconds: Number(interval) * 60, expected_version: saved.version });
      reload();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not save Dashboard settings";
      setError(message);
      if (typeof cause === "object" && cause !== null && "status" in cause && cause.status === 409) setConflict(true);
    } finally { setBusy(false); }
  }}>
    <label className="flex items-center gap-2"><input type="checkbox" checked={enabled} disabled={busy || conflict} onChange={event => setEnabled(event.target.checked)} />Use stored Dashboard snapshots</label>
    <label className="block text-sm">Refresh interval (minutes)
      <input type="number" min="1" max="1440" step="1" required value={interval} disabled={busy || conflict}
        onChange={event => setIntervalValue(event.target.value)} className="mt-1 block w-32 max-w-full rounded border border-white/20 bg-navy p-2" />
    </label>
    <p className="text-xs text-white/60">Default: 1 hour. Organizations inherit this interval unless their admin overrides it. Scheduled work is spread by up to 10% of the interval (maximum 5 minutes), then waits for worker capacity. Disabling returns to live reads; running refreshes finish safely.</p>
    <StatusMessage loading={busy} error={error} />
    {conflict && <p role="status">Reload settings before retrying. Your changes were not saved.</p>}
    <button disabled={busy || conflict} className="rounded-md bg-cyan px-4 py-2 text-navy disabled:opacity-60">Save Dashboard settings</button>
  </form>;
}
