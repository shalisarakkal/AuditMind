"use client";
import { useId, useState } from "react";
import Link from "next/link";
import { useApi } from "@/lib/useApi";
import { canWrite, DOMAIN_LABELS } from "@/lib/domain";
import type { UserRole } from "@/lib/types";
import type { Catalogs, ControlMapping, MappingDecision } from "@/lib/controlCatalog";
import ControlCatalogBrowser, { CATALOG_INPUT } from "./ControlCatalogBrowser";
import ControlMappingDialog from "./ControlMappingDialog";
import MappingDecisionView from "./ControlMappingDecision";
import { DIALOG_NEUTRAL, DIALOG_PRIMARY } from "./DialogActions";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;


function MappingHistory({ orgId, ruleId }: { orgId: string; ruleId: string }) {
  const [open, setOpen] = useState(false), [pages, setPages] = useState<number[]>([]);
  const before = pages.at(-1);
  const history = useApi<MappingDecision[]>(open ? `/orgs/${orgId}/control-rules/${ruleId}/history?limit=20${before ? `&before_version=${before}` : ""}` : null);
  return <section className="space-y-3">
    <button type="button" aria-expanded={open} className="text-cyan underline" onClick={() => setOpen(value => !value)}>{open ? "Hide mapping history" : "Show mapping history"}</button>
    {open && <>{history.loading ? <p role="status">Loading mapping history…</p> : history.error ? <p role="alert">{history.error} <button type="button" onClick={history.reload}>Retry history</button></p> : <>
      {history.data?.map(d => <MappingDecisionView key={d.id} decision={d} title={d.state === "approved" ? "Approved mapping" : d.state === "withdrawn" ? "Withdrawn mapping" : "Proposed mapping"} />)}
      {!history.data?.length && <p>No mapping decisions recorded.</p>}
    </>}
      <div className="flex flex-wrap gap-3"><button type="button" className={DIALOG_NEUTRAL} disabled={history.loading || !pages.length} onClick={() => setPages(p => p.slice(0, -1))}>Newer mapping history</button><button type="button" className={DIALOG_NEUTRAL} disabled={history.loading || (history.data?.length || 0) < 20} onClick={() => { const last = history.data?.at(-1); if (last) setPages(p => [...p, last.version]); }}>Older mapping history</button></div>
    </>}
  </section>;
}

