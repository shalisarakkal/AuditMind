"use client";
import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { enumLabel } from "@/lib/presentation";
import { formatDateTime } from "@/lib/domain";
import FindingActionDialog from "./FindingActionDialog";
import { DIALOG_FOOTER,DIALOG_NEUTRAL,DIALOG_PRIMARY } from "./DialogActions";
import type { PublicationSetting } from "./PublicationSettings";
type Props={orgId:string;findingId:string;observationId?:string;disabled?:boolean;hasWorkflowDraft?:boolean;onBusyChange?(value:boolean):void;onChanged():void};
type Value={value:unknown;truncated:boolean;bytes:number;sha256:string};
type Plan={finding_id:string;observation_id:string;operation:"publish"|"undo";expected_version:number;review_token:string;apply_available:boolean;no_op:boolean;
 changes:{field:string;before:Value;after:Value;removal:boolean}[];provenance:{original_filename:string|null;observation_filename:string|null;recorded_at:string;observed_at:string|null}};
function valueText(value:Value,field:string){return value.value===null?"Not set":typeof value.value==="string"?field==="severity"?enumLabel(value.value):value.value:JSON.stringify(value.value);}
export default function PublicationAction(props:Props) {
 const [open,setOpen]=useState(false);
 const setting=useApi<PublicationSetting>(`/orgs/${props.orgId}/observation-publication/settings`);
 const undo=!props.observationId;
 return <section aria-label={undo?"Undo scanner-field publication":"Publish reviewed scanner fields"} className="mt-3 space-y-2 text-sm">
  {setting.loading&&<p role="status">Checking publication availability...</p>}
  {setting.error&&<p role="alert">{setting.error} <button type="button" className="text-cyan underline" onClick={setting.reload}>Retry action availability</button></p>}
  {setting.data&&!setting.loading&&!setting.error&&<>
   {!setting.data.available?<p>{setting.data.reason}</p>:!undo&&!setting.data.enabled?<p>New scanner-field publication is Off in organization Settings.</p>:null}
   {props.hasWorkflowDraft&&<p role="status">Save or clear the unsaved workflow draft before publication or Undo.</p>}
   <button type="button" className="text-cyan underline disabled:opacity-50" disabled={props.disabled||props.hasWorkflowDraft||!setting.data.available||(!undo&&!setting.data.enabled)} onClick={()=>setOpen(true)}>{undo?"Review Undo publication":"Review publication"}</button>
  </>}
  {open&&<Review key={`${props.orgId}:${props.findingId}:${props.observationId||"undo"}`} {...props} onClose={()=>{setOpen(false);setting.reload();}}/>}
 </section>;
}
function Review({orgId,findingId,observationId,onBusyChange,onChanged,onClose}:Props&{onClose():void}) {
 const root=`/orgs/${orgId}/observation-publication/findings/${findingId}`;
 const endpoint=observationId?`${root}/observations/${observationId}`:root;
 const [plan,setPlan]=useState<Plan|null>(null),[revision,setRevision]=useState(0),[loading,setLoading]=useState(true);
 const [reason,setReason]=useState(""),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[unknown,setUnknown]=useState(false);
 const reasonId=useId(),inFlight=useRef(false),request=useRef<Record<string,unknown>|null>(null);
 useEffect(()=>{let current=true;setLoading(true);setPlan(null);setConfirmed(false);setError(null);request.current=null;
  api.post<Plan>(endpoint+(observationId?"/preview":"/undo-preview"),{}).then(result=>{if(current)setPlan(result);}).catch(cause=>{if(current)setError(cause instanceof Error?cause.message:"Review unavailable");}).finally(()=>{if(current)setLoading(false);});
  return ()=>{current=false;};
 },[endpoint,observationId,revision]);
 function close(){if(inFlight.current)return;if(unknown)onChanged();else onClose();}
 async function save(){if(inFlight.current||!plan||!plan.apply_available||(!request.current&&(!confirmed||!reason.trim())))return;
  if(!request.current)request.current={request_id:crypto.randomUUID(),expected_version:plan.expected_version,review_token:plan.review_token,rationale:reason.trim(),confirm:true};
  inFlight.current=true;setBusy(true);onBusyChange?.(true);setError(null);let success=false;
  try{await api.post(endpoint+(observationId?"/publish":"/undo"),request.current);success=true;}
  catch(cause){setError(cause instanceof Error?cause.message:"No response was received");
   const definite=cause instanceof ApiError&&cause.status>=400&&cause.status<500&&cause.status!==408;
   // A denied retry cannot prove whether the FIRST uncertain request committed.
   if(unknown||!definite)setUnknown(true);
   else{request.current=null;setPlan(null);setConfirmed(false);}
  }finally{inFlight.current=false;setBusy(false);onBusyChange?.(false);}
  if(success)onChanged();
 }
 return <FindingActionDialog title={observationId?"Publish reviewed scanner fields":"Undo scanner-field publication"} orgName="One fixed finding" onClose={close}>
  <div aria-busy={busy} className="min-w-0 space-y-3 text-sm [overflow-wrap:anywhere]">
   <p>Only reviewed scanner fields change. Finding ID, original import/asset ownership, workflow status, assignee, notes and deadlines remain. Scores may change and evidence coverage becomes stale. Stored reports remain unchanged.</p>
   {!observationId&&<p>Undo restores the exact retained before-snapshot, preserves current workflow and does not revive an old approval. It cannot reconstruct purged data.</p>}
   <details><summary>Fixed target</summary><p>Finding ID: {findingId}</p>{observationId&&<p>Observation ID: {observationId}</p>}</details>
   {loading&&<p role="status">Validating current source and publication generation...</p>}
   {plan&&<><p>Original owner import: {plan.provenance.original_filename||"Retained import"}</p><p>Decision observation source: {plan.provenance.observation_filename||"Retained import"}</p><p>Server recorded: {formatDateTime(plan.provenance.recorded_at)}</p>
    <p>Source observed time: {plan.provenance.observed_at?formatDateTime(plan.provenance.observed_at):"Not provided"}</p>
    {plan.no_op?<p>No scanner-field differences. Publication is not needed.</p>:<dl className="space-y-3">{plan.changes.map(change=><div key={change.field} className="min-w-0 rounded border border-white/15 p-2"><dt className="font-semibold">{enumLabel(change.field)}{change.removal?" (would be cleared)":""}</dt><dd className="grid min-w-0 gap-2 sm:grid-cols-2">{(["before","after"] as const).map(side=><div key={side} className="min-w-0"><p className="font-semibold">{side==="before"?"Current":"Reviewed result"}</p><p className="whitespace-pre-wrap">{valueText(change[side],change.field)}</p>{change[side].truncated&&<p>Display shortened; the full value was compared.</p>}<details><summary>Value fingerprint</summary><p>{change[side].bytes} bytes</p><p>{change[side].sha256}</p></details></div>)}</dd></div>)}</dl>}
   </>}
   {(plan?.apply_available||reason)&&<><label htmlFor={reasonId} className="block">Publication review rationale</label><textarea id={reasonId} maxLength={2000} className="w-full rounded border border-white/20 bg-navy p-2" disabled={busy||unknown||!plan} value={reason} onChange={event=>setReason(event.target.value)}/>
    <label className="flex items-start gap-2"><input type="checkbox" disabled={busy||unknown||!plan} checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/>I reviewed this source, scanner-field changes and scoring consequences; current workflow and original ownership will be preserved.</label></>}
   {error&&<p role="alert" className="text-red-300">{error}</p>}
   {unknown&&<p role="status">Outcome unknown. Retry the same request to check its saved receipt, or close and inspect publication history. Closing does not cancel an operation that completed. A failed retry does not establish the original outcome.</p>}
   {!loading&&!plan&&!unknown&&<button type="button" className="text-cyan underline" disabled={busy} onClick={()=>setRevision(value=>value+1)}>Reload and review current source</button>}
   <footer className={DIALOG_FOOTER}><button type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={busy} onClick={close}>{unknown?"Close and refresh":"Cancel"}</button>
    <button type="button" className={DIALOG_PRIMARY} disabled={loading||busy||!plan?.apply_available||(!unknown&&(!confirmed||!reason.trim()))} onClick={()=>void save()}>{busy?"Saving...":unknown?"Retry same request":observationId?"Publish scanner fields":"Undo publication"}</button></footer>
  </div>
 </FindingActionDialog>;
}
