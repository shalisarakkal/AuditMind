"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import FindingActionDialog from "@/components/FindingActionDialog";
import { useImports } from "@/context/ImportsContext";
import { ApiError, api } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
import { isFileDrop } from "@/lib/fileDrop";
import {
  GENERIC_ASSETS,
  GENERIC_FINDINGS,
  canRead,
  fileExtension,
  importTarget,
  readColumns,
  suggestProfile,
} from "@/lib/importProfiles";
import type { ImportProfile, ImportResponse, RepeatUpload } from "@/lib/types";

type ImportButtonProps = {
  orgId: string;
  /** Which page it's on: sets the default source (the generic asset list or
   * generic findings). */
  kind: "assets" | "findings";
  accept: string;
  label: string;
  /** Import profiles to choose from. Without them, a picked file is uploaded
   * straight away with the page's generic source. */
  profiles?: ImportProfile[] | null;
};

/** A picked file awaiting its source: the source its columns matched, if any,
 * and the columns read (for the "no source recognises this file" note). */
type Pending = { file: File; detected: string | null; columns: string[] };

/** A file the server says was already imported, awaiting "Import anyway". */
type Repeat = { file: File; profileKey: string; previous: RepeatUpload };
type UploadResult = "accepted" | "skipped" | "failed" | "duplicate" | "stopped";
type QueueState = { ready: boolean; failed: boolean; busy: boolean; duplicate: RepeatUpload | null; error: string | null };
type QueueControl = QueueState & { run(confirm?: boolean): Promise<UploadResult> };

/** Uploads a file. With profiles, the user confirms the file's source first
 * (pre-selected when the file's columns match a profile). The import is then
 * followed app-wide (ImportsContext): its progress and report show on the
 * page (ImportStatus), whichever page the user is on when it finishes. */
export default function ImportButton(props: ImportButtonProps) {
  return <ImportQueue key={props.orgId} {...props} />;
}