export default function ControlMappingWorkspace({ orgId, orgName, role, initialFindingId = "", initialRuleId = "" }: { orgId: string; orgName: string; role: UserRole; initialFindingId?: string; initialRuleId?: string }) {
  const id = useId();
  const initialKind = initialRuleId ? "rule" : "finding";
  const initialId = initialRuleId || initialFindingId;
  const [kind, setKind] = useState<"finding" | "rule">(initialKind);
  const [input, setInput] = useState(initialId), [lookup, setLookup] = useState<{ kind: "finding" | "rule"; id: string } | null>(UUID.test(initialId) ? { kind: initialKind, id: initialId } : null);
  const [validation, setValidation] = useState<string | null>(null), [action, setAction] = useState<"propose" | "approve" | "withdraw" | null>(null);
  const [browse, setBrowse] = useState(false), [release, setRelease] = useState("");
  const catalogs = useApi<Catalogs>(`/orgs/${orgId}/control-catalogs`);
  const mapping = useApi<ControlMapping>(lookup ? lookup.kind === "rule" ? `/orgs/${orgId}/control-rules/${lookup.id}` : `/orgs/${orgId}/findings/${lookup.id}/control-mapping` : null);
  const responseKind = mapping.data?.context_kind || "finding";
  const responseId = responseKind === "rule" ? mapping.data?.rule_id : mapping.data?.finding_id;
  const ready = !mapping.loading && !mapping.error && mapping.data && input.trim() === lookup?.id && kind === lookup?.kind && responseKind === lookup?.kind && responseId === lookup?.id;
  const data = ready ? mapping.data : null;
  const writer = canWrite(role), admin = role === "admin";
  return <div className="min-w-0 space-y-5 [overflow-wrap:anywhere]">
    <h1 className="text-2xl font-semibold">Control mappings</h1>
    <p className="text-sm text-white/70">Review relevance between finding categories and versioned controls. A mapping is not a control assessment, compliance pass or certification. Scores and saved reports are unchanged.</p>
    <form className="flex flex-wrap items-end gap-3" onSubmit={e => { e.preventDefault(); const value = input.trim(); if (!UUID.test(value)) { setValidation(`Enter a full ${kind === "rule" ? "Rule" : "Finding"} ID.`); return; } setValidation(null); if (value === lookup?.id && kind === lookup.kind) mapping.reload(); else setLookup({ kind, id: value }); }}>
      <div><label className="mb-1 block text-sm" htmlFor={`${id}-kind`}>Lookup by</label><select id={`${id}-kind`} className={CATALOG_INPUT} value={kind} onChange={e => { setKind(e.target.value as "finding" | "rule"); setInput(""); setLookup(null); setValidation(null); }}><option value="finding">Finding ID</option><option value="rule">Rule ID</option></select></div>
      <div className="min-w-0 flex-1"><label className="mb-1 block text-sm" htmlFor={`${id}-context`}>{kind === "rule" ? "Rule ID" : "Finding ID"}</label><input id={`${id}-context`} maxLength={128} className={CATALOG_INPUT} value={input} onChange={e => setInput(e.target.value)} placeholder={kind === "rule" ? "Copy the Rule ID from mapping details or Activity" : "Copy the Finding ID from the finding row"} /></div>
      <button className={DIALOG_PRIMARY} disabled={!!lookup && mapping.loading}>Open / reload {kind === "rule" ? "rule" : "finding"}</button>
    </form>
    {validation && <p role="alert">{validation}</p>}
    {mapping.loading && <p role="status">Loading mapping context…</p>}
    {lookup && mapping.error && <p role="alert">{mapping.error}</p>}
    {data && <section className="space-y-4 rounded-xl border border-white/15 p-4">
      <h2 className="text-lg font-semibold">{!data.available ? "Mapping unavailable" : data.status === "mapped" ? "Approved category mapping" : "Unmapped"}</h2>
      <dl className="grid gap-1 text-sm sm:grid-cols-2"><dt>Source</dt><dd>{data.source || "Not provided"}</dd><dt>Domain</dt><dd>{DOMAIN_LABELS[data.domain]}</dd><dt>Category</dt><dd>{data.category || "Not provided (uncategorised)"}</dd></dl>
      <details className="text-xs text-white/60"><summary>Finding and rule identifiers</summary><p>Finding ID: {data.finding_id || "Not bound; retained category rule"}</p><p>Rule ID: {data.rule_id || "Not created"} · Generation {data.version}</p></details>
      {data.rule_id && data.context_kind !== "rule" && <Link className="text-cyan underline" href={`/controls?org=${orgId}&rule_id=${data.rule_id}`}>Open retained category rule</Link>}
      {!data.available ? <p role="status">Control mappings require coordinated database activation.</p> : <>
        {!data.effective && <p>No approved control mapping is applied to this exact category. This does not indicate a control pass or failure.</p>}
        {data.effective && <MappingDecisionView decision={data.effective} title="Effective approved mapping" />}
        {data.proposal && <MappingDecisionView decision={data.proposal} title="Proposal pending administrator review" />}
        {data.inactive && <p className="text-amber-200">This finding is inactive. Mapping history is read-only here; category rules are retained.</p>}
        <div className="flex flex-wrap gap-3">
          {writer && <button type="button" className={DIALOG_PRIMARY} disabled={data.inactive || !catalogs.data?.items.length || catalogs.loading} onClick={() => setAction("propose")}>{data.proposal ? "Revise proposal" : "Propose mapping"}</button>}
          {admin && data.proposal && <button type="button" className={DIALOG_NEUTRAL} disabled={data.inactive} onClick={() => setAction("approve")}>Review proposal</button>}
          {admin && (data.effective || data.proposal) && <button type="button" className={DIALOG_NEUTRAL} disabled={data.inactive} onClick={() => setAction("withdraw")}>Withdraw mapping</button>}
        </div>
        {data.rule_id && <MappingHistory key={`${data.rule_id}:${data.version}`} orgId={orgId} ruleId={data.rule_id} />}
      </>}
    </section>}
    {catalogs.loading && <p role="status">Loading catalog releases…</p>}
    {catalogs.error && <p role="alert">{catalogs.error} <button type="button" onClick={catalogs.reload}>Retry catalog releases</button></p>}
    {catalogs.data && !catalogs.data.available && <p>Catalog installation requires coordinated database activation.</p>}
    {catalogs.data?.available && !catalogs.data.items.length && <p>No control catalog is installed. A platform administrator must install the verified baseline before mapping proposals can be made.</p>}
    <button type="button" className="text-cyan underline" aria-expanded={browse} onClick={() => setBrowse(value => !value)}>{browse ? "Hide control catalog" : "Browse control catalog"}</button>
    {browse && <ControlCatalogBrowser catalogs={catalogs.data?.items || []} basePath={`/orgs/${orgId}/control-catalogs`} value={release || catalogs.data?.items[0]?.id || ""} onChange={setRelease} />}
    {action && data && <ControlMappingDialog orgId={orgId} orgName={orgName} mapping={data} catalogs={catalogs.data?.items || []} action={action} onClose={() => setAction(null)} onChanged={mapping.reload} />}
  </div>;
}
