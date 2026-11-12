"use client";

import { useState } from "react";
import FindingActionDialog from "@/components/FindingActionDialog";
import FindingSuppressionDialog, { type SuppressionTarget } from "@/components/FindingSuppressionDialog";
import FindingReference from "@/components/FindingReference";
import { DIALOG_NEUTRAL, DIALOG_SECONDARY } from "@/components/DialogActions";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/domain";

type Row = { id: string; finding_id: string; label: string; state: "suppressed" | "cleared"; version: number; reappearance_count: number };
type Page = { items: Row[]; has_more: boolean };
type Decision = { id: string; version: number; state: string; actor_label: string; rationale: string; created_at: string };
type Appearance = { id: string; finding_id: string; filename: string | null; created_at: string; state: string };

function History({ orgId, row }: { orgId: string; row: Row }) {
  const [before, setBefore] = useState<number | null>(null);
  const history = useApi<{ items: Decision[]; has_more: boolean }>(`/orgs/${orgId}/finding-suppressions/${row.id}/history?limit=20${before ? `&before_version=${before}` : ""}`);
  return <section aria-label="Suppression decision history" className="space-y-2 border-t border-white/10 pt-3">
    <h3 className="font-medium">Decision history</h3>
    {history.loading && <p role="status">Loading history...</p>}
    {history.error && <p role="alert" className="text-red-300">{history.error}</p>}
    {history.data?.items.map(item => <article key={item.id} className="rounded border border-white/10 p-2 text-sm">
      <p>{item.state === "suppressed" ? "Suppressed" : "Suppression cleared"} &middot; {item.actor_label} &middot; {formatDateTime(item.created_at)} &middot; Version {item.version}</p>
      <p className="whitespace-pre-wrap break-words">{item.rationale}</p>
    </article>)}
    <div className="flex flex-wrap gap-2"><button type="button" disabled={!before || history.loading} className={DIALOG_SECONDARY} onClick={() => setBefore(null)}>Latest decisions</button>
      <button type="button" disabled={!history.data?.has_more || history.loading} className={DIALOG_SECONDARY} onClick={() => setBefore(history.data?.items.at(-1)?.version ?? null)}>Older decisions</button></div>
  </section>;
}

function Reappearances({ orgId, row }: { orgId: string; row: Row }) {
  const [offset, setOffset] = useState(0);
  const data = useApi<{ items: Appearance[]; has_more: boolean }>(`/orgs/${orgId}/finding-suppressions/${row.id}/reappearances?limit=20&offset=${offset}`);
  return <section aria-label="Possible reappearances" className="space-y-2 border-t border-white/10 pt-3">
    <h3 className="font-medium">Possible reappearances</h3>
    <p className="text-xs text-white/70">Source similarity is not a trusted identity binding. Review the new finding independently; these records do not hide it.</p>
    {data.loading && <p role="status">Loading possible reappearances...</p>}
    {data.error && <p role="alert" className="text-red-300">{data.error}</p>}
    {data.data?.items.map(item => <article key={item.id} className="min-w-0 rounded border border-white/10 p-2 text-sm"><p className="break-words">{item.filename ?? "Source payload unavailable"} &middot; {formatDateTime(item.created_at)}</p><FindingReference orgId={orgId} id={item.finding_id} /></article>)}
    <div className="flex flex-wrap gap-2"><button type="button" disabled={!offset || data.loading} className={DIALOG_SECONDARY} onClick={() => setOffset(value => Math.max(0, value - 20))}>Previous reappearances</button>
      <button type="button" disabled={!data.data?.has_more || data.loading} className={DIALOG_SECONDARY} onClick={() => setOffset(value => value + 20)}>More reappearances</button></div>
  </section>;
}

export default function SuppressedFindingsDialog({ orgId, orgName, role, onClose, onSaved }: {
  orgId: string; orgName: string; role: string; onClose(): void; onSaved(): void;
}) {
  const [state, setState] = useState("suppressed");
  const [offset, setOffset] = useState(0);
  const [opened, setOpened] = useState<string | null>(null);
  const [appearances, setAppearances] = useState<string | null>(null);
  const [target, setTarget] = useState<SuppressionTarget | null>(null);
  const page = useApi<Page>(`/orgs/${orgId}/finding-suppressions?state=${state}&limit=20&offset=${offset}`);
  return <FindingActionDialog title="Suppressed findings" orgName={orgName} onClose={onClose}>
    <div className="min-w-0 space-y-4">
      <p className="text-sm text-white/70">Suppression controls visibility, not remediation status or verified evidence. Only an organization admin can clear it.</p>
      <label className="block text-sm">Suppression state<select value={state} className="ml-2 rounded border border-white/20 bg-navy p-2" disabled={page.loading}
        onChange={event => { setState(event.target.value); setOffset(0); setOpened(null); setAppearances(null); }}><option value="suppressed">Suppressed</option><option value="cleared">Cleared</option><option value="all">All</option></select></label>
      {page.loading && <p role="status">Loading suppressed findings...</p>}
      {page.error && <p role="alert" className="text-red-300">{page.error}</p>}
      {!page.loading && !page.data?.items.length && !page.error && <p>No suppression records in this view.</p>}
      {page.data?.items.map(row => <article key={row.id} className="min-w-0 space-y-2 rounded-lg border border-white/15 p-3">
        <p className="break-words font-semibold">{row.label || "Finding"}</p><FindingReference orgId={orgId} id={row.finding_id} />
        <p className="text-sm">{row.state === "suppressed" ? "Suppressed" : "Cleared"} &middot; Version {row.version}</p>
        <div className="flex flex-wrap gap-3 text-sm">
          <button type="button" className="text-cyan underline" onClick={() => setOpened(value => value === row.id ? null : row.id)}>{opened === row.id ? "Hide history" : "Show history"}</button>
          {!!row.reappearance_count && <button type="button" className="text-cyan underline" onClick={() => setAppearances(value => value === row.id ? null : row.id)}>{appearances === row.id ? "Hide reappearances" : `Review possible reappearances (${row.reappearance_count})`}</button>}
          {role === "admin" && row.state === "suppressed" && <button type="button" className="text-cyan underline" disabled={page.loading} onClick={() => setTarget({ action: "clear", suppression_id: row.id })}>Clear suppression</button>}
        </div>
        {opened === row.id && <History key={`${row.id}-${row.version}`} orgId={orgId} row={row} />}
        {appearances === row.id && <Reappearances orgId={orgId} row={row} />}
      </article>)}
      <footer className="flex flex-col gap-3 border-t border-white/15 pt-4 sm:flex-row sm:flex-wrap sm:items-center">
        <button type="button" className={DIALOG_SECONDARY} disabled={!offset || page.loading} onClick={() => setOffset(value => Math.max(0, value - 20))}>Previous</button>
        <button type="button" className={DIALOG_SECONDARY} disabled={!page.data?.has_more || page.loading} onClick={() => setOffset(value => value + 20)}>Next</button>
        <button type="button" className={`${DIALOG_NEUTRAL} sm:ml-auto`} data-confirm-cancel onClick={onClose}>Close</button>
      </footer>
      {target && <FindingSuppressionDialog key={target.suppression_id} orgId={orgId} orgName={orgName} target={target} onClose={() => setTarget(null)} onSaved={() => { setTarget(null); setOffset(0); page.reload(); onSaved(); }} />}
    </div>
  </FindingActionDialog>;
}
