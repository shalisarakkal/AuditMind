"use client";

import { useRef, useState } from "react";

import ConfirmPanel from "@/components/ConfirmPanel";
import { useImports } from "@/context/ImportsContext";
import type { ArchiveAction, ArchiveItemType } from "@/lib/types";
import type { Selection } from "@/lib/useSelection";

/** What a SelectionBar button asks to confirm. */
export type BulkRequest = {
  action: ArchiveAction;
  /** What the selected ids are, for archive. */
  itemType?: ArchiveItemType;
  label: string;
  message: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
};

/** Confirms an action on every selected row, then queues a job for each
 * (rows show "Queued…", then their own progress) and clears the selection.
 * Rows that couldn't start are listed with why. */
export default function BulkConfirm({ request, selection, onClose }: { request: BulkRequest; selection: Selection; onClose(): void }) {
  const { startBulk } = useImports();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refused, setRefused] = useState<{ name: string; detail: string }[] | null>(null);
  const inFlight = useRef(false);

  async function confirm() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const ids = selection.ids;
    const picked = selection.names(ids);
    const names = new Map(ids.map((id, i) => [id, picked[i]]));
    try {
      const result = await startBulk(request.action, ids, request.itemType);
      selection.clear();
      if (result.refused.length === 0) return onClose();
      setRefused(result.refused.map((r) => ({ name: names.get(r.id) ?? r.id, detail: r.detail })));
    } catch (err) {
      setError((err as Error).message);
    } finally { inFlight.current = false; }
    setBusy(false);
  }

  if (refused) {
    return (
      <div role="alert" className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-yellow-400/30 bg-yellow-400/5 p-3 text-sm text-yellow-100">
        <div>
          <p>
            {refused.length.toLocaleString("en-US")} of the selected couldn&apos;t start; the others are queued:
          </p>
          <ul className="mt-1 list-disc pl-5 text-xs">
            {refused.slice(0, 10).map((r, i) => (
              <li key={i}>
                {r.name}: {r.detail}
              </li>
            ))}
            {refused.length > 10 && <li>and {(refused.length - 10).toLocaleString("en-US")} more</li>}
          </ul>
        </div>
        <button type="button" onClick={onClose} className="text-xs text-white/60 hover:text-white">
          Dismiss
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <ConfirmPanel
        label={request.label}
        message={request.message}
        confirmLabel={request.confirmLabel}
        onConfirm={() => void confirm()}
        onCancel={onClose}
        busy={busy}
        danger={request.danger}
      />
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}

/** "3 assets", "1 upload". */
export function selectedText(count: number, noun: string): string {
  return `${count.toLocaleString("en-US")} ${count === 1 ? noun : `${noun}s`}`;
}