function ImportQueue(props: ImportButtonProps) {
  const [batch, setBatch] = useState<{ id: number; file: File; single: boolean }[]>([]);
  const picker = useRef<HTMLInputElement>(null);
  const dropArea = useRef<HTMLDivElement>(null);
  const receiveDrop = useRef<(files: File[]) => void>(() => {});
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const controls = useRef(new Map<number, QueueControl>());
  const [states, setStates] = useState<Record<number, QueueState>>({});
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [confirmClose, setConfirmClose] = useState(false);
  const [selectedDuplicates, setSelectedDuplicates] = useState<Set<number>>(new Set());
  const active = useRef(false);
  const stop = useRef(false);
  const register = useCallback((id: number, control: QueueControl) => {
    controls.current.set(id, control);
    const state = { ready: control.ready, failed: control.failed, busy: control.busy, duplicate: control.duplicate, error: control.error };
    setStates(previous => previous[id]?.ready === state.ready && previous[id]?.failed === state.failed && previous[id]?.busy === state.busy && previous[id]?.duplicate === state.duplicate && previous[id]?.error === state.error
      ? previous : { ...previous, [id]: state });
  }, []);
  useEffect(() => () => { stop.current = true; }, []);
  const ready = batch.filter(item => states[item.id]?.ready);
  const failed = ready.filter(item => states[item.id]?.failed);
  const freshReady = ready.filter(item => !states[item.id]?.failed);
  const duplicates = batch.filter(item => states[item.id]?.duplicate);
  const duplicateTargets = duplicates.filter(item => selectedDuplicates.has(item.id));
  const attention = batch.filter(item => !states[item.id]?.ready && !states[item.id]?.busy && !states[item.id]?.duplicate);
  const anyBusy = Object.values(states).some(state => state.busy);
  useEffect(() => {
    if (batch.length || !progress) return;
    const timer = setTimeout(() => setProgress(""), 3000);
    return () => clearTimeout(timer);
  }, [batch.length, progress]);
  function remove(id: number) {
    controls.current.delete(id);
    setStates(previous => { const next = { ...previous }; delete next[id]; return next; });
    setBatch(previous => previous.filter(row => row.id !== id));
    setSelectedDuplicates(previous => { const next = new Set(previous); next.delete(id); return next; });
  }
  function cancelQueue() {
    if (active.current || anyBusy) return;
    setConfirmClose(false);
    setBatch([]);
    controls.current.clear();
    setStates({});
    setSelectedDuplicates(new Set());
    setProgress("");
    setError(null);
  }
  function skipDuplicates() {
    if (active.current || anyBusy) return;
    duplicateTargets.forEach(item => remove(item.id));
  }
  async function runBatch(mode: "ready" | "failed" | "duplicates" = "ready") {
    if (active.current || anyBusy) return;
    const targets = mode === "duplicates" ? duplicateTargets : mode === "failed" ? failed : freshReady;
    if (!targets.length) return;
    active.current = true;
    stop.current = false;
    setRunning(true);
    let submitted = 0;
    let rejected = 0;
    let repeated = 0;
    let skipped = 0;
    try {
      for (const item of targets) {
        if (stop.current) break;
        setProgress(`Submitting ${submitted + rejected + repeated + skipped + 1} of ${targets.length}: ${item.file.name}`);
        const result = await controls.current.get(item.id)?.run(mode === "duplicates");
        if (result === "duplicate") { repeated++; continue; }
        if (result === "skipped") { skipped++; continue; }
        if (result === "accepted") submitted++;
        else if (result === "failed") rejected++;
        else break;
      }
      setProgress(`Last upload attempt: ${submitted} submitted; ${rejected} failed; ${repeated} already uploaded; ${skipped} skipped. ${stop.current ? "Stopped. Remaining files have not been submitted." : "Review any remaining files in this dialog."} Submitted files are processed in the background. View their progress and reports on the page.`);
    } finally {
      active.current = false;
      setRunning(false);
    }
  }
  function receive(files: File[], singleSelection = true) {
    if (active.current || anyBusy) return;
    if (files.length > 20 || batch.length + files.length > 20) { setError("Choose at most 20 files at a time."); return; }
    setError(null);
    const additions = files.map(file => ({ id: ++sequence.current, file, single: singleSelection && files.length === 1 }));
    setBatch(previous => [...previous, ...additions]);
  }
  useEffect(() => { receiveDrop.current = files => receive(files, false); });
  useEffect(() => {
    const receivePageDrop = (event: DragEvent) => {
      if (!isFileDrop(event)) return;
      event.preventDefault();
      // Do not open an upload queue over a different action/confirmation modal.
      const modal = document.querySelector("dialog[open]");
      if (modal && !dropArea.current?.contains(modal)) return;
      receiveDrop.current(Array.from(event.dataTransfer!.files));
    };
    const allowFileDrop = (event: DragEvent) => { if (isFileDrop(event)) event.preventDefault(); };
    document.addEventListener("dragover", allowFileDrop);
    document.addEventListener("drop", receivePageDrop);
    return () => {
      document.removeEventListener("dragover", allowFileDrop);
      document.removeEventListener("drop", receivePageDrop);
    };
  }, []);
  return <div ref={dropArea} aria-label="File upload area" onDragOver={event => { if (isFileDrop(event.nativeEvent)) event.preventDefault(); }} onDrop={event => {
    if (!isFileDrop(event.nativeEvent)) return;
    event.preventDefault(); event.stopPropagation(); receive(Array.from(event.dataTransfer.files), false);
  }} className="self-start">
    <input ref={picker} type="file" multiple accept={props.accept} className="hidden" data-testid={`${props.kind}-file-input`} disabled={running || anyBusy}
      onChange={event => { receive(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
    <button type="button" disabled={running || anyBusy || batch.length > 0} onClick={() => picker.current?.click()}
      className="h-10 rounded-md bg-cyan px-4 text-sm font-medium text-navy disabled:opacity-60">{props.label}</button>
    {batch.length > 0 && <FindingActionDialog title="Upload files" orgName="Review each file's source before uploading. Up to 20 files; each has its own report."
      onClose={() => setConfirmClose(true)}>
    <div aria-busy={running || anyBusy} className="space-y-3">
    {confirmClose && <section role="alert" className="rounded-lg border border-amber-300/40 p-3 text-sm">
      <p>Close and remove all remaining files from this queue? Submitted imports will not be cancelled.</p>
      <div className="mt-2 flex gap-4">
        <button type="button" onClick={cancelQueue} className="text-cyan">Close and remove queued files</button>
        <button type="button" onClick={() => setConfirmClose(false)} className="text-cyan">Keep reviewing</button>
      </div>
    </section>}
    <p className="text-xs text-white/60">Ready: {ready.length - failed.length} · Submission failed: {failed.length} · Already uploaded: {duplicates.length} · Source needs attention: {attention.length}</p>
    {[
      { title: "Ready files", items: freshReady },
      { title: "Submission failed", items: failed },
      { title: "Source needs attention", items: attention },
      { title: "Submitting", items: batch.filter(item => states[item.id]?.busy) },
      { title: "", items: duplicates },
    ].flatMap(group => [
      ...(group.title && group.items.length ? [<h3 key={`heading-${group.title}`} className="text-sm font-medium text-white/80">{group.title} ({group.items.length})</h3>] : []),
      ...group.items.map(item => <SingleImportButton {...props} key={`${props.orgId}-${item.id}`} initialFile={item.file}
      shortSourceLabel={item.single} autoUpload={item.single && props.profiles !== null && !props.profiles?.length}
      locked={running} register={control => register(item.id, control)}
      onSkipped={reason => setProgress(`Skipped ${item.file.name}: ${reason}`)}
      onSettled={() => remove(item.id)} />),
    ])}
    {duplicates.length > 0 && <section aria-label="Already uploaded files" className="space-y-3 rounded-lg border border-amber-300/30 bg-amber-300/5 p-3">
      <h3 className="font-medium text-amber-200">Already uploaded ({duplicates.length})</h3>
      <p className="text-xs text-white/70">Other ready files have not been blocked. Select files to skip or upload again. Upload anyway starts another import; it does not promise to update existing records.</p>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={running || anyBusy} checked={duplicates.length > 0 && duplicateTargets.length === duplicates.length}
        onChange={event => setSelectedDuplicates(event.target.checked ? new Set(duplicates.map(item => item.id)) : new Set())} />Select all already uploaded files</label>
      {duplicates.map(item => {
        const previous = states[item.id].duplicate!;
        return <div key={item.id} className="rounded border border-white/10 p-2">
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={running || anyBusy} checked={selectedDuplicates.has(item.id)}
            onChange={event => setSelectedDuplicates(current => { const next = new Set(current); if (event.target.checked) next.add(item.id); else next.delete(item.id); return next; })} /><span className="min-w-0 break-all">{item.file.name}</span></label>
          <p className="mt-1 text-xs text-white/60">Previously uploaded by {previous.imported_by}{previous.imported_at ? ` on ${formatDateTime(previous.imported_at)}` : ""}</p>
          {states[item.id].error && <p role="alert" className="text-xs text-red-300">{states[item.id].error}</p>}
        </div>;
      })}
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={running || anyBusy || !duplicateTargets.length} onClick={skipDuplicates} className="text-sm text-white/70 disabled:opacity-60">Skip selected ({duplicateTargets.length})</button>
        <button type="button" disabled={running || anyBusy || !duplicateTargets.length} onClick={() => void runBatch("duplicates")} className="rounded-md border border-cyan px-3 py-2 text-sm text-cyan disabled:opacity-60">Upload selected anyway ({duplicateTargets.length})</button>
      </div>
    </section>}
    {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    <div className="flex flex-wrap items-center justify-end gap-3 border-t border-white/10 pt-4">
      <button type="button" data-confirm-cancel disabled={running || anyBusy} onClick={() => setConfirmClose(true)} className="text-sm text-white/70 disabled:opacity-60">Close</button>
      {(freshReady.length > 0 || running) && <button type="button" disabled={running || anyBusy || !freshReady.length} onClick={() => void runBatch()}
        className="rounded-md bg-cyan px-3 py-2 text-sm font-medium text-navy disabled:opacity-60">Upload all ready files ({freshReady.length})</button>}
      {failed.length > 0 && <button type="button" disabled={running || anyBusy} onClick={() => void runBatch("failed")} className="text-sm text-cyan disabled:opacity-60">Retry failed ({failed.length})</button>}
      {running && <button type="button" onClick={() => { stop.current = true; setProgress("Stopping after the current submission. Accepted uploads are not cancelled."); }} className="text-sm text-cyan">Stop remaining uploads</button>}
    </div>
    {progress && <p role="status" className="text-right text-sm text-white/60">{progress}</p>}
    </div>
    </FindingActionDialog>}
    {!batch.length && error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    {!batch.length && progress && <p role="status" className="fixed bottom-4 right-4 z-50 max-w-md rounded-lg border border-cyan/30 bg-navy p-3 text-sm text-white shadow-lg">{progress}</p>}
  </div>;
}

function SingleImportButton({ orgId, kind, profiles, initialFile, onSettled, onSkipped, locked = false, register, shortSourceLabel = false, autoUpload = false }: ImportButtonProps & {
  initialFile: File; onSettled?(): void;
  onSkipped?(reason: string): void;
  locked?: boolean; register?(control: QueueControl): void;
  shortSourceLabel?: boolean; autoUpload?: boolean;
}) {
  const imports = useImports();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [repeat, setRepeat] = useState<Repeat | null>(null);
  const [source, setSource] = useState(kind === "assets" ? GENERIC_ASSETS : GENERIC_FINDINGS);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const pageDefault = kind === "assets" ? GENERIC_ASSETS : GENERIC_FINDINGS;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  /** `confirm`: import even if this exact file was imported before. */
  async function upload(file: File, profileKey: string, confirm = false): Promise<UploadResult> {
    // A second click that lands before the re-render hides the confirm
    // button must not upload the file again.
    if (inFlight.current || !mounted.current) return "stopped";
    inFlight.current = true;
    const previousRepeat = repeat;
    setRepeat(null);
    setError(null);
    setUploading(true);
    let response: ImportResponse;
    try {
      const { path, fields } = importTarget(orgId, profileKey);
      response = await api.upload<ImportResponse>(path, file, confirm ? { ...fields, confirm: "true" } : fields);
      setPending(null);
    } catch (err) {
      if (!mounted.current) return "stopped";
      if (err instanceof ApiError && err.status === 409 && isRepeatUpload(err.detail)) {
        // Already imported: a warning, the user decides.
        setRepeat({ file, profileKey, previous: err.detail });
        setPending(null);
        return "duplicate";
      }
      // The upload itself failed (e.g. an unsupported file): nothing to track.
      setError(`${file.name}: ${(err as Error).message}`);
      if (confirm && previousRepeat) setRepeat(previousRepeat);
      return "failed";
    } finally {
      inFlight.current = false;
      if (mounted.current) setUploading(false);
    }
    // Accepted: the import is followed from here on, wherever the user goes.
    if (!mounted.current) return "accepted";
    if (response.skipped) {
      // The matching scan may belong to another uploader: do not track/show its
      // report or imply that a new import was created.
      onSkipped?.(response.skip_reason ?? "Exact duplicate file");
      onSettled?.();
      return "skipped";
    }
    // Tracking cannot turn an accepted submission into a retryable upload.
    try { await imports.track(response.scan_id, kind); } catch { /* The server owns the accepted job. */ }
    onSettled?.();
    return "accepted";
  }

  async function handleFile(file: File) {
    setError(null); // a new file: the last one's error no longer applies
    if (!profiles?.length) {
      if (initialFile && !autoUpload) { setPending({ file, detected: null, columns: [] }); return; }
      await upload(file, pageDefault);
      return;
    }
    if (fileExtension(file.name) === ".nessus") {
      setSource(GENERIC_FINDINGS);
      setPending({ file, detected: null, columns: [] });
      return;
    }
    const columns = await readColumns(file);
    const detected = suggestProfile(columns, profiles);
    if (!mounted.current) return;
    setSource(detected?.key ?? pageDefault);
    setPending({ file, detected: detected?.key ?? null, columns });
  }

  const started = useRef(false);
  useEffect(() => {
    if (!initialFile || started.current || profiles === null) return;
    started.current = true;
    void handleFile(initialFile);
  }, [initialFile, profiles]);

  const busy = uploading;
  const nessus = pending !== null && fileExtension(pending.file.name) === ".nessus";
  const choices = nessus ? (profiles ?? []).filter((p) => p.key === GENERIC_FINDINGS) : sortedChoices(profiles ?? [], pageDefault);
  // Import only with a source that can identify the file's rows.
  const selected = choices.find((p) => p.key === source);
  const columns = pending?.columns ?? [];
  const readable = !selected || canRead(selected, columns);
  const noSourceReads = !readable && choices.every((p) => !canRead(p, columns));
  useEffect(() => {
    register?.({ ready: pending !== null && readable && !uploading && repeat === null, failed: error !== null, busy: uploading, duplicate: repeat?.previous ?? null, error,
      run: (confirm = false) => repeat ? upload(repeat.file, repeat.profileKey, confirm) : pending ? upload(pending.file, source) : Promise.resolve("stopped") });
  });

  if (repeat) return null;
  return (
    <div className="flex flex-col gap-2">
      {initialFile && uploading && <p role="status" className="text-sm text-white/60"><span>Uploading…</span> {initialFile.name}</p>}
      {initialFile && error && <button type="button" disabled={locked} onClick={onSettled} className="text-xs text-cyan">Dismiss {initialFile.name}</button>}

      {error && (
        <p role="alert" className="max-w-md text-right text-sm text-red-300">
          {error}
        </p>
      )}

      {pending && (
        <div
          role="group"
          aria-label="Upload options"
          className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-sm"
        >
          <span className="min-w-0 flex-1 basis-40 break-all font-medium text-white" title={pending.file.name}>
            {pending.file.name}
          </span>
          <span className={`text-xs ${error ? "text-red-300" : readable ? "text-emerald-300" : "text-amber-200"}`}>{error ? "Submission failed" : readable ? "Ready" : "Source needs attention"}</span>
          <label className="text-white/60">
            Source
          <select
            aria-label={initialFile && !shortSourceLabel ? `Source for ${initialFile.name}` : "Source"}
            value={source}
            disabled={locked || busy}
            onChange={(e) => setSource(e.target.value)}
            className="max-w-64 rounded-md border border-white/15 bg-navy px-2 py-1 text-sm text-white focus:border-cyan focus:outline-none"
          >
            {choices.map((p) => (
              <option key={p.key} value={p.key}>
                {p.builtin ? p.name : `${p.name} (${p.family_label})`}
              </option>
            ))}
          </select>
          </label>
          {pending.detected && source === pending.detected && (
            <span title="Detected from the file's columns" className="rounded bg-emerald-400/10 px-2 py-1 text-xs text-emerald-300">Detected</span>
          )}
          {!readable && (
            <p role="note" className="basis-full text-right text-xs text-amber-300">
              {noSourceReads ? (
                <>
                  No supported source matches this file&apos;s columns ({shortList(columns)}). Configure a compatible import profile in Settings, convert the file to a supported format, or remove it from this queue.
                </>
              ) : (
                <>
                  {selected!.name} cannot read this file. Select a compatible source from the Source list.
                </>
              )}
            </p>
          )}
          <button
            type="button"
            disabled={locked || busy || !readable}
            onClick={() => void upload(pending.file, source)}
            title={!readable ? "Select a compatible source to upload" : undefined}
            className="px-1 text-xs text-cyan hover:underline disabled:cursor-not-allowed disabled:text-white/40 disabled:no-underline"
          >
            Upload
          </button>
          <button
            type="button"
            disabled={locked || busy}
            onClick={() => {
              setPending(null);
              setError(null);
              onSettled?.();
            }}
            className="px-1 text-xs text-white/60 hover:text-white">
            Remove
          </button>
        </div>
      )}
    </div>
  );
}

function isRepeatUpload(detail: unknown): detail is RepeatUpload {
  return typeof detail === "object" && detail !== null && "imported_by" in detail;
}

/** "a, b, c, d, e, f, …": the first few names of a list. */
function shortList(names: string[], shown = 6): string {
  return names.slice(0, shown).join(", ") + (names.length > shown ? ", …" : "");
}

/** The page's generic source first, then the other built-ins, then the org's own. */
function sortedChoices(profiles: ImportProfile[], first: string): ImportProfile[] {
  const rank = (p: ImportProfile) => (p.key === first ? 0 : p.builtin ? 1 : 2);
  return [...profiles].sort((a, b) => rank(a) - rank(b));
}
