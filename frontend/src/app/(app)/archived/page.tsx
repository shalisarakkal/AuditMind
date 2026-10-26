"use client";

import { Fragment, Suspense, useState } from "react";

import BulkConfirm, { type BulkRequest, selectedText } from "@/components/BulkConfirm";
import JobButton from "@/components/JobButton";
import FindingActionDialog from "@/components/FindingActionDialog";
import JobConfirm, { type JobRequest } from "@/components/JobConfirm";
import ImportReportPanel from "@/components/ImportReportPanel";
import JobStatus from "@/components/JobStatus";
import { PickFilter, SortHeader, TextFilter } from "@/components/ListControls";
import {
  ACTIONS_CELL,
  DateRangeFilter,
  EmptyRow,
  FILTER_CELL,
  FilterChips,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW,
  ROW_ACTION_DANGER,
  ROW_ACTION_VIEW,
  SELECT_CELL,
  SelectBox,
  SelectionAction,
  SelectionBar,
  SelectPageBox,
  TD,
  TH,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { isRunning, scanResult, useImports } from "@/context/ImportsContext";
import { canWrite, countsText, formatDateTime, purgeCountdown } from "@/lib/domain";
import type { ArchivedItem, ArchivedPage, ArchiveItemType, Scan } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const COLUMNS = 7; // plus the checkboxes, for writers

const TYPE_LABELS: Record<ArchiveItemType, string> = { upload: "Upload", asset: "Asset", finding: "Finding" };
const TYPE_OPTIONS: { value: ArchiveItemType; label: string }[] = [
  { value: "upload", label: "Uploads" },
  { value: "asset", label: "Assets" },
  { value: "finding", label: "Findings" },
];

// The list reads its sort and filters (the type chips too) from the page
// address.
export default function ArchivedPage() {
  const { selectedOrg } = useApp();
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Archived key={selectedOrg?.id} />
    </Suspense>
  );
}

