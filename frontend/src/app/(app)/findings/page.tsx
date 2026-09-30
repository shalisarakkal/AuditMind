"use client";

import { Suspense, useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportStatus from "@/components/ImportStatus";
import { ArchiveButtons } from "@/components/JobButton";
import JobConfirm, { type JobRequest, undoRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import {
  DOMAIN_LABELS,
  DOMAIN_ORDER,
  SEARCH_BOX,
  SEVERITY_BADGES,
  SEVERITY_ORDER,
  canWrite,
  formatDateTime,
} from "@/lib/domain";
import type { Domain, FindingFacets, FindingListItem, FindingPage, ImportProfile } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const SEVERITY_OPTIONS = SEVERITY_ORDER.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }));
const DOMAIN_OPTIONS = DOMAIN_ORDER.map((d) => ({ value: d, label: DOMAIN_LABELS[d] }));

// The list reads its sort and filters from the page address.
export default function FindingsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Findings />
    </Suspense>
  );
}

function Findings() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<FindingPage>(`/orgs/${org.id}/findings?${list.apiQuery}`);
  const facets = useApi<FindingFacets>(`/orgs/${org.id}/findings/facets`);
  const profiles = useApi<ImportProfile[]>(writer ? `/orgs/${org.id}/import-profiles` : null);
  useReloadOnImport(reload);
  useReloadOnImport(facets.reload);
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  // Only findings added by hand are archived one by one; imported ones go
  // with their upload or asset (a re-import would bring them back).
  const archive = (f: FindingListItem) => {
    const name = f.description ?? f.category ?? "this finding";
    setConfirming({
      path: `/orgs/${org.id}/findings/${f.id}/archive`,
      label: `Archive ${name}`,
      message: (
        <>
          Archive <strong>{name}</strong>? It leaves every list and score. You can restore it from Archived until it&apos;s
          purged.
        </>
      ),
      confirmLabel: "Archive",
    });
  };

  const counts = page?.domain_counts ?? {};
  const allCount = Object.values(counts).reduce((sum, n) => sum + (n ?? 0), 0);
  const domains = list.values("domain") as Domain[];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Findings</h1>
          <p className="mt-1 text-sm text-white/60">
            {page && !list.hasFilters ? `${page.total.toLocaleString("en-US")} findings in ${org.name}` : org.name}
          </p>
        </div>
        {writer && (
          <ImportButton
            orgId={org.id}
            kind="findings"
            accept=".csv,.json,.nessus"
            label="Import data"
            profiles={profiles.data}
          />
        )}
      </div>

      {writer && (
        <p className="text-xs text-white/50">
          A native Nessus export (.nessus); CSV/JSON generic findings (hostname and/or ip, domain, severity, category,
          description, source); or a tool export such as an endpoint agent or network scan, which records the hosts as
          assets too. Pick the file, then its source.
        </p>
      )}
      <ImportStatus page="findings" />
      <JobStatus />
      {confirming && <JobConfirm request={confirming} onClose={() => setConfirming(null)} />}

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <TextFilter
            name="q"
            label="search"
            list={list}
            ariaLabel="Search findings"
            placeholder="Search all columns"
            className={SEARCH_BOX}
          />
          {list.hasFilters && (
            <button type="button" onClick={list.clearFilters} className="text-sm text-cyan hover:underline">
              Clear filters
            </button>
          )}
        </div>
        {page && (
          <div role="group" aria-label="Domain" className="flex flex-wrap gap-2">
            <DomainChip label="All" count={allCount} active={domains.length === 0} onClick={() => list.setValues("domain", [])} />
            {DOMAIN_ORDER.filter((d) => counts[d] || domains.includes(d)).map((d) => (
              <DomainChip
                key={d}
                label={DOMAIN_LABELS[d]}
                count={counts[d] ?? 0}
                active={domains.includes(d)}
                onClick={() => list.setValues("domain", [d])}
              />
            ))}
          </div>
        )}
      </div>

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full table-fixed text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
              <tr>
                <SortHeader label="Severity" column="severity" list={list} defaultSort="severity" className="w-32" />
                <SortHeader label="Finding" column="finding" list={list} />
                <SortHeader label="Domain" column="domain" list={list} className="w-44" />
                <SortHeader label="Asset" column="asset" list={list} className="w-44" />
                <SortHeader label="Source" column="source" list={list} className="w-36" />
                <SortHeader label="Added" column="created" list={list} className="w-40" />
                {writer && (
                  <th className="w-24 px-4 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
              <tr>
                <th className="px-4 pb-2">
                  <PickFilter name="severity" label="severity" list={list} options={SEVERITY_OPTIONS} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="finding" label="finding" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="domain" label="domain" list={list} options={DOMAIN_OPTIONS} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="asset" label="asset" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="source" label="source" list={list} options={facetOptions(facets.data?.source)} />
                </th>
                <th />
                {writer && <th />}
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 && (
                <tr className="border-t border-white/10">
                  <td colSpan={writer ? 7 : 6} className="px-4 py-6 text-center text-white/60">
                    {list.hasFilters ? "No findings match." : "No findings yet."}
                  </td>
                </tr>
              )}
              {page.items.map((f) => (
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
                  <td className="px-4 py-2">{DOMAIN_LABELS[f.domain]}</td>
                  <td className="truncate px-4 py-2" title={f.asset_cloud_id ?? undefined}>
                    {f.asset_hostname ?? f.asset_ip ?? f.asset_cloud_id ?? "—"}
                  </td>
                  <td className="truncate px-4 py-2">{f.source ?? "—"}</td>
                  <td className="px-4 py-2 text-xs text-white/60">{formatDateTime(f.created_at)}</td>
                  {writer && (
                    <td className="px-4 py-2 text-right">
                      {f.scan_id === null && (
                        <ArchiveButtons
                          itemId={f.id}
                          name={f.description ?? f.category ?? "finding"}
                          archiving={f.archiving}
                          batchId={f.archiving_batch_id}
                          onArchive={() => archive(f)}
                          onUndo={(batchId) => setConfirming(undoRequest(org.id, batchId, f.description ?? f.category ?? "finding"))}
                        />
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}

function DomainChip({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick(): void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
        active ? "border-cyan bg-cyan/10 text-cyan" : "border-white/15 text-white/70 hover:border-cyan hover:text-cyan"
      }`}
    >
      {label} ({count.toLocaleString("en-US")})
    </button>
  );
}
