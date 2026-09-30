"use client";

import { Suspense, useState } from "react";

import { ArchiveButtons } from "@/components/JobButton";
import JobConfirm, { type JobRequest, undoRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import { SortHeader, TextFilter } from "@/components/ListControls";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { isRunning } from "@/context/ImportsContext";
import { SCAN_STATUS_BADGES, SEARCH_BOX, canWrite, formatDateTime, scanTypeLabel } from "@/lib/domain";
import type { Page, Upload } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;

/** What an import did, in a few words. */
function outcome(upload: Upload): string {
  if (isRunning(upload)) return "Importing…";
  const s = upload.summary;
  if (!s) return "—";
  if (s.error) return s.error;
  const parts = [
    s.created && `${s.created.toLocaleString("en-US")} created`,
    s.updated && `${s.updated.toLocaleString("en-US")} updated`,
    s.findings_created && `${s.findings_created.toLocaleString("en-US")} findings`,
    s.failed && `${s.failed.toLocaleString("en-US")} failed`,
  ].filter(Boolean);
  return parts.join(", ") || "Nothing imported";
}

// The list reads its sort and search from the page address.
export default function ImportsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Imports />
    </Suspense>
  );
}

function Imports() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<Upload>>(`/orgs/${org.id}/uploads?${list.apiQuery}`);
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  useReloadOnImport(reload);

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Imports</h1>
        <p className="mt-1 text-sm text-white/60">
          {page && !list.hasFilters ? `${page.total.toLocaleString("en-US")} uploads in ${org.name}` : org.name}
        </p>
      </div>
      <JobStatus />
      {confirming && <JobConfirm request={confirming} onClose={() => setConfirming(null)} />}

      <TextFilter
        name="q"
        label="search"
        list={list}
        ariaLabel="Search uploads"
        placeholder="File, type or uploader"
        className={SEARCH_BOX}
      />

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
              <tr>
                <SortHeader label="File" column="filename" list={list} />
                <SortHeader label="Type" column="type" list={list} />
                <SortHeader label="Uploaded by" column="uploaded_by" list={list} />
                <SortHeader label="Uploaded" column="started" list={list} />
                <SortHeader label="Status" column="status" list={list} />
                <th className="px-4 py-2">Result</th>
                {writer && (
                  <th className="px-4 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 && (
                <tr className="border-t border-white/10">
                  <td colSpan={writer ? 7 : 6} className="px-4 py-6 text-center text-white/60">
                    {list.hasFilters ? "No uploads match." : "No uploads yet."}
                  </td>
                </tr>
              )}
              {page.items.map((u) => (
                <tr key={u.id} className="border-t border-white/10 text-white/80">
                  <td className="px-4 py-2 text-white">{u.filename ?? "—"}</td>
                  <td className="px-4 py-2">{scanTypeLabel(u.scan_type)}</td>
                  <td className="px-4 py-2">{u.uploaded_by ?? "—"}</td>
                  <td className="px-4 py-2 text-xs text-white/60">{formatDateTime(u.started_at)}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs capitalize ${SCAN_STATUS_BADGES[u.status]}`}>{u.status}</span>
                  </td>
                  <td className="px-4 py-2 text-xs text-white/60">{outcome(u)}</td>
                  {writer && (
                    <td className="px-4 py-2 text-right">
                      <ArchiveButtons
                        itemId={u.id}
                        name={u.filename ?? "upload"}
                        archiving={u.archiving}
                        batchId={u.archiving_batch_id}
                        onArchive={() => archive(u)}
                        onUndo={(batchId) => setConfirming(undoRequest(org.id, batchId, u.filename ?? "upload"))}
                        disabled={isRunning(u)}
                        disabledTitle="Archive it once it has finished importing"
                      />
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
