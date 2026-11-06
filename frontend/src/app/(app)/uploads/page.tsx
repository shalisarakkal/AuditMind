"use client";

import { Fragment, Suspense, useState } from "react";

import BulkConfirm, { type BulkRequest, selectedText } from "@/components/BulkConfirm";
import ConfirmPanel from "@/components/ConfirmPanel";
import FindingActionDialog from "@/components/FindingActionDialog";
import ImportReportPanel from "@/components/ImportReportPanel";
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
  ROW_ACTION,
  ROW_ACTION_VIEW,
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
import ScanSnapshotDialog, { ScanSnapshotComparisonDialog } from "@/components/ScanSnapshotDialog";
import { useApp } from "@/context/AppContext";
import { isRunning, scanResult, useImports } from "@/context/ImportsContext";
import { canWrite, formatDateTime, scanTypeLabel } from "@/lib/domain";
import { importCountsText } from "@/lib/importCounts";
import type { Me, Page, Scan, Upload } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const COLUMNS = 7; // plus the checkboxes, for writers

/** What an import did, in a few words. */
function outcome(upload: Upload): string {
  if (isRunning(upload) && upload.abort_requested_at) return "Stopping… Waiting for rollback confirmation.";
  if (isRunning(upload)) return upload.status === "pending" ? "Waiting…" : "Processing…";
  const s = upload.summary;
  if (!s) return "—";
  if (s.error) return s.error;
  return importCountsText(upload.scan_type, s) || "Nothing recorded";
}

