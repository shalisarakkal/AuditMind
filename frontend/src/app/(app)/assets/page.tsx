"use client";

import { Fragment, useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportReportPanel, { type ImportResult } from "@/components/ImportReportPanel";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { ASSET_TYPE_LABELS, canWrite } from "@/lib/domain";
import { humanize } from "@/lib/importProfiles";
import type { Asset, AssetType, ImportProfile } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AssetsPage() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const { data: assets, error, loading, reload } = useApi<Asset[]>(`/orgs/${org.id}/assets`);
  const profiles = useApi<ImportProfile[]>(writer ? `/orgs/${org.id}/import-profiles` : null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Assets</h1>
          <p className="mt-1 text-sm text-white/60">
            {assets ? `${assets.length} assets in ${org.name}` : org.name}
          </p>
        </div>
        {writer && (
          <ImportButton
            orgId={org.id}
            kind="assets"
            accept=".csv,.json"
            label="Import data"
            profiles={profiles.data}
            onComplete={(r) => {
              setResult(r);
              reload();
            }}
          />
        )}
      </div>

      {writer && !result && (
        <p className="text-xs text-white/50">
          CSV or JSON. Pick the file, then its source: a generic asset list (type, hostname and/or ip, environment,
          criticality, tags, cloud_id) or a tool export such as an endpoint agent, network scan or cloud inventory, which
          also records findings. The source is picked for you when the file&apos;s columns match a profile.
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
                <th className="px-4 py-2">Subtype</th>
                <th className="px-4 py-2">Environment</th>
                <th className="px-4 py-2">Criticality</th>
                <th className="px-4 py-2">Tags</th>
                <th className="px-4 py-2">
                  <span className="sr-only">Details</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => {
                const details = Object.entries(a.details ?? {});
                const open = expanded.has(a.id);
                return (
                  <Fragment key={a.id}>
                    <tr className="border-t border-white/10 text-white/80">
                      <td className="px-4 py-2 text-white">{a.hostname ?? "—"}</td>
                      <td className="px-4 py-2">{a.ip ?? "—"}</td>
                      <td className="px-4 py-2">{ASSET_TYPE_LABELS[a.type as AssetType] ?? a.type}</td>
                      <td className="px-4 py-2">{a.subtype ?? "—"}</td>
                      <td className="px-4 py-2">{a.environment ?? "—"}</td>
                      <td className="px-4 py-2 capitalize">{a.criticality ?? "—"}</td>
                      <td className="px-4 py-2">
                        {(a.tags ?? []).map((t) => (
                          <span key={t} className="mr-1 rounded bg-white/10 px-1.5 py-0.5 text-xs">
                            {t}
                          </span>
                        ))}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {details.length > 0 && (
                          <button
                            type="button"
                            aria-expanded={open}
                            aria-label={`${open ? "Hide" : "Show"} details for ${a.hostname ?? a.ip}`}
                            onClick={() => toggle(a.id)}
                            className="text-xs text-cyan hover:underline"
                          >
                            {open ? "Hide details" : "Details"}
                          </button>
                        )}
                      </td>
                    </tr>
                    {open && (
                      <tr className="bg-white/[0.03] text-white/80">
                        <td colSpan={8} className="px-4 py-3">
                          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
                            {details.map(([key, value]) => (
                              <div key={key} className="flex gap-2">
                                <dt className="text-white/50">{humanize(key)}</dt>
                                <dd className="text-white">{Array.isArray(value) ? value.join(", ") : String(value)}</dd>
                              </div>
                            ))}
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
