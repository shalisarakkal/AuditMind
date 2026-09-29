"use client";

import { Fragment, Suspense, useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportStatus from "@/components/ImportStatus";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { ASSET_TYPE_LABELS, canWrite } from "@/lib/domain";
import { humanize } from "@/lib/importProfiles";
import type { Asset, AssetFacets, AssetType, ImportProfile, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const SEARCH =
  "w-full max-w-sm rounded-md border border-white/15 bg-navy px-3 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none";

// The list reads its sort and filters from the page address.
export default function AssetsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Assets />
    </Suspense>
  );
}

function Assets() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<Asset>>(`/orgs/${org.id}/assets?${list.apiQuery}`);
  const facets = useApi<AssetFacets>(`/orgs/${org.id}/assets/facets`);
  const profiles = useApi<ImportProfile[]>(writer ? `/orgs/${org.id}/import-profiles` : null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  useReloadOnImport(reload);
  useReloadOnImport(facets.reload);

  const assets = page?.items;
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
            {page && !list.hasFilters ? `${page.total.toLocaleString("en-US")} assets in ${org.name}` : org.name}
          </p>
        </div>
        {writer && (
          <ImportButton orgId={org.id} kind="assets" accept=".csv,.json" label="Import data" profiles={profiles.data} />
        )}
      </div>

      {writer && (
        <p className="text-xs text-white/50">
          CSV or JSON. Pick the file, then its source: a generic asset list (type, hostname and/or ip, environment,
          criticality, tags, cloud_id) or a tool export such as an endpoint agent, network scan or cloud inventory, which
          also records findings. The source is picked for you when the file&apos;s columns match a profile.
        </p>
      )}
      <ImportStatus page="assets" />

      <div className="flex flex-wrap items-center gap-3">
        <TextFilter
          name="q"
          label="search"
          list={list}
          ariaLabel="Search assets"
          placeholder="Search all columns"
          className={SEARCH}
        />
        {list.hasFilters && (
          <button type="button" onClick={list.clearFilters} className="text-sm text-cyan hover:underline">
            Clear filters
          </button>
        )}
      </div>

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
              <tr>
                <SortHeader label="Hostname" column="hostname" list={list} />
                <SortHeader label="IP" column="ip" list={list} />
                <SortHeader label="Cloud ID" column="cloud_id" list={list} />
                <SortHeader label="Type" column="type" list={list} />
                <SortHeader label="Subtype" column="subtype" list={list} />
                <SortHeader label="Environment" column="environment" list={list} />
                <SortHeader label="Criticality" column="criticality" list={list} />
                <th className="px-4 py-2">Tags</th>
                <th className="px-4 py-2">
                  <span className="sr-only">Details</span>
                </th>
              </tr>
              <tr>
                <th className="px-4 pb-2">
                  <TextFilter name="hostname" label="hostname" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="ip" label="IP" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="cloud_id" label="cloud ID" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="type" label="type" list={list} options={facetOptions(facets.data?.type, ASSET_TYPE_LABELS)} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="subtype" label="subtype" list={list} options={facetOptions(facets.data?.subtype)} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="environment" label="environment" list={list} options={facetOptions(facets.data?.environment)} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="criticality" label="criticality" list={list} options={facetOptions(facets.data?.criticality)} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="tags" label="tags" list={list} />
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {assets!.length === 0 && (
                <tr className="border-t border-white/10">
                  <td colSpan={9} className="px-4 py-6 text-center text-white/60">
                    {list.hasFilters ? "No assets match." : "No assets yet."}
                  </td>
                </tr>
              )}
              {assets!.map((a) => {
                const details = Object.entries(a.details ?? {});
                const open = expanded.has(a.id);
                return (
                  <Fragment key={a.id}>
                    <tr className="border-t border-white/10 text-white/80">
                      <td className="px-4 py-2 text-white">{a.hostname ?? "—"}</td>
                      <td className="px-4 py-2">{a.ip ?? "—"}</td>
                      <td className="max-w-56 truncate px-4 py-2" title={a.cloud_id ?? undefined}>
                        {a.cloud_id ?? "—"}
                      </td>
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
                            aria-label={`${open ? "Hide" : "Show"} details for ${a.hostname ?? a.ip ?? a.cloud_id}`}
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
                        <td colSpan={9} className="px-4 py-3">
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
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}
