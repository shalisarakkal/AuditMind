"use client";

import { Suspense, useState } from "react";

import BulkConfirm, { type BulkRequest, selectedText } from "@/components/BulkConfirm";
import { ArchiveButtons } from "@/components/JobButton";
import JobConfirm, { type JobRequest, undoRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import { PickFilter, SortHeader, TextFilter } from "@/components/ListControls";
import {
  ACTIONS_CELL,
  DateRangeFilter,
  EmptyRow,
  FILTER_CELL,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW,
  SELECT_CELL,
  SelectBox,
  SelectionAction,
  SelectionBar,
  SelectPageBox,
  StatusBadge,
  TD,
  TH,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { isRunning } from "@/context/ImportsContext";
import { canWrite, formatDateTime, scanTypeLabel } from "@/lib/domain";
import { importCountsText } from "@/lib/importCounts";
import type { Page, Upload } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const COLUMNS = 7; // plus the checkboxes, for writers

/** What an import did, in a few words. */
function outcome(upload: Upload): string {
  if (isRunning(upload)) return upload.status === "pending" ? "Waiting…" : "Processing…";
  const s = upload.summary;
  if (!s) return "—";
  if (s.error) return s.error;
  return importCountsText(upload.scan_type, s) || "Nothing recorded";
}

// The list reads its sort and filters from the page address.
export default function UploadsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Uploads />
    </Suspense>
  );
}

function Uploads() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<Upload>>(`/orgs/${org.id}/uploads?${list.apiQuery}`);
  const facets = useApi<{ type: string[]; status: string[] }>(`/orgs/${org.id}/uploads/facets`);
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  const selection = useSelection(list, org.id);
  const [bulk, setBulk] = useState<BulkRequest | null>(null);
  useReloadOnImport(reload);
  useReloadOnImport(facets.reload);

  const archive = (upload: Upload) =>
    setConfirming({
      path: `/orgs/${org.id}/scans/${upload.id}/archive`,
      label: `Archive ${upload.filename ?? "upload"}`,
      message: (
        <>
          Archive <strong>{upload.filename ?? "this upload"}</strong>? Its findings, and the assets only it created, leave
          every list and score. You can restore it from Archived until it&apos;s purged.
        </>
      ),
      confirmLabel: "Archive",
    });

  // An upload still processing, or being archived, can't be picked.
  const pickable = (u: Upload) => !isRunning(u) && u.archiving !== "running";
  const archiveSelected = () =>
    setBulk({
      action: "archive",
      itemType: "upload",
      label: "Archive selected uploads",
      message: (
        <>
          Archive <strong>{selectedText(selection.count, "upload")}</strong>? Their findings, and the assets only they
          created, leave every list and score. Each can be restored from Archived until it&apos;s purged.
        </>
      ),
      confirmLabel: "Archive",
    });

  const typeOptions = (facets.data?.type ?? []).map((t) => ({ value: t, label: scanTypeLabel(t) }));
  const statusOptions = (facets.data?.status ?? []).map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }));

  return (
    <div className="space-y-6">
      <PageHeader title="Uploads" total={page?.total} noun="uploads" orgName={org.name} filtered={list.hasFilters} />
      <JobStatus />
      {confirming && <JobConfirm request={confirming} onClose={() => setConfirming(null)} />}
      <ListToolbar list={list} label="uploads">
        <DateRangeFilter list={list} label="Uploaded" />
      </ListToolbar>
      {writer && (
        <SelectionBar selection={selection}>
          <SelectionAction onClick={archiveSelected}>Archive selected</SelectionAction>
        </SelectionBar>
      )}
      {bulk && <BulkConfirm request={bulk} selection={selection} onClose={() => setBulk(null)} />}

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable>
          <thead className={THEAD}>
            <tr>
              {writer && (
                <th className={SELECT_CELL}>
                  <SelectPageBox
                    selection={selection}
                    rows={page.items.filter(pickable).map((u) => ({ id: u.id, name: u.filename ?? "upload" }))}
                  />
                </th>
              )}
              <SortHeader label="File" column="filename" list={list} />
              <SortHeader label="Type" column="type" list={list} />
              <SortHeader label="Uploaded by" column="uploaded_by" list={list} />
              <SortHeader label="Uploaded" column="started" list={list} defaultSort="started" defaultOrder="desc" />
              <SortHeader label="Status" column="status" list={list} />
              <th className={TH}>Result</th>
              <th className={TH}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
            <tr>
              {writer && <th />}
              <th className={FILTER_CELL}>
                <TextFilter name="filename" label="file" list={list} />
              </th>
              <th className={FILTER_CELL}>
                <PickFilter name="type" label="type" list={list} options={typeOptions} />
              </th>
              <th className={FILTER_CELL}>
                <TextFilter name="uploaded_by" label="uploaded by" list={list} />
              </th>
              <th />
              <th className={FILTER_CELL}>
                <PickFilter name="status" label="status" list={list} options={statusOptions} />
              </th>
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {page.items.length === 0 && <EmptyRow colSpan={COLUMNS + (writer ? 1 : 0)} noun="uploads" filtered={list.hasFilters} />}
            {page.items.map((u) => (
              <tr key={u.id} className={ROW}>
                {writer && (
                  <td className={SELECT_CELL}>
                    <SelectBox selection={selection} id={u.id} name={u.filename ?? "upload"} disabled={!pickable(u)} />
                  </td>
                )}
                <td className={`${TD} text-white`}>{u.filename ?? "—"}</td>
                <td className={TD}>{scanTypeLabel(u.scan_type)}</td>
                <td className={TD}>{u.uploaded_by ?? "—"}</td>
                <td className={`${TD} text-xs text-white/60`}>{formatDateTime(u.started_at)}</td>
                <td className={TD}>
                  <StatusBadge status={u.status} />
                </td>
                <td className={`${TD} text-xs text-white/60`}>{outcome(u)}</td>
                <td className={ACTIONS_CELL}>
                  {writer && (
                    <ArchiveButtons
                      itemId={u.id}
                      name={u.filename ?? "upload"}
                      archiving={u.archiving}
                      batchId={u.archiving_batch_id}
                      onArchive={() => archive(u)}
                      onUndo={(batchId) => setConfirming(undoRequest(org.id, batchId, u.filename ?? "upload"))}
                      disabled={isRunning(u)}
                      disabledTitle="Archive it once it has finished processing"
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}
