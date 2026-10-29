"use client";

import { Fragment, Suspense, useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportStatus from "@/components/ImportStatus";
import BulkConfirm, { type BulkRequest, selectedText } from "@/components/BulkConfirm";
import FindingActionDialog from "@/components/FindingActionDialog";
import { ArchiveButtons } from "@/components/JobButton";
import JobConfirm, { type JobRequest, undoRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import {
  ACTIONS_CELL,
  EmptyRow,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW_ACTION_VIEW,
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
import ListLoading from "@/components/ListLoading";
import { useApp } from "@/context/AppContext";
import { ASSET_TYPE_LABELS, canWrite } from "@/lib/domain";
import { humanize } from "@/lib/importProfiles";
import type { Asset, AssetFacets, AssetType, ImportProfile, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;

// The list reads its sort and filters from the page address.
export default function AssetsPage() {
  const { selectedOrg } = useApp();
  return (
    <Suspense fallback={<ListLoading label="assets" initial />}>
      <Assets key={selectedOrg?.id} />
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
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  const selection = useSelection(list, org.id);
  const [bulk, setBulk] = useState<BulkRequest | null>(null);
  useReloadOnImport(() => { selection.clear(); reload(); });
  useReloadOnImport(facets.reload);

  const assets = page?.items;
  const archive = (a: Asset) => {
    const name = a.hostname ?? a.ip ?? a.cloud_id ?? "this asset";
    setConfirming({
      path: `/orgs/${org.id}/assets/${a.id}/archive`,
      label: `Archive ${name}`,
      message: (
        <>
          Archive <strong>{name}</strong> and all its findings? They leave every list and score, and new uploads stop matching
          it. You can restore them from Archived until they&apos;re purged.
        </>
      ),
      confirmLabel: "Archive",
    });
  };
  const nameOf = (a: Asset) => a.hostname ?? a.ip ?? a.cloud_id ?? "asset";
  const archiveSelected = () =>
    setBulk({
      action: "archive",
      itemType: "asset",
      label: "Archive selected assets",
      message: (
        <>
          Archive <strong>{selectedText(selection.count, "asset")}</strong> and all their findings? They leave every list and
          score, and new uploads stop matching them. Each can be restored from Archived until it&apos;s purged.
        </>
      ),
      confirmLabel: "Archive",
    });
  const columns = writer ? 10 : 9;
  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="min-w-0 space-y-6 [overflow-wrap:anywhere]">
      <PageHeader
        title="Assets"
        total={page?.total}
        noun="assets"
        orgName={org.name}
        filtered={list.hasFilters}
        note={
          writer &&
          "CSV or JSON. Pick the file, then its source: a generic asset list (type, hostname and/or ip, environment, criticality, tags, cloud_id) or a tool export such as an endpoint agent, network scan or cloud inventory, which also records findings. The source is picked for you when the file's columns match a profile."
        }
        action={
          writer && <ImportButton orgId={org.id} kind="assets" accept=".csv,.json" label="Upload file" profiles={profiles.data} />
        }
      />
      <ImportStatus page="assets" />
      <JobStatus />
      {confirming && <FindingActionDialog title={confirming.label} orgName={org.name} onClose={() => setConfirming(null)}><JobConfirm request={confirming} onClose={() => setConfirming(null)} /></FindingActionDialog>}

      <ListToolbar list={list} label="assets" />
      {writer && (
        <SelectionBar selection={selection}>
          <SelectionAction onClick={archiveSelected}>Archive selected</SelectionAction>
        </SelectionBar>
      )}
      {bulk && <FindingActionDialog title={bulk.label} orgName={org.name} onClose={() => setBulk(null)}><BulkConfirm request={bulk} selection={selection} onClose={() => setBulk(null)} /></FindingActionDialog>}

      <StatusMessage loading={false} error={error} />
      {loading && <ListLoading label="assets" initial={!page} />}
      {error && <button type="button" onClick={reload} className="text-sm text-cyan underline">Retry assets</button>}
      {page && (
        <ListTable>
            <thead className={THEAD}>
              <tr>
                {writer && (
                  <th className={SELECT_CELL}>
                    <SelectPageBox
                      selection={selection}
                      rows={assets!.filter((a) => a.archiving !== "running").map((a) => ({ id: a.id, name: nameOf(a) }))}
                    />
                  </th>
                )}
                <SortHeader label="Hostname" column="hostname" list={list} />
                <SortHeader label="IP" column="ip" list={list} />
                <SortHeader label="Cloud ID" column="cloud_id" list={list} />
                <SortHeader label="Type" column="type" list={list} />
                <SortHeader label="Subtype" column="subtype" list={list} />
                <SortHeader label="Environment" column="environment" list={list} />
                <SortHeader label="Criticality" column="criticality" list={list} />
                <th className="px-4 py-2">Tags</th>
                <th className="px-4 py-2">
                  <span className="sr-only">Details and actions</span>
                </th>
              </tr>
              <tr>
                {writer && <th />}
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
                <EmptyRow colSpan={columns} noun="assets" filtered={list.hasFilters} />
              )}
              {assets!.map((a) => {
                const details = Object.entries(a.details ?? {});
                const open = expanded.has(a.id);
                return (
                  <Fragment key={a.id}>
                    <tr className="border-t border-white/10 text-white/80">
                      {writer && (
                        <td className={SELECT_CELL}>
                          <SelectBox selection={selection} id={a.id} name={nameOf(a)} disabled={a.archiving === "running"} />
                        </td>
                      )}
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
                      <td className={ACTIONS_CELL}>
                        {details.length > 0 && (
                          <button
                            type="button"
                            aria-expanded={open}
                            aria-label={`${open ? "Hide" : "Show"} details for ${a.hostname ?? a.ip ?? a.cloud_id}`}
                            onClick={() => toggle(a.id)}
                            className={ROW_ACTION_VIEW}
                          >
                            {open ? "Hide details" : "Details"}
                          </button>
                        )}
                        {writer && (
                          <ArchiveButtons
                            itemId={a.id}
                            name={a.hostname ?? a.ip ?? a.cloud_id ?? "asset"}
                            archiving={a.archiving}
                            batchId={a.archiving_batch_id}
                            onArchive={() => archive(a)}
                            disabled={selection.count > 0 || loading}
                            disabledTitle="Clear selection to use individual row actions."
                            onUndo={(batchId) => setConfirming(undoRequest(org.id, batchId, a.hostname ?? a.ip ?? a.cloud_id ?? "asset"))}
                          />
                        )}
                      </td>
                    </tr>
                    {open && (
                      <tr className="bg-white/[0.03] text-white/80">
                        <td colSpan={columns} className="px-4 py-3">
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
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}
