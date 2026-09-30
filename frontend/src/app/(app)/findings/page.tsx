"use client";

import { Suspense, useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportStatus from "@/components/ImportStatus";
import BulkConfirm, { type BulkRequest, selectedText } from "@/components/BulkConfirm";
import { ArchiveButtons } from "@/components/JobButton";
import JobConfirm, { type JobRequest, undoRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import {
  ACTIONS_CELL,
  DateRangeFilter,
  EmptyRow,
  FilterChips,
  ListTable,
  ListToolbar,
  PageHeader,
  SELECT_CELL,
  SelectBox,
  SelectionAction,
  SelectionBar,
  SelectPageBox,
  THEAD,
} from "@/components/ListPage";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import {
  DOMAIN_LABELS,
  DOMAIN_ORDER,
  SEVERITY_BADGES,
  SEVERITY_ORDER,
  canWrite,
  formatDateTime,
} from "@/lib/domain";
import type { FindingFacets, FindingListItem, FindingPage, ImportProfile } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";
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
  const selection = useSelection(list, org.id);
  const [bulk, setBulk] = useState<BulkRequest | null>(null);
  const nameOf = (f: FindingListItem) => f.description ?? f.category ?? "finding";
  // Only findings added by hand, not being archived, can be picked.
  const pickable = (f: FindingListItem) => f.scan_id === null && f.archiving !== "running";
  const archiveSelected = () =>
    setBulk({
      action: "archive",
      itemType: "finding",
      label: "Archive selected findings",
      message: (
        <>
          Archive <strong>{selectedText(selection.count, "finding")}</strong>? They leave every list and score. Each can be
          restored from Archived until it&apos;s purged.
        </>
      ),
      confirmLabel: "Archive",
    });
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Findings"
        total={page?.total}
        noun="findings"
        orgName={org.name}
        filtered={list.hasFilters}
        note={
          writer &&
          "A native Nessus export (.nessus); CSV/JSON generic findings (hostname and/or ip, domain, severity, category, description, source); or a tool export such as an endpoint agent or network scan, which records the hosts as assets too. Pick the file, then its source."
        }
        action={
          writer && (
            <ImportButton orgId={org.id} kind="findings" accept=".csv,.json,.nessus" label="Upload file" profiles={profiles.data} />
          )
        }
      />
      <ImportStatus page="findings" />
      <JobStatus />
      {confirming && <JobConfirm request={confirming} onClose={() => setConfirming(null)} />}

      <div className="space-y-3">
        <ListToolbar list={list} label="findings">
          <DateRangeFilter list={list} label="Added" />
        </ListToolbar>
        {writer && (
          <SelectionBar selection={selection}>
            <SelectionAction onClick={archiveSelected}>Archive selected</SelectionAction>
          </SelectionBar>
        )}
        {bulk && <BulkConfirm request={bulk} selection={selection} onClose={() => setBulk(null)} />}
        {page && (
          <FilterChips list={list} name="domain" label="Domain" options={DOMAIN_OPTIONS} counts={page.domain_counts} />
        )}
      </div>

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable fixed>
            <thead className={THEAD}>
              <tr>
                {writer && (
                  <th className={SELECT_CELL}>
                    <SelectPageBox selection={selection} rows={page.items.filter(pickable).map((f) => ({ id: f.id, name: nameOf(f) }))} />
                  </th>
                )}
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
                {writer && <th />}
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
                <EmptyRow colSpan={writer ? 8 : 6} noun="findings" filtered={list.hasFilters} />
              )}
              {page.items.map((f) => (
                <tr key={f.id} className="border-t border-white/10 text-white/80">
                  {writer && (
                    <td className={SELECT_CELL}>
                      {f.scan_id === null && <SelectBox selection={selection} id={f.id} name={nameOf(f)} disabled={!pickable(f)} />}
                    </td>
                  )}
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
                    <td className={ACTIONS_CELL}>
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
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}
