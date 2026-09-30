"use client";

import { useEffect, useRef, useState } from "react";

import ConfirmPanel from "@/components/ConfirmPanel";
import { useImports } from "@/context/ImportsContext";
import { ApiError, api } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
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

/** Uploads a file. With profiles, the user confirms the file's source first
 * (pre-selected when the file's columns match a profile). The import is then
 * followed app-wide (ImportsContext): its progress and report show on the
 * page (ImportStatus), whichever page the user is on when it finishes. */
export default function ImportButton({ orgId, kind, accept, label, profiles }: ImportButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
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
  async function upload(file: File, profileKey: string, confirm = false) {
    // A second click that lands before the re-render hides the confirm
    // button must not upload the file again.
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(null);
    setRepeat(null);
    setError(null);
    setUploading(true);
    let response: ImportResponse;
    try {
      const { path, fields } = importTarget(orgId, profileKey);
      response = await api.upload<ImportResponse>(path, file, confirm ? { ...fields, confirm: "true" } : fields);
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof ApiError && err.status === 409 && isRepeatUpload(err.detail)) {
        // Already imported: a warning, the user decides.
        setRepeat({ file, profileKey, previous: err.detail });
        return;
      }
      // The upload itself failed (e.g. an unsupported file): nothing to track.
      setError(`${file.name}: ${(err as Error).message}`);
      return;
    } finally {
      inFlight.current = false;
      if (mounted.current) setUploading(false);
    }
    // Accepted: the import is followed from here on, wherever the user goes.
    await imports.track(response.scan_id, kind);
  }

  async function handleFile(file: File) {
    if (inputRef.current) inputRef.current.value = "";
    setError(null); // a new file: the last one's error no longer applies
    if (!profiles?.length) {
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

  const busy = uploading;
  const nessus = pending !== null && fileExtension(pending.file.name) === ".nessus";
  const choices = nessus ? (profiles ?? []).filter((p) => p.key === GENERIC_FINDINGS) : sortedChoices(profiles ?? [], pageDefault);
  // Import only with a source that can identify the file's rows.
  const selected = choices.find((p) => p.key === source);
  const columns = pending?.columns ?? [];
  const readable = !selected || canRead(selected, columns);
  const noSourceReads = !readable && choices.every((p) => !canRead(p, columns));

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          data-testid={`${kind}-file-input`}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
        {uploading && <span className="text-sm text-white/60">Uploading…</span>}
        <button
          type="button"
          disabled={busy || pending !== null || repeat !== null}
          onClick={() => inputRef.current?.click()}
          className="rounded-md bg-cyan px-4 py-2 text-sm font-medium text-navy transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {label}
        </button>
      </div>

      {error && (
        <p role="alert" className="max-w-md text-right text-sm text-red-300">
          {error}
        </p>
      )}

      {repeat && (
        <ConfirmPanel
          label="Already imported"
          message={
            <>
              <strong>{repeat.file.name}</strong>: this exact file was already imported
              {repeat.previous.imported_at ? ` on ${formatDateTime(repeat.previous.imported_at)}` : ""} by{" "}
              {repeat.previous.imported_by}. Import it again?
            </>
          }
          confirmLabel="Import anyway"
          onConfirm={() => void upload(repeat.file, repeat.profileKey, true)}
          onCancel={() => setRepeat(null)}
          busy={busy}
        />
      )}

      {pending && (
        <div
          role="group"
          aria-label="Import options"
          className="flex flex-wrap items-center justify-end gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm"
        >
          <span className="max-w-56 truncate font-medium text-white" title={pending.file.name}>
            {pending.file.name}
          </span>
          <label htmlFor={`${kind}-import-source`} className="text-white/60">
            Source
          </label>
          <select
            id={`${kind}-import-source`}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="max-w-64 rounded-md border border-white/15 bg-navy px-2 py-1 text-sm text-white focus:border-cyan focus:outline-none"
          >
            {choices.map((p) => (
              <option key={p.key} value={p.key}>
                {p.builtin ? p.name : `${p.name} (${p.family_label})`}
              </option>
            ))}
          </select>
          {pending.detected && source === pending.detected && (
            <span className="text-xs text-emerald-300">Detected from the file&apos;s columns</span>
          )}
          {!readable && (
            <p role="note" className="basis-full text-right text-xs text-amber-300">
              {noSourceReads ? (
                <>
                  No source can read this file: none of its columns ({shortList(columns)}) identifies a host. Event
                  logs (cloud activity, audit or endpoint security events) can&apos;t be imported yet; press Cancel.
                </>
              ) : (
                <>
                  {selected!.name} can&apos;t read this file: none of its columns ({shortList(columns)}) is one that
                  source identifies hosts by. Pick another source.
                </>
              )}
            </p>
          )}
          <button
            type="button"
            disabled={busy || !readable}
            onClick={() => void upload(pending.file, source)}
            className="rounded-md bg-cyan px-3 py-1 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-60"
          >
            Import
          </button>
          <button
            type="button"
            onClick={() => {
              setPending(null);
              setError(null);
            }}
            className="px-1 text-xs text-white/60 hover:text-white">
            Cancel
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