// The list reads its sort and filters from the page address.
export default function UploadsPage() {
  const { selectedOrg } = useApp();
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Uploads key={selectedOrg?.id} />
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
  const [opened, setOpened] = useState<string | null>(null);
  const [bulk, setBulk] = useState<BulkRequest | null>(null);
  const { retry, abort } = useImports();
  const me = useApi<Me>("/auth/me");
  const [abortTarget, setAbortTarget] = useState<Upload | null>(null);
  const [aborting, setAborting] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Upload | null>(null);
  const [baseline, setBaseline] = useState<{ id: string; name: string } | null>(null);
  const [comparison, setComparison] = useState<{ baselineId: string; currentId: string } | null>(null);
  useReloadOnImport(() => { selection.clear(); reload(); });
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

  // A failed large upload, run again from its kept file (the uploader or an
  // admin; the server says so to anyone else).
  const retryUpload = (upload: Upload) => {
    setRetrying(upload.id);
    setRetryError(null);
    retry(upload)
      .then(reload)
      .catch((err: Error) => setRetryError(`Couldn't retry ${upload.filename ?? "the upload"}: ${err.message}`))
      .finally(() => setRetrying(null));
  };

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
      {baseline && <div role="region" aria-label="Scan comparison baseline" className="flex flex-wrap items-center gap-3 rounded-lg border border-cyan/30 p-3 text-sm">
        <span className="min-w-0 break-words">Baseline: {baseline.name}. Open another upload&apos;s Snapshot to review against it.</span>
        <button type="button" className="text-cyan underline" onClick={() => setBaseline(null)}>Clear baseline</button>
      </div>}
      {snapshot && <ScanSnapshotDialog key={snapshot.id} orgId={org.id} orgName={org.name} scanId={snapshot.id} writer={writer}
        onClose={() => setSnapshot(null)} baselineId={baseline?.id}
        onBaseline={name => { setBaseline({ id: snapshot.id, name }); setSnapshot(null); }}
        onCompare={() => { if (baseline) { setComparison({ baselineId: baseline.id, currentId: snapshot.id }); setSnapshot(null); } }} />}
      {comparison && <ScanSnapshotComparisonDialog orgId={org.id} orgName={org.name} {...comparison} onClose={() => setComparison(null)} />}
      {confirming && <FindingActionDialog title={confirming.label} orgName={org.name} onClose={() => setConfirming(null)}><JobConfirm request={confirming} onClose={() => setConfirming(null)} /></FindingActionDialog>}
      <ListToolbar list={list} label="uploads">
        <DateRangeFilter list={list} label="Uploaded" />
      </ListToolbar>
      {writer && (
        <SelectionBar selection={selection}>
          <SelectionAction onClick={archiveSelected}>Archive selected</SelectionAction>
        </SelectionBar>
      )}
      {bulk && <FindingActionDialog title={bulk.label} orgName={org.name} onClose={() => setBulk(null)}><BulkConfirm request={bulk} selection={selection} onClose={() => setBulk(null)} /></FindingActionDialog>}

      {retryError && (
        <p role="alert" className="text-sm text-red-300">
          {retryError}
        </p>
      )}
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
              <Fragment key={u.id}>
                <tr className={ROW}>
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
                    <button type="button" className={ROW_ACTION_VIEW} aria-label={`Scan snapshot for ${u.filename ?? "upload"}`}
                      disabled={isRunning(u) || selection.count > 0 || loading || u.archiving === "running"}
                      title={selection.count ? "Clear selection to use individual row actions." : "Review or declare the source scan scope"}
                      onClick={() => setSnapshot(u)}>Snapshot</button>
                    {!isRunning(u) && (
                      <button
                        type="button"
                        aria-expanded={opened === u.id}
                        aria-label={`${opened === u.id ? "Hide" : "Show"} report for ${u.filename ?? "upload"}`}
                        onClick={() => setOpened(opened === u.id ? null : u.id)}
                        className={ROW_ACTION_VIEW}
                      >
                        {opened === u.id ? "Hide report" : "Report"}
                      </button>
                    )}
                    {writer && u.retryable && (
                      <button
                        type="button"
                        aria-label={`Retry ${u.filename ?? "upload"}`}
                        disabled={retrying === u.id || selection.count > 0 || loading}
                        onClick={() => retryUpload(u)}
                        className={ROW_ACTION}
                      >
                        {retrying === u.id ? "Retrying…" : "Retry"}
                      </button>
                    )}
                    {isRunning(u) && (org.role === "admin" || u.started_by === me.data?.id) && <button
                      type="button" className="text-xs text-red-300 hover:underline"
                      disabled={!!u.abort_requested_at || selection.count > 0 || loading}
                      onClick={() => { setRetryError(null); setAbortTarget(u); }}>
                      {u.abort_requested_at ? "Stopping…" : "Abort import"}
                    </button>}
                    {writer && (
                      <ArchiveButtons
                        itemId={u.id}
                        name={u.filename ?? "upload"}
                        archiving={u.archiving}
                        batchId={u.archiving_batch_id}
                        onArchive={() => archive(u)}
                        onUndo={(batchId) => setConfirming(undoRequest(org.id, batchId, u.filename ?? "upload"))}
                        disabled={isRunning(u) || selection.count > 0 || loading}
                        disabledTitle={selection.count ? "Clear selection to use individual row actions." : "Archive it once it has finished processing"}
                      />
                    )}
                  </td>
                </tr>
                {opened === u.id && (
                  <tr>
                    <td colSpan={COLUMNS + (writer ? 1 : 0)} className="px-4 pb-3">
                      <UploadReport orgId={org.id} scanId={u.id} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
      {abortTarget && <FindingActionDialog title="Abort import" orgName={org.name} onClose={() => { if (!aborting) setAbortTarget(null); }}>
        <ConfirmPanel label="Confirm abort import" confirmLabel="Abort import" danger busy={aborting}
          message={<>Abort <strong>{abortTarget.filename}</strong>? Unfinished writes will roll back. The uploaded file is kept for retry. Other jobs are not cancelled.</>}
          onCancel={() => setAbortTarget(null)} onConfirm={async () => {
            setAborting(true);
            try { await abort(abortTarget); setAbortTarget(null); reload(); }
            catch (err) { setRetryError(err instanceof Error ? err.message : "Could not request abort"); }
            finally { setAborting(false); }
          }} />
        {retryError && <p role="alert" className="mt-3 text-red-300">{retryError}</p>}
      </FindingActionDialog>}
    </div>
  );
}

/** A past upload's full report: counts, problems, warnings, and the rows
 * skipped or found to be duplicates. */
function UploadReport({ orgId, scanId }: { orgId: string; scanId: string }) {
  const { data: scan, error, loading } = useApi<Scan>(`/orgs/${orgId}/scans/${scanId}`);
  if (!scan) return <StatusMessage loading={loading} error={error} />;
  return <ImportReportPanel result={scanResult(scan)} />;
}
