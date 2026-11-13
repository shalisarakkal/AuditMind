"use client";
import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/apiClient";
import { DOMAIN_LABELS, formatDateTime } from "@/lib/domain";
import { useApi } from "@/lib/useApi";
import type { Domain } from "@/lib/types";
import { enumLabel } from "@/lib/presentation";
import { findingHref } from "./FindingReference";
import FindingActionDialog from "./FindingActionDialog";
import FindingObservations from "./FindingObservations";
import { DIALOG_FOOTER,DIALOG_NEUTRAL,DIALOG_PRIMARY } from "./DialogActions";

type Group={id:string;version:number;state:string;published:boolean;canonical_finding_id:string;canonical_decision_id:string;member_ids:string[]};
type Groups={settings:{enabled:boolean;version:number};items:Group[];has_more?:boolean;current_group_id?:string|null};
type Decision={id:string;state:string;latest:boolean;canonical_finding_id:string};
type Target={action:"apply"|"undo";id:string};
type Plan={review_token:string;expected_version:number;members?:{finding_id:string;role:string}[];
  findings?:{id:string;description:string;scan_id:string;asset_id:string;domain?:Domain;severity?:string;latest_observation?:{filename:string|null}}[];
  source_counts?:Record<string,number>;context?:{members:{id:string;scan_id:string;asset_id:string}[];canonical_finding_id:string}};

