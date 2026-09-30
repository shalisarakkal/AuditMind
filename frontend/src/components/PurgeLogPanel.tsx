"use client";

import { useState } from "react";

import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { countsText, formatDateTime } from "@/lib/domain";
import type { Page, PurgeLogEntry } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 50;
const REASONS: Record<PurgeLogEntry["reason"], string> = {
  manual: "Purged",
  auto: "Retention period over",
  duplicate: "Duplicates on restore",
};
const ITEM_TYPES: Record<PurgeLogEntry["item_type"], string> = { upload: "Upload", asset: "Asset", finding: "Finding" };

/** What was permanently deleted, by whom and when, newest first (admins). */
export default function PurgeLogPanel({ orgId }: { orgId: string }) {
  const [offset, setOffset] = useState(0);
  const { data: page, error, loading } = useApi<Page<PurgeLogEntry>>(
    `/orgs/${orgId}/purge-log?limit=${PAGE_SIZE}&offset=${offset}`,
  );

  return (
    <div className="space-y-3">
      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
              <tr>
                <th className="px-4 py-2">Purged</th>
                <th className="px-4 py-2">What</th>
                <th className="px-4 py-2">Rows deleted</th>
                <th className="px-4 py-2">Why</th>
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 && (
                <tr className="border-t border-white/10">
                  <td colSpan={4} className="px-4 py-6 text-center text-white/60">
                    Nothing has been purged.
                  </td>
                </tr>
              )}
              {page.items.map((entry) => (
                <tr key={entry.id} className="border-t border-white/10 text-white/80">
                  <td className="px-4 py-2 text-xs text-white/60">
                    {formatDateTime(entry.purged_at)}
                    <p>by {entry.purged_by ?? "the daily auto-purge"}</p>
                  </td>
                  <td className="px-4 py-2">
                    <span className="text-white">{entry.label}</span>
                    <p className="text-xs text-white/50">
                      {ITEM_TYPES[entry.item_type]}, archived {formatDateTime(entry.archived_at)}
                    </p>
                  </td>
                  <td className="px-4 py-2">{countsText(entry.counts)}</td>
                  <td className="px-4 py-2">{REASONS[entry.reason]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {page && <Pager offset={offset} limit={PAGE_SIZE} total={page.total} onChange={setOffset} />}
    </div>
  );
}