function Archived() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const admin = org.role === "admin";
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<ArchivedPage>(`/orgs/${org.id}/archive?${list.apiQuery}`);
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  const { jobs } = useImports();
  const selection = useSelection(list, org.id);
  const [bulk, setBulk] = useState<BulkRequest | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const busy = (item: ArchivedItem) => item.running !== null || jobs.some((j) => isRunning(j) && j.batch_id === item.id);
  const eligibility = (item: ArchivedItem) => ({ restore: !busy(item) && item.state !== "purging", purge: !busy(item) && item.state !== "restoring" });
  const canSelectAction = (action: "restore" | "purge") => selection.ids.every(id => {
    const current = page?.items.find(item => item.id === id);
    return current ? eligibility(current)[action] : selection.metadata(id)?.[action] === true && !jobs.some(j => isRunning(j) && j.batch_id === id);
  });
  const targetNames = selection.names(selection.ids);
  const targetSummary = <details className="my-2"><summary>Selected archived items ({selection.count})</summary><ul className="max-h-48 overflow-y-auto break-all text-xs">{selection.ids.map((id, i) => <li key={id}>{targetNames[i]} — {id}</li>)}</ul></details>;
  const restoreSelected = () =>
    setBulk({
      action: "restore",
      label: "Restore selected",
      message: (
        <>
          Restore <strong>{selectedText(selection.count, "archived item")}</strong>? Findings recorded again since they were
          archived are kept, and their archived copies purged.
          {targetSummary}
        </>
      ),
      confirmLabel: "Restore",
    });
  const purgeSelected = () =>
    setBulk({
      action: "purge",
      label: "Purge selected",
      message: (
        <>
          Permanently delete <strong>{selectedText(selection.count, "archived item")}</strong> and everything archived with
          them? This can&apos;t be undone.
          {targetSummary}
        </>
      ),
      confirmLabel: "Purge for good",
      danger: true,
    });
  useReloadOnImport(() => { selection.clear(); reload(); });

  const restore = (item: ArchivedItem) =>
    setConfirming({
      path: `/orgs/${org.id}/archive/${item.id}/restore`,
      label: `Restore ${item.label}`,
      message: (
        <>
          Restore <strong>{item.label}</strong> ({countsText(item.counts)})? Findings recorded again since it was archived
          are kept, and their archived copies purged.
        </>
      ),
      confirmLabel: "Restore",
    });
  const purge = (item: ArchivedItem) =>
    setConfirming({
      path: `/orgs/${org.id}/archive/${item.id}/purge`,
      label: `Purge ${item.label}`,
      message: (
        <>
          Permanently delete <strong>{item.label}</strong> ({countsText(item.counts)})? This can&apos;t be undone.
        </>
      ),
      confirmLabel: "Purge for good",
      danger: true,
    });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Archived"
        total={page?.total}
        noun="archived items"
        orgName={org.name}
        filtered={list.hasFilters}
        note="Archived items are hidden from every list and score, and purged automatically after the retention period set in Settings."
      />
      <JobStatus />
      {confirming && <FindingActionDialog title={confirming.label} orgName={org.name} onClose={() => setConfirming(null)}><JobConfirm request={confirming} onClose={() => setConfirming(null)} /></FindingActionDialog>}

      <div className="space-y-3">
        <ListToolbar list={list} label="archived items">
          <DateRangeFilter list={list} label="Archived" />
        </ListToolbar>
        {page && <FilterChips list={list} name="type" label="Type" options={TYPE_OPTIONS} counts={page.type_counts} />}
      </div>
      {writer && (
        <SelectionBar selection={selection}>
          <span>Actions for selected archived items</span>
          <SelectionAction disabled={loading || !canSelectAction("restore")} onClick={restoreSelected}>Restore selected</SelectionAction>
          {admin && (
            <SelectionAction disabled={loading || !canSelectAction("purge")} onClick={purgeSelected} danger>
              Purge selected
            </SelectionAction>
          )}
          <span className="text-xs text-white/60">Clear selection to use individual row actions. Restore is unavailable for purging items; Purge is unavailable for restoring items. No items are silently skipped.</span>
        </SelectionBar>
      )}
      {bulk && <FindingActionDialog title={bulk.label} orgName={org.name} onClose={() => setBulk(null)}><BulkConfirm request={bulk} selection={selection} onClose={() => setBulk(null)} /></FindingActionDialog>}

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable>
          <thead className={THEAD}>
            <tr>
              {writer && (
                <th className={SELECT_CELL}>
                  <SelectPageBox
                    selection={selection}
                    rows={page.items.filter((item) => !busy(item)).map((item) => ({ id: item.id, name: item.label, metadata: eligibility(item) }))}
                  />
                </th>
              )}
              <SortHeader label="Name" column="name" list={list} />
              <SortHeader label="Type" column="type" list={list} />
              <th className={TH}>Archived with it</th>
              <SortHeader label="Archived by" column="archived_by" list={list} />
              <SortHeader label="Archived" column="archived" list={list} defaultSort="archived" defaultOrder="desc" />
              <SortHeader label="Purge" column="purge" list={list} />
              <th className={`${TH} sticky right-0 z-10 bg-navy`}>
                Actions
              </th>
            </tr>
            <tr>
              {writer && <th />}
              <th className={FILTER_CELL}>
                <TextFilter name="name" label="name" list={list} />
              </th>
              <th className={FILTER_CELL}>
                <PickFilter name="type" label="type" list={list} options={TYPE_OPTIONS} />
              </th>
              <th />
              <th className={FILTER_CELL}>
                <TextFilter name="archived_by" label="archived by" list={list} />
              </th>
              <th />
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {page.items.length === 0 && <EmptyRow colSpan={COLUMNS + (writer ? 1 : 0)} noun="archived items" filtered={list.hasFilters} />}
            {page.items.map((item) => (
              <Fragment key={item.id}>
                <tr className={ROW}>
                  {writer && (
                    <td className={SELECT_CELL}>
                      <SelectBox selection={selection} id={item.id} name={item.label} metadata={eligibility(item)} disabled={busy(item)} />
                    </td>
                  )}
                  <td className={`${TD} text-white`}>{item.label}</td>
                  <td className={TD}>{TYPE_LABELS[item.item_type]}</td>
                  <td className={TD}>{countsText(item.counts)}</td>
                  <td className={TD}>{item.archived_by ?? "—"}</td>
                  <td className={`${TD} text-xs text-white/60`}>{formatDateTime(item.archived_at)}</td>
                  <td className={`${TD} text-xs text-white/60`}>
                    <div>{purgeCountdown(item.purge_at)}</div>
                    <div className="text-white/40">{formatDateTime(item.purge_at)}</div>
                  </td>
                  <td className={`${ACTIONS_CELL} sticky right-0 bg-navy`}>
                    {item.item_type === "upload" && (
                      <button
                        type="button"
                        aria-expanded={opened === item.id}
                        aria-label={`${opened === item.id ? "Hide" : "Show"} report for ${item.label}`}
                        onClick={() => setOpened(opened === item.id ? null : item.id)}
                        className={ROW_ACTION_VIEW}
                      >
                        {opened === item.id ? "Hide report" : "Report"}
                      </button>
                    )}
                    {writer && (
                      <RowActions
                        item={item}
                        busy={busy(item) || loading || selection.count > 0}
                        canPurge={admin}
                        onRestore={() => restore(item)}
                        onPurge={() => purge(item)}
                      />
                    )}
                  </td>
                </tr>
                {opened === item.id && (
                  <tr>
                    <td colSpan={COLUMNS + (writer ? 1 : 0)} className="px-4 pb-3">
                      <ArchivedReport orgId={org.id} batchId={item.id} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}

/** An archived upload's full report, read-only (no Retry or Dismiss): to
 * decide whether to restore or purge it. */
function ArchivedReport({ orgId, batchId }: { orgId: string; batchId: string }) {
  const { data: scan, error, loading } = useApi<Scan>(`/orgs/${orgId}/archive/${batchId}/report`);
  if (!scan) return <StatusMessage loading={loading} error={error} />;
  return <ImportReportPanel result={scanResult(scan)} />;
}

/** Restore and (admins) Purge. While a job runs on the item, its button reads
 * "Restoring…" or "Purging…" and the other is disabled; a restore or purge
 * that stopped part-way offers only "Retry restore" or "Retry purge". */
function RowActions({
  item,
  busy,
  canPurge,
  onRestore,
  onPurge,
}: {
  item: ArchivedItem;
  busy: boolean;
  canPurge: boolean;
  onRestore(): void;
  onPurge(): void;
}) {
  const progress = (action: "restore" | "purge") =>
    item.running === action ? "running" : item.state === (action === "restore" ? "restoring" : "purging") ? "stopped" : null;
  return (
    <>
      {item.state !== "purging" && (
        <JobButton
          action="restore"
          itemId={item.id}
          name={item.label}
          progress={progress("restore")}
          onClick={onRestore}
          disabled={busy}
        />
      )}
      {canPurge && item.state !== "restoring" && (
        <JobButton
          action="purge"
          itemId={item.id}
          name={item.label}
          progress={progress("purge")}
          onClick={onPurge}
          disabled={busy}
          className={ROW_ACTION_DANGER}
        />
      )}
    </>
  );
}
