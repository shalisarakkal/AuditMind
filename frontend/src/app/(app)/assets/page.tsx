"use client";

import { useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportReportPanel, { type ImportResult } from "@/components/ImportReportPanel";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { canWrite } from "@/lib/domain";
import type { Asset } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AssetsPage() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const { data: assets, error, loading, reload } = useApi<Asset[]>(`/orgs/${org.id}/assets`);
  const [result, setResult] = useState<ImportResult | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Assets</h1>
          <p className="mt-1 text-sm text-white/60">
            {assets ? `${assets.length} assets in ${org.name}` : org.name}
          </p>
        </div>
        {canWrite(org.role) && (
          <ImportButton
            orgId={org.id}
            kind="assets"
            accept=".csv,.json"
            label="Import assets"
            onComplete={(r) => {
              setResult(r);
              reload();
            }}
          />
        )}
      </div>

      {canWrite(org.role) && !result && (
        <p className="text-xs text-white/50">
          CSV or JSON with columns: type (server, workstation, network_device, database, cloud_resource, application),
          hostname and/or ip, environment, criticality, tags, cloud_id.
        </p>
      )}
      {result && <ImportReportPanel result={result} onDismiss={() => setResult(null)} />}

      <StatusMessage loading={loading && !assets} error={error} />
      {assets && assets.length === 0 && <p className="text-sm text-white/60">No assets yet.</p>}
      {assets && assets.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
              <tr>
                <th className="px-4 py-2">Hostname</th>
                <th className="px-4 py-2">IP</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Environment</th>
                <th className="px-4 py-2">Criticality</th>
                <th className="px-4 py-2">Tags</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id} className="border-t border-white/10 text-white/80">
                  <td className="px-4 py-2 text-white">{a.hostname ?? "—"}</td>
                  <td className="px-4 py-2">{a.ip ?? "—"}</td>
                  <td className="px-4 py-2">{a.type.replace("_", " ")}</td>
                  <td className="px-4 py-2">{a.environment ?? "—"}</td>
                  <td className="px-4 py-2 capitalize">{a.criticality ?? "—"}</td>
                  <td className="px-4 py-2">
                    {(a.tags ?? []).map((t) => (
                      <span key={t} className="mr-1 rounded bg-white/10 px-1.5 py-0.5 text-xs">
                        {t}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
