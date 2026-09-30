"use client";

import { Suspense, useState } from "react";

import JobButton from "@/components/JobButton";
import JobConfirm, { type JobRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import { TextFilter } from "@/components/ListControls";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { isRunning, useImports } from "@/context/ImportsContext";
import { SEARCH_BOX, canWrite, countsText, formatDateTime, purgeCountdown } from "@/lib/domain";
import type { ArchivedItem, ArchiveItemType, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;

const TABS: { type: ArchiveItemType; label: string; empty: string }[] = [
  { type: "upload", label: "Uploads", empty: "No archived uploads." },
  { type: "asset", label: "Assets", empty: "No archived assets." },
  { type: "finding", label: "Findings", empty: "No archived findings." },
];

// The search reads from the page address; the tab is kept on the page.
export default function ArchivedPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Archived />
    </Suspense>
  );
}

function Archived() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const admin = org.role === "admin";
  const [tab, setTab] = useState<ArchiveItemType>("upload");
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<ArchivedItem>>(
    `/orgs/${org.id}/archive?item_type=${tab}&${list.apiQuery}`,
  );
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  const { jobs } = useImports();
  useReloadOnImport(reload);
  const current = TABS.find((t) => t.type === tab)!;

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
      <div>
        <h1 className="text-2xl font-semibold text-white">Archived</h1>
        <p className="mt-1 text-sm text-white/60">
          Archived items are hidden from every list and score, and purged automatically after the retention period set in
          Settings. {admin ? "Restore or purge them here." : writer ? "Restore them here." : ""}
        </p>
      </div>
      <JobStatus />
      {confirming && <JobConfirm request={confirming} onClose={() => setConfirming(null)} />}

      <div role="tablist" aria-label="Archived items" className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.type}
            type="button"
            role="tab"
            aria-selected={t.type === tab}
            onClick={() => {
              setTab(t.type);
              setConfirming(null);
              list.setOffset(0);
            }}
            className={`rounded-full border px-3 py-1 text-sm transition-colors ${
              t.type === tab ? "border-cyan bg-cyan/10 text-cyan" : "border-white/15 text-white/70 hover:border-cyan hover:text-cyan"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <TextFilter name="q" label="search" list={list} ariaLabel="Search archived items" placeholder="Name" className={SEARCH_BOX} />

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Archived with it</th>
                <th className="px-4 py-2">Archived</th>
                <th className="px-4 py-2">Purge</th>
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
                  <td colSpan={writer ? 5 : 4} className="px-4 py-6 text-center text-white/60">
                    {list.hasFilters ? "Nothing matches." : current.empty}
                  </td>
                </tr>
              )}
              {page.items.map((item) => (
                <tr key={item.id} className="border-t border-white/10 text-white/80">
                  <td className="px-4 py-2 text-white">{item.label}</td>
                  <td className="px-4 py-2">{countsText(item.counts)}</td>
                  <td className="px-4 py-2 text-xs text-white/60">
                    {formatDateTime(item.archived_at)}
                    {item.archived_by && <p>by {item.archived_by}</p>}
                  </td>
                  <td className="px-4 py-2 text-xs text-white/60">{purgeCountdown(item.purge_at)}</td>
                  {writer && (
                    <td className="whitespace-nowrap px-4 py-2 text-right">
                      <RowActions
                        item={item}
                        busy={item.running !== null || jobs.some((j) => isRunning(j) && j.batch_id === item.id)}
                        canPurge={admin}
                        onRestore={() => restore(item)}
                        onPurge={() => purge(item)}
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
          className="ml-3 text-xs text-red-300 hover:underline"
        />
      )}
    </>
  );
}
