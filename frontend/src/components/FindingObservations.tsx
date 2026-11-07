"use client";

import FindingIdentityBinding from "./FindingIdentityBinding";
import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/domain";

type Observation = {
  id: string; import_id: string; filename: string | null; source: string;
  source_row: number; recorded_at: string; observed_at: string | null;
  reconciliation_eligible: boolean; ineligibility_reasons: string[];
  identity_assessment?: { version: string; mapping: string | null; candidate_key: string | null };
  payload: { severity?: string; category?: string; description?: string };
};
const reasons: Record<string, string> = {
  source_instance_not_configured: "Tool instance is not configured",
  stable_asset_mapping_not_verified: "Stable asset mapping is not verified",
  stable_source_identifier_unavailable: "Stable source finding identifier is unavailable",
  source_instance_discriminator_missing: "Port or protocol is missing",
  legacy_matching_only: "Current import matching does not establish a reconciliation identity",
  source_observed_time_invalid: "Source observed time is invalid or has no timezone offset",
};

export default function FindingObservations({ orgId, findingId, canReview = false, disabled = false, onBusyChange }: { orgId: string; findingId: string; canReview?: boolean; disabled?: boolean; onBusyChange?(busy: boolean): void }) {
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState<string[]>([]);
  const before = pages.at(-1);
  const rows = useApi<Observation[]>(open
    ? `/orgs/${orgId}/findings/${findingId}/observations?limit=20${before ? `&before=${before}` : ""}` : null);
  return <section aria-label="Source observations" className="mt-5 border-t border-white/15 pt-3">
    <button type="button" aria-expanded={open} className="text-cyan underline" onClick={() => setOpen(value => !value)}>{open ? "Hide source observations" : "Show source observations"}</button>
    {open && <div className="mt-3">
      <p className="text-sm text-white/70">Import occurrences are separate from workflow decisions. History starts with imports processed after this feature was installed.</p>
      {rows.loading ? <p role="status">Loading observations…</p> : rows.error ? <p role="alert">{rows.error} <button type="button" className="text-cyan underline" onClick={rows.reload}>Retry observations</button></p> : rows.data?.length ? <ol className="mt-3 space-y-3">{rows.data.map(row => <li key={row.id} className="rounded border border-white/15 p-3 text-sm">
        <p className="break-words font-semibold">{row.filename || "Imported file"} · Row {row.source_row}</p>
        <p>Recorded: {formatDateTime(row.recorded_at)}</p>
        <p>Source observed time: {row.observed_at ? formatDateTime(row.observed_at) : "Not provided"}</p>
        <p className="break-words">Source: {row.source} · Severity: {row.payload.severity ? row.payload.severity.charAt(0).toUpperCase() + row.payload.severity.slice(1) : "Not provided"}</p>
        <p className="whitespace-pre-wrap break-words">{row.payload.category}{row.payload.description ? `: ${row.payload.description}` : ""}</p>
        <p>{row.reconciliation_eligible ? "Reconciliation eligible" : "Not eligible for reconciliation"}</p>
        <p className="text-xs text-white/70">Recorded eligibility reasons at import:</p>
        <ul className="list-inside list-disc text-xs text-white/70">{row.ineligibility_reasons.map(reason => <li key={reason}>{reasons[reason] || reason.replaceAll("_", " ")}</li>)}</ul>
        {row.identity_assessment && <details><summary>Identity assessment</summary>
          <p className="break-words text-xs text-white/70">Version: {row.identity_assessment.version}</p>
          <p className="break-words text-xs text-white/70">Source mapping: {row.identity_assessment.mapping || "No reviewed mapping"}</p>
          <p className="break-all text-xs text-white/70">Identity candidate: {row.identity_assessment.candidate_key || "Unavailable until tool and asset bindings are established"}</p>
          <p className="text-xs text-white/70">Identity diagnostics do not authorize reconciliation, suppression or workflow changes.</p>
        </details>}
        {canReview && row.identity_assessment?.mapping === "nessus-plugin-service-v1" && <FindingIdentityBinding orgId={orgId} findingId={findingId} observationId={row.id} disabled={disabled} onBusyChange={onBusyChange} onSaved={rows.reload} />}
        <details><summary>Import ID</summary><p className="break-all">{row.import_id}</p></details>
      </li>)}</ol> : <p className="mt-3 text-sm">No source observations recorded.</p>}
      <div className="mt-3 flex gap-4 text-sm">
        <button type="button" disabled={rows.loading || pages.length === 0} onClick={() => setPages(value => value.slice(0, -1))}>Newer observations</button>
        <button type="button" disabled={rows.loading || !!rows.error || (rows.data?.length ?? 0) < 20} onClick={() => { const last = rows.data?.at(-1); if (last) setPages(value => [...value, last.id]); }}>Older observations</button>
      </div>
    </div>}
  </section>;
}
