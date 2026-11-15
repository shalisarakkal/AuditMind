"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/domain";
import { enumLabel } from "@/lib/presentation";
import PublicationAction from "./PublicationAction";
import { DIALOG_NEUTRAL } from "./DialogActions";

type Source = { id: string | null; filename: string | null; retained: boolean; archived: boolean; status: string | null };
type Entry = { id: string; version: number; operation: string; actor_label: string; rationale: string; created_at: string;
  observation_id: string; observation_retained: boolean; observation_owner_retained?: boolean; recorded_at: string | null; observed_at: string | null;
  admission_contract: string; source: Source; snapshots: Record<string, string> };
type History = { availability: string; status: string; current: Entry | null; original_source?: Source;
  items: Entry[]; has_more: boolean; next_before_version: number | null; recovery: string[]; message: string };
const states: Record<string, string> = { not_published: "No publication recorded", published: "Publication recorded",
  undone: "Publication undone", recovery_required: "Recovery review required", unavailable: "History unavailable" };

function sourceLabel(source: Source) {
  return `${source.filename || (source.id ? "Import reference" : "No import linked")}${!source.retained && source.id ? " (no longer retained)" : source.archived ? " (archived)" : ""}`;
}

type Actions = { canReview?: boolean; hasWorkflowDraft?: boolean; onBusyChange?(busy: boolean): void; onChanged?(): void };
export default function FindingPublication({ orgId, findingId, disabled = false, ...actions }: { orgId: string; findingId: string; disabled?: boolean } & Actions) {
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState<number[]>([]);
  const before = pages.at(-1);
  const history = useApi<History>(open ? `/orgs/${orgId}/findings/${findingId}/publication-status?limit=20${before ? `&before_version=${before}` : ""}` : null);
  return <section aria-label="Scanner-field publication history" className="mt-5 min-w-0 border-t border-white/15 pt-3">
    <button type="button" disabled={disabled} aria-expanded={open} className="text-cyan underline disabled:opacity-50" onClick={() => setOpen(value => !value)}>{open ? "Hide publication history" : "Show publication history"}</button>
    {open && <div className="mt-3 min-w-0 space-y-3 text-sm [overflow-wrap:anywhere]">
      <p className="text-white/70">Read-only source provenance. Publication actions require a separate fresh review. Workflow decisions and source ownership are preserved.</p>
      {history.loading ? <p role="status">Loading publication history...</p> : history.error ? <p role="alert">{history.error} <button type="button" className="text-cyan underline" onClick={history.reload}>Retry publication history</button></p> : history.data && <>
        <p className="font-semibold">{states[history.data.status] || "Unrecognized publication state"}</p>
        {actions.canReview && actions.onChanged && history.data.status === "published" && history.data.current?.admission_contract === "observation-publication-consumers-v1" && <PublicationAction orgId={orgId} findingId={findingId} disabled={disabled} hasWorkflowDraft={actions.hasWorkflowDraft} onBusyChange={actions.onBusyChange} onChanged={actions.onChanged} />}
        {history.data.original_source && <p>Original owner import: {sourceLabel(history.data.original_source)}</p>}
        {history.data.current && <p>Current recorded generation: {history.data.current.version} · Decision source: {sourceLabel(history.data.current.source)}</p>}
        <p className="text-xs text-white/70">{history.data.message}</p>
        {history.data.recovery.length > 0 && <div role="status" className="space-y-2 rounded border border-amber-400/40 p-3 text-amber-200">{history.data.recovery.map(message => <p key={message}>{message}</p>)}</div>}
        {history.data.items.length > 0 && <ol className="space-y-3">{history.data.items.map(entry => <li key={entry.id} className="space-y-1 rounded border border-white/15 p-3">
          <p className="font-semibold">{entry.operation === "publish" ? "Publish recorded" : "Undo recorded"} · Version {entry.version}</p>
          <p>{entry.actor_label} · {formatDateTime(entry.created_at)}</p>
          <p className="whitespace-pre-wrap">Reason: {entry.rationale}</p>
          <p>Decision source: {sourceLabel(entry.source)}</p>
          <p>Observation: {entry.observation_retained ? entry.observation_owner_retained === false ? "Retained reference (original owner unavailable)" : "Retained" : "No longer retained"}{entry.recorded_at ? ` · Recorded: ${formatDateTime(entry.recorded_at)}` : ""}</p>
          {entry.observed_at && <p>Source observed time: {formatDateTime(entry.observed_at)}</p>}
          {entry.operation === "publish" && <p>Payload snapshots: before {entry.snapshots.before ? "retained" : "unavailable"}; after {entry.snapshots.after ? "retained" : "unavailable"}.</p>}
          <details><summary>Technical source references</summary><p>Decision ID: {entry.id}</p><p>Observation ID: {entry.observation_id}</p><p>Import ID: {entry.source.id}</p><p>Admission contract: {entry.admission_contract}</p></details>
        </li>)}</ol>}
        <div className="flex flex-wrap gap-3">
          <button type="button" className="text-cyan underline disabled:opacity-50" disabled={disabled} onClick={history.reload}>Reload publication history</button>
          <button type="button" disabled={disabled || pages.length === 0} onClick={() => setPages(value => value.slice(0, -1))}>Newer publication decisions</button>
          <button type="button" disabled={disabled || !history.data.has_more || !history.data.next_before_version} onClick={() => { const cursor = history.data?.next_before_version; if (cursor) setPages(value => [...value, cursor]); }}>Older publication decisions</button>
        </div>
      </>}
    </div>}
  </section>;
}

