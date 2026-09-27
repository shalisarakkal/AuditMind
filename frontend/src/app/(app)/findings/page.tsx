"use client";

import { useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportReportPanel, { type ImportResult } from "@/components/ImportReportPanel";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { DOMAIN_LABELS, DOMAIN_ORDER, SEVERITY_BADGES, SEVERITY_ORDER, canWrite } from "@/lib/domain";
import type { Asset, Finding } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function FindingsPage() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const findings = useApi<Finding[]>(`/orgs/${org.id}/findings`);
  const assets = useApi<Asset[]>(`/orgs/${org.id}/assets`);
  const [result, setResult] = useState<ImportResult | null>(null);

  const hostById = new Map((assets.data ?? []).map((a) => [a.id, a.hostname ?? a.ip ?? "—"]));
  const list = findings.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Findings</h1>
          <p className="mt-1 text-sm text-white/60">
            {findings.data ? `${list.length} findings in ${org.name}, grouped by domain` : org.name}
          </p>
        </div>
        {canWrite(org.role) && (
          <ImportButton
            orgId={org.id}
            kind="findings"
            accept=".csv,.json,.nessus"
            label="Upload findings"
            onComplete={(r) => {
              setResult(r);
              findings.reload();
              assets.reload();
            }}
          />
        )}
      </div>

      {canWrite(org.role) && !result && (
        <p className="text-xs text-white/50">
          A native Nessus export (.nessus), or CSV/JSON with columns: hostname and/or ip, domain, severity, category,
          description, source.
        </p>
      )}
      {result && <ImportReportPanel result={result} onDismiss={() => setResult(null)} />}

      <StatusMessage loading={findings.loading && !findings.data} error={findings.error} />
      {findings.data && list.length === 0 && <p className="text-sm text-white/60">No findings yet.</p>}

      {DOMAIN_ORDER.map((domain) => {
        const inDomain = list
          .filter((f) => f.domain === domain)
          .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));
        if (inDomain.length === 0) return null;
        return (
          <section key={domain} aria-label={DOMAIN_LABELS[domain]}>
            <h2 className="mb-2 text-lg font-medium text-white">
              {DOMAIN_LABELS[domain]} <span className="text-sm font-normal text-white/50">({inDomain.length})</span>
            </h2>
            <div className="overflow-x-auto rounded-xl border border-white/10">
              <table className="w-full table-fixed text-left text-sm">
                <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
                  <tr>
                    <th className="w-28 px-4 py-2">Severity</th>
                    <th className="px-4 py-2">Finding</th>
                    <th className="w-56 px-4 py-2">Asset</th>
                    <th className="w-40 px-4 py-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {inDomain.map((f) => (
                    <tr key={f.id} className="border-t border-white/10 text-white/80">
                      <td className="px-4 py-2">
                        <span className={`rounded px-2 py-0.5 text-xs capitalize ${SEVERITY_BADGES[f.severity]}`}>
                          {f.severity}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <p className="text-white">{f.description ?? f.category ?? "—"}</p>
                        {f.description && f.category && <p className="text-xs text-white/50">{f.category}</p>}
                      </td>
                      <td className="px-4 py-2">{f.asset_id ? (hostById.get(f.asset_id) ?? "—") : "—"}</td>
                      <td className="px-4 py-2">{f.source ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