export default function FindingConsolidation({orgId,findingId,canReview,disabled,hasWorkflowDraft=false,onBusyChange,onChanged}:{orgId:string;findingId:string;canReview:boolean;disabled:boolean;hasWorkflowDraft?:boolean;onBusyChange(busy:boolean):void;onChanged():void}) {
  const [open,setOpen]=useState(false),[target,setTarget]=useState<Target|null>(null),[offset,setOffset]=useState(0);
  const path=`/orgs/${orgId}/finding-consolidations`;
  const groups=useApi<Groups>(open?`${path}/for-finding/${findingId}?limit=20&offset=${offset}`:null);
  const decisions=useApi<Decision[]>(open?`/orgs/${orgId}/findings/${findingId}/canonical-decisions`:null);
  const current=!!groups.data?.current_group_id||groups.data?.items.some(row=>row.published&&row.state==="active");
  return <section aria-label="Reviewed finding consolidation" className="mt-5 min-w-0 border-t border-white/15 pt-3">
    <button type="button" aria-expanded={open} disabled={disabled} className="text-cyan underline" onClick={()=>setOpen(value=>!value)}>{open?"Hide consolidation review":"Show consolidation review"}</button>
    {open&&<div className="mt-3 min-w-0 space-y-3 [overflow-wrap:anywhere]">
      <p className="text-sm text-white/70">A reviewed native pair contributes one visible finding. Both original source records and workflows remain; scanner fields are not merged. New source occurrences never join a pair automatically.</p>
      {(groups.loading||decisions.loading)&&<p role="status">Loading consolidation review...</p>}
      {(groups.error||decisions.error)&&<p role="alert">{groups.error||decisions.error} <button type="button" className="underline" onClick={()=>{groups.reload();decisions.reload();}}>Reload consolidation review</button></p>}
      {groups.data&&!groups.data.settings.enabled&&<p className="text-sm">New consolidation is disabled. {canReview&&<Link className="text-cyan underline" href="/settings">Review organization Settings</Link>}</p>}
      {canReview&&hasWorkflowDraft&&<p role="status" className="text-sm">Save or clear the unsaved workflow draft before starting consolidation or undo.</p>}
      {groups.data?.items.map(group=><article key={group.id} className="space-y-2 rounded border border-white/15 p-3 text-sm">
        <p>{group.published?"Published pair":group.state==="undone"?"Undone pair":"Retained metadata"} - Version {group.version}</p>
        <p>Canonical finding: <Link className="text-cyan underline" href={findingHref(orgId,group.canonical_finding_id)}>{group.canonical_finding_id}</Link></p>
        <p className="text-xs text-white/60">Group: {group.id}</p>
        {group.member_ids.filter(id=>id!==findingId).map(id=><RetainedSources key={id} orgId={orgId} findingId={id}/>)}
        <GroupHistory path={path} groupId={group.id}/>
        {canReview&&group.published&&group.state==="active"&&<button type="button" disabled={disabled||hasWorkflowDraft} className="text-cyan underline" onClick={()=>setTarget({action:"undo",id:group.id})}>Preview undo consolidation</button>}
      </article>)}
      {canReview&&!current&&groups.data?.settings.enabled&&decisions.data?.filter(row=>row.latest&&row.state==="selected").map(row=><button key={row.id} type="button" disabled={disabled||hasWorkflowDraft} className="block text-cyan underline" onClick={()=>setTarget({action:"apply",id:row.id})}>Preview consolidation for {row.canonical_finding_id}</button>)}
      {groups.data&&<div className="flex flex-wrap gap-3 text-sm"><button type="button" className="text-cyan underline disabled:opacity-50" disabled={groups.loading||offset===0} onClick={()=>setOffset(value=>Math.max(0,value-20))}>Newer finding groups</button><button type="button" className="text-cyan underline disabled:opacity-50" disabled={groups.loading||!!groups.error||!groups.data.has_more} onClick={()=>setOffset(value=>value+20)}>Older finding groups</button></div>}
      {groups.data&&!groups.data.items.length&&<p className="text-sm">No consolidation recorded. First independently review both native identities and designate a canonical finding through Source observations.</p>}
    </div>}
    {target&&<Review key={`${target.action}:${target.id}`} path={path} target={target} onBusyChange={onBusyChange}
      onClose={()=>{setTarget(null);groups.reload();decisions.reload();}} onChanged={()=>{setTarget(null);groups.reload();decisions.reload();onChanged();}}/>}
  </section>;
}
function RetainedSources({orgId,findingId}:{orgId:string;findingId:string}) {
  const [open,setOpen]=useState(false);
  const history=useApi<{version:number;rationale:string;verification:string|null;actor_label:string}[]>(open?`/orgs/${orgId}/findings/${findingId}/workflow/history?limit=20`:null);
  return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>Retained member source and workflow history: {findingId}</summary>
    {open&&<div className="space-y-2">
      <p>Read-only retained source record. Group review does not transfer its workflow or notes.</p>
      {history.error&&<p role="alert">{history.error}</p>}
      {history.loading?<p role="status">Loading retained history...</p>:history.data?.length?<ol>{history.data.map(row=><li key={row.version}>{row.actor_label} - Version {row.version}: {row.rationale}{row.verification&&` - Verification note: ${row.verification}`}</li>)}</ol>:<p>No workflow entries.</p>}
      {history.data?.length===20&&<p>Showing the latest 20 workflow entries.</p>}
      <FindingObservations orgId={orgId} findingId={findingId} canReview={false}/>
    </div>}
  </details>;
}
function Review({path,target,onBusyChange,onClose,onChanged}:{path:string;target:Target;onBusyChange(value:boolean):void;onClose():void;onChanged():void}) {
  const [plan,setPlan]=useState<Plan|null>(null),[revision,setRevision]=useState(0),[loading,setLoading]=useState(true);
  const [reason,setReason]=useState(""),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[unknown,setUnknown]=useState(false);
  const reasonId=useId();
  const inFlight=useRef(false),request=useRef<Record<string,unknown>|null>(null);
  useEffect(()=>{let abandoned=false;setLoading(true);setPlan(null);setConfirmed(false);setError(null);setUnknown(false);request.current=null;
    const endpoint=target.action==="apply"?`${path}/publication-preview`:`${path}/${target.id}/undo-preview`;
    api.post<Plan>(endpoint,target.action==="apply"?{canonical_decision_id:target.id}:{}).then(value=>{if(!abandoned)setPlan(value);}).catch(cause=>{if(!abandoned)setError(cause instanceof Error?cause.message:"Preview failed");}).finally(()=>{if(!abandoned)setLoading(false);});
    return ()=>{abandoned=true;};
  },[path,target.id,target.action,revision]);
  async function save(){if(inFlight.current||!plan||(!request.current&&(!confirmed||!reason.trim())))return;
    if(!request.current)request.current={request_id:crypto.randomUUID(),expected_version:plan.expected_version,review_token:plan.review_token,rationale:reason.trim(),confirm:true,...(target.action==="apply"?{canonical_decision_id:target.id}:{})};
    inFlight.current=true;setBusy(true);onBusyChange(true);setError(null);
    try{await api.post(target.action==="apply"?`${path}/apply`:`${path}/${target.id}/undo`,request.current);onChanged();}
    catch(cause){setError(cause instanceof Error?cause.message:"The response was not received");
      if(cause instanceof ApiError&&cause.status>=400&&cause.status<500&&cause.status!==408){request.current=null;setPlan(null);setConfirmed(false);setUnknown(false);}
      else setUnknown(true);
    }finally{inFlight.current=false;setBusy(false);onBusyChange(false);}}
  const members=plan?.members?.map(row=>row.finding_id)||plan?.context?.members.map(row=>row.id)||[];
  return <FindingActionDialog title={target.action==="apply"?"Consolidate reviewed pair":"Undo finding consolidation"} orgName="Exact reviewed targets" onClose={()=>{if(!inFlight.current){if(unknown)onChanged();else onClose();}}}>
    <div aria-busy={busy} className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
      <p>{target.action==="apply"?"This pair will contribute one visible canonical finding instead of two. Both physical source records and independent histories remain. Approved scoring evidence must be revoked first; no scanner payload is copied.":"Retained records regain independent visibility where their sources remain active. Archived records stay archived, and current canonical workflow edits remain. Undo does not restore an old approval or recreate purged data. Approved group evidence must be explicitly revoked first."}</p>
      {loading&&<p role="status">Validating current targets and sources...</p>}
      {plan&&<><ul className="space-y-2">{members.map(id=><li key={id} className="rounded border border-white/15 p-2"><p className="font-semibold">{(plan.members?.find(row=>row.finding_id===id)?.role==="canonical"||plan.context?.canonical_finding_id===id)?"Canonical finding: remains the primary record":"Retained alias: excluded from active counts while consolidated"}</p><p>{id}</p>{plan.findings?.filter(row=>row.id===id).map(row=><div key={row.id}><p>{row.description}</p>{row.severity&&<p>{enumLabel(row.severity)}{row.domain?` - ${DOMAIN_LABELS[row.domain]}`:""}</p>}<details><summary>Original source ownership</summary><p>{row.latest_observation?.filename||"Retained source"}</p><p>Scan: {row.scan_id}</p><p>Asset: {row.asset_id}</p></details></div>)}</li>)}</ul>
        {plan.source_counts&&<p>Retained sources: {plan.source_counts.scan} uploads, {plan.source_counts.asset} assets and {plan.source_counts.observation} observations.</p>}
      </>}
      {(plan||reason)&&<>
        <div><label htmlFor={reasonId} className="block text-sm">Review rationale</label><textarea id={reasonId} maxLength={2000} disabled={busy||unknown||!plan} className="mt-1 block w-full rounded border border-white/20 bg-navy p-2" value={reason} onChange={e=>setReason(e.target.value)}/></div>
        <label className="flex items-start gap-2"><input type="checkbox" disabled={busy||unknown||!plan} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I reviewed both source records and the visibility and scoring consequences.</label>
      </>}
      {error&&<p role="alert" className="text-red-300">{error}</p>}
      {unknown&&<p role="status">Outcome unknown. Retry the same request to check its saved receipt. Closing does not undo an operation that completed.</p>}
      {!loading&&!plan&&<button type="button" disabled={busy} className="text-cyan underline" onClick={()=>setRevision(value=>value+1)}>Reload and review current targets</button>}
      <footer className={DIALOG_FOOTER}><button type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={busy} onClick={()=>{if(unknown)onChanged();else onClose();}}>Cancel</button>
        <button type="button" className={DIALOG_PRIMARY} disabled={loading||busy||!plan||(!unknown&&(!confirmed||!reason.trim()))} onClick={()=>void save()}>{busy?"Saving...":unknown?"Retry same request":target.action==="apply"?"Consolidate pair":"Undo consolidation"}</button>
      </footer>
    </div>
  </FindingActionDialog>;
}

