"use client";

import { isRunning, useImports } from "@/context/ImportsContext";
import { ROW_ACTION } from "@/components/ListPage";
import type { ArchiveAction, ArchiveProgress } from "@/lib/types";

type Labels = { idle: string; running: string; done: string; retry: string };
type State = "idle" | "queued" | "running" | "done" | "stopped";

// Waiting its turn in the background worker (e.g. one of several selected).
const QUEUED = "Queued…";

const LABELS: Record<ArchiveAction, Labels> = {
  archive: { idle: "Archive", running: "Archiving…", done: "Archived", retry: "Retry archive" },
  restore: { idle: "Restore", running: "Restoring…", done: "Restored", retry: "Retry restore" },
  purge: { idle: "Purge", running: "Purging…", done: "Purged", retry: "Retry purge" },
};
// Restoring an archive that stopped part-way.
const UNDO: Labels = { idle: "Undo", running: "Undoing…", done: "Undone", retry: "Undo" };

const STOPPED_TITLE = "Stopped part-way. Click to finish from where it stopped.";

/** Where this browser's `action` job on the item (archive) or batch
 * (restore, purge) stands: "queued" while one it follows waits its turn,
 * "running" while one runs (or its request is still out), "done" just after
 * a small one finished, else null. */
function useFollowed(action: ArchiveAction, id: string | null | undefined): Exclude<State, "idle" | "stopped"> | null {
  const { jobs, requested } = useImports();
  if (!id) return null;
  // The endpoints end in /{item or batch id}/{action}.
  const asked = Object.entries(requested).find(([path]) => path.endsWith(`/${id}/${action}`))?.[1];
  const followed = jobs.find(
    (job) => isRunning(job) && job.action === action && (action === "archive" ? job.item_id : job.batch_id) === id,
  );
  if (followed) return followed.status === "pending" ? "queued" : "running";
  return asked === "starting" ? "running" : asked === "done" ? "done" : null;
}

/** A row's Archive, Restore or Purge button, labelled with where the job
 * stands: "Archiving…" (disabled) while one runs, from the list or a job
 * this browser is following or has just asked for; "Archived" (disabled)
 * once a small one is done, until the row leaves the list; "Retry archive"
 * when one stopped part-way. */
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
  className = ROW_ACTION,
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
  const state: State = useFollowed(action, itemId) ?? progress ?? "idle";
  const label = { idle: labels.idle, queued: QUEUED, running: labels.running, done: labels.done, stopped: labels.retry }[state];
  const busy = state === "queued" || state === "running" || state === "done";
  const title = disabled && !busy ? disabledTitle : state === "stopped" ? STOPPED_TITLE : idleTitle;

  return (
    <button
      type="button"
      aria-label={`${label.replace("…", "")} ${name}`}
      disabled={busy || disabled}
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
  className = ROW_ACTION,
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
  const undoing = useFollowed("restore", batchId) !== null;
  const archivingNow = useFollowed("archive", itemId) !== null || archiving === "running";
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
          disabled={disabled}
          disabledTitle={disabledTitle}
          idleTitle="Bring back what was archived before it stopped."
          onClick={() => onUndo(batchId)}
          className={className}
        />
      )}
    </>
  );
}
