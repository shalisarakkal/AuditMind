"use client";

import { isRunning, useImports } from "@/context/ImportsContext";
import type { ArchiveAction, ArchiveProgress } from "@/lib/types";

type Labels = { idle: string; running: string; retry: string };

const LABELS: Record<ArchiveAction, Labels> = {
  archive: { idle: "Archive", running: "Archiving…", retry: "Retry archive" },
  restore: { idle: "Restore", running: "Restoring…", retry: "Retry restore" },
  purge: { idle: "Purge", running: "Purging…", retry: "Retry purge" },
};
// Restoring an archive that stopped part-way.
const UNDO: Labels = { idle: "Undo", running: "Undoing…", retry: "Undo" };

const STOPPED_TITLE = "Stopped part-way. Click to finish from where it stopped.";

/** Whether this browser follows a running `action` job on the item (archive)
 * or batch (restore, purge). */
function useFollowed(action: ArchiveAction, id: string | null | undefined): boolean {
  const { jobs } = useImports();
  return (
    !!id &&
    jobs.some((job) => isRunning(job) && job.action === action && (action === "archive" ? job.item_id : job.batch_id) === id)
  );
}

/** A row's Archive, Restore or Purge button, labelled with where the job
 * stands: "Archiving…" (disabled) while one runs, from the list or a job
 * this browser is following; "Retry archive" when one stopped part-way. */
export default function JobButton({
  action,
  itemId,
  name,
  progress,
  onClick,
  disabled = false,
  disabledTitle,
  labels = LABELS[action],
  idleTitle,
  className = "text-xs text-cyan hover:underline",
}: {
  action: ArchiveAction;
  /** The upload, asset or finding (archive), or the archived batch (restore, purge). */
  itemId: string;
  name: string;
  /** What the list says about this row's job. */
  progress: ArchiveProgress | null | undefined;
  onClick(): void;
  /** Unavailable for another reason (e.g. the upload is still importing). */
  disabled?: boolean;
  disabledTitle?: string;
  labels?: Labels;
  idleTitle?: string;
  className?: string;
}) {
  const followed = useFollowed(action, itemId);
  const state = followed ? "running" : (progress ?? "idle");
  const label = state === "running" ? labels.running : state === "stopped" ? labels.retry : labels.idle;
  const title = disabled && state !== "running" ? disabledTitle : state === "stopped" ? STOPPED_TITLE : idleTitle;

  return (
    <button
      type="button"
      aria-label={`${label.replace("…", "")} ${name}`}
      disabled={state === "running" || disabled}
      title={title}
      onClick={onClick}
      className={`${className} disabled:text-white/30 disabled:no-underline`}
    >
      {label}
    </button>
  );
}

/** A row's Archive button; when its archive stopped part-way, "Retry archive"
 * and "Undo" (bring back what it had archived). While either runs, only its
 * own button shows ("Archiving…" or "Undoing…"). */
export function ArchiveButtons({
  itemId,
  name,
  archiving,
  batchId,
  onArchive,
  onUndo,
  disabled = false,
  disabledTitle,
  className = "text-xs text-cyan hover:underline",
}: {
  itemId: string;
  name: string;
  archiving: ArchiveProgress | null | undefined;
  /** The unfinished archive's batch (to undo). */
  batchId: string | null | undefined;
  onArchive(): void;
  onUndo(batchId: string): void;
  disabled?: boolean;
  disabledTitle?: string;
  className?: string;
}) {
  const undoing = useFollowed("restore", batchId);
  const archivingNow = useFollowed("archive", itemId) || archiving === "running";
  return (
    <>
      {!undoing && (
        <JobButton
          action="archive"
          itemId={itemId}
          name={name}
          progress={archiving}
          onClick={onArchive}
          disabled={disabled}
          disabledTitle={disabledTitle}
          className={className}
        />
      )}
      {archiving === "stopped" && batchId && !archivingNow && (
        <JobButton
          action="restore"
          itemId={batchId}
          name={name}
          progress={null}
          labels={UNDO}
          idleTitle="Bring back what was archived before it stopped."
          onClick={() => onUndo(batchId)}
          className={undoing ? className : "ml-3 text-xs text-cyan hover:underline"}
        />
      )}
    </>
  );
}