type Summary = { value: unknown; truncated: boolean; bytes: number; sha256: string };
type Preview = { no_op: boolean; changes: { field: string; before: Summary; after: Summary; removal: boolean }[];
  message: string; provenance: { original_filename: string | null; observation_filename: string | null;
    original_scan_id: string; observation_scan_id: string; observation_id: string; recorded_at: string; observed_at: string | null } };
function summaryText(summary: Summary, field: string) {
  if (summary.value === null) return "Not set";
  return typeof summary.value === "string" ? field === "severity" ? enumLabel(summary.value) : summary.value : JSON.stringify(summary.value);
}

export function ObservationPublicationPreview({ orgId, findingId, observationId, disabled = false, ...actions }: { orgId: string; findingId: string; observationId: string; disabled?: boolean } & Actions) {
  const [open, setOpen] = useState(false);
  return <section aria-label="Read-only scanner-field preview" className="mt-3 min-w-0">
    <button type="button" disabled={disabled} aria-expanded={open} className="text-cyan underline disabled:opacity-50" onClick={() => setOpen(value => !value)}>{open ? "Hide scanner-field preview" : "Preview scanner-field differences"}</button>
    {open && actions.canReview && actions.onChanged && <PublicationAction orgId={orgId} findingId={findingId} observationId={observationId} disabled={disabled} hasWorkflowDraft={actions.hasWorkflowDraft} onBusyChange={actions.onBusyChange} onChanged={actions.onChanged} />}
    {open && <PreviewBody key={`${orgId}:${findingId}:${observationId}`} orgId={orgId} findingId={findingId} observationId={observationId} disabled={disabled} onClose={() => setOpen(false)} />}
  </section>;
}
function PreviewBody({ orgId, findingId, observationId, disabled, onClose }: { orgId: string; findingId: string; observationId: string; disabled: boolean; onClose(): void }) {
  const [version, setVersion] = useState(0);
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true;
    setLoading(true); setData(null); setError(null);
    api.post<Preview>(`/orgs/${orgId}/findings/${findingId}/observations/${observationId}/publication-preview`, {})
      .then(result => { if (current) setData(result); })
      .catch((failure: unknown) => { if (current) setError(failure instanceof Error ? failure.message : "Preview unavailable"); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [orgId, findingId, observationId, version]);
  return <div className="mt-2 min-w-0 space-y-3 rounded border border-white/20 p-3 text-sm [overflow-wrap:anywhere]">
    <p className="text-white/70">Read-only comparison. No scanner fields, workflow, scores or source ownership will change. This preview cannot authorize Publish or Undo.</p>
    {loading && <p role="status">Loading scanner-field preview...</p>}
    {error && <div role="alert"><p>{error}</p><p>Review the source and identity prerequisites. Missing or purged data must not be reconstructed; ask an organization administrator to review recovery.</p></div>}
    {data && <>
      <p>Original owner import: {data.provenance.original_filename || "Retained import"}</p>
      <p>Compared observation import: {data.provenance.observation_filename || "Retained import"}</p>
      <p>Recorded: {formatDateTime(data.provenance.recorded_at)}</p>
      <p>Source observed time: {data.provenance.observed_at ? formatDateTime(data.provenance.observed_at) : "Not provided"}</p>
      <p className="text-xs text-white/70">{data.message}</p>
      {data.no_op ? <p>No scanner-field differences.</p> : <dl className="space-y-3">{data.changes.map(change => <div key={change.field} className="min-w-0 rounded border border-white/15 p-2">
        <dt className="font-semibold">{enumLabel(change.field)}{change.removal ? " (would be cleared)" : ""}</dt>
        <dd className="mt-1 grid min-w-0 gap-2 sm:grid-cols-2">{(["before", "after"] as const).map(side => <div key={side} className="min-w-0"><p className="font-semibold">{side === "before" ? "Current" : "Observation"}</p><p className="whitespace-pre-wrap">{summaryText(change[side], change.field)}</p>{change[side].truncated && <p className="text-amber-200">Display shortened; comparison uses the full value.</p>}<details><summary>Value fingerprint</summary><p>{change[side].bytes} bytes</p><p>{change[side].sha256}</p></details></div>)}</dd>
      </div>)}</dl>}
      <details><summary>Technical comparison references</summary><p>Original import ID: {data.provenance.original_scan_id}</p><p>Observation import ID: {data.provenance.observation_scan_id}</p><p>Observation ID: {data.provenance.observation_id}</p></details>
    </>}
    <footer className="flex flex-wrap justify-end gap-3 border-t border-white/15 pt-3">
      <button type="button" className={DIALOG_NEUTRAL} onClick={onClose}>Close preview</button>
      <button type="button" className="text-cyan underline disabled:opacity-50" disabled={disabled || loading} onClick={() => setVersion(value => value + 1)}>Reload scanner-field preview</button>
    </footer>
  </div>;
}