function GroupHistory({path,groupId}:{path:string;groupId:string}) {
  const [open,setOpen]=useState(false),[before,setBefore]=useState<number[]>([]);
  const cursor=before.at(-1);
  const history=useApi<{items:{id:string;version:number;state:string;rationale:string;actor_label:string;created_at:string}[];has_more:boolean}>(open?`${path}/${groupId}/history?limit=20${cursor?`&before_version=${cursor}`:""}`:null);
  return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>Group decision history</summary>{open&&<div className="mt-2 space-y-2">
    {history.loading&&<p role="status">Loading group decisions...</p>}{history.error&&<p role="alert">{history.error}</p>}
    {history.data?.items.map(row=><article key={row.id} className="rounded border border-white/10 p-2"><p>{row.actor_label} - {formatDateTime(row.created_at)} - Version {row.version} - {row.state==="active"?"Applied":"Undone"}</p><p className="whitespace-pre-wrap">{row.rationale}</p></article>)}
    <div className="flex flex-wrap gap-3"><button type="button" className="text-cyan underline disabled:opacity-50" disabled={history.loading||!before.length} onClick={()=>setBefore(v=>v.slice(0,-1))}>Newer group decisions</button>
      <button type="button" className="text-cyan underline disabled:opacity-50" disabled={history.loading||!!history.error||!history.data?.has_more} onClick={()=>{const value=history.data?.items.at(-1)?.version;if(value)setBefore(v=>[...v,value]);}}>Older group decisions</button></div>
  </div>}</details>;
}
