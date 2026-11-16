"use client";
import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { useDebounced } from "@/lib/useDebounced";
import { formatDateTime } from "@/lib/domain";
import { BUSINESS_CRITICALITY, ownerText, type AssetContext } from "@/lib/assetContext";
import FindingActionDialog from "./FindingActionDialog";
import { DIALOG_FOOTER,DIALOG_NEUTRAL,DIALOG_PRIMARY } from "./DialogActions";
type Props={orgId:string;orgName:string;assetId:string;assetName:string;writer:boolean;scannerEnvironment:string|null;scannerCriticality:string|null;onClose():void;onSaved():void};
const control="mt-1 w-full rounded border border-white/20 bg-navy px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none focus:ring-1 focus:ring-cyan disabled:opacity-50";
export default function AssetContextDialog(props:Props){
 const path=`/orgs/${props.orgId}/assets/${props.assetId}/context`;
 const current=useApi<AssetContext>(path);
 const [revision,setRevision]=useState(0),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[confirmReload,setConfirmReload]=useState(false);
 const inFlight=useRef(false),refreshOnClose=useRef(false),reloadButton=useRef<HTMLButtonElement>(null),wasPrompt=useRef(false);
 const [unknownOutcome,setUnknownOutcome]=useState(false);
 useEffect(()=>{if(!confirmReload&&wasPrompt.current)reloadButton.current?.focus();wasPrompt.current=confirmReload;},[confirmReload]);
 function close(){if(!inFlight.current){if(refreshOnClose.current)props.onSaved();props.onClose();}}
 function reload(){if(inFlight.current)return;setConfirmReload(false);setDirty(false);setRevision(x=>x+1);current.reload();}
 return <FindingActionDialog title="Asset context" orgName={props.orgName} onClose={close}>
  <div aria-busy={busy} className="min-w-0 space-y-4 text-sm [overflow-wrap:anywhere]">
   <p className="font-semibold">{props.assetName}</p>
   <p>Organization-managed ownership and business context. Imports preserve these values. They do not change finding workflow, scores or saved reports.</p>
   <p className="text-white/70">Scanner environment: {props.scannerEnvironment||"Not provided"} &middot; Scanner criticality: {props.scannerCriticality||"Not provided"}</p>
   <details><summary>Asset ID</summary><p>{props.assetId}</p></details>
   {current.loading?<p role="status">Loading asset context...</p>:current.error?<p role="alert">{current.error}</p>:current.data&&<>
    {!current.data.available?<p role="status">Asset context requires coordinated database activation.</p>:<>
     <dl className="grid gap-2 sm:grid-cols-2"><dt>Current owner</dt><dd>{ownerText(current.data)}</dd><dt>Managed environment</dt><dd>{current.data.environment||"Unknown"}</dd><dt>Business criticality</dt><dd>{BUSINESS_CRITICALITY[current.data.business_criticality||""]||"Unknown"}</dd></dl>
     <p className="text-xs text-white/60">Version {current.data.version}{current.data.updated_at?` - ${formatDateTime(current.data.updated_at)}`:" - No context saved"}</p>
    </>}
   </>}
   {unknownOutcome&&<p role="status">An earlier save had an unknown outcome. Inspect context history; closing or reloading does not cancel a submitted save.</p>}
   <button ref={reloadButton} type="button" disabled={busy||current.loading} className="text-cyan underline disabled:opacity-50" onClick={()=>dirty?setConfirmReload(true):reload()}>Reload saved context</button>
   {confirmReload&&<div className="space-y-2 rounded border border-amber-400/40 p-3"><p>Reload saved context and discard unsaved edits?</p><div className={DIALOG_FOOTER}><button type="button" className={DIALOG_NEUTRAL} onClick={()=>setConfirmReload(false)}>Keep editing</button><button type="button" className={DIALOG_PRIMARY} onClick={reload}>Reload and discard edits</button></div></div>}
   {current.data?.available&&<ContextHistory key={revision} path={path} disabled={busy}/>}
   {!current.loading&&!current.error&&current.data?.available&&props.writer&&!current.data.asset_archived?<ContextForm key={`${current.data.version}:${revision}`} saved={current.data} blocked={confirmReload} orgId={props.orgId} path={path} onDirty={setDirty} onUnknown={()=>{refreshOnClose.current=true;setUnknownOutcome(true);}} onBusy={value=>{inFlight.current=value;setBusy(value);}} onClose={close} onSaved={()=>{props.onSaved();props.onClose();}}/>:<footer className={DIALOG_FOOTER}><button type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={busy} onClick={close}>{props.writer?"Cancel":"Close"}</button></footer>}
  </div>
 </FindingActionDialog>;
}
function ContextForm({saved,blocked,orgId,path,onDirty,onBusy,onClose,onSaved,onUnknown}:{saved:AssetContext;blocked:boolean;orgId:string;path:string;onDirty(value:boolean):void;onBusy(value:boolean):void;onClose():void;onSaved():void;onUnknown():void}){
 const id=useId(),pending=useRef(false),cancel=useRef<HTMLButtonElement>(null);
 useEffect(()=>{cancel.current?.focus();},[]);
 const [owner,setOwner]=useState("keep"),[selectedLabel,setSelectedLabel]=useState("");
 const [environment,setEnvironment]=useState(saved.environment||""),[criticality,setCriticality]=useState(saved.business_criticality||"");
 const [reason,setReason]=useState(""),[query,setQuery]=useState(""),[offset,setOffset]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[unknown,setUnknown]=useState(false);
 const settled=useDebounced(query);
 const members=useApi<{items:{id:string;name:string|null;email:string}[];total:number}>(`/orgs/${orgId}/members?limit=50&offset=${offset}&q=${encodeURIComponent(settled)}&search_scope=identity&status=active&status=locked&status=must_change_password`);
 const selectedOwner=owner==="keep"?saved.owner_id:owner||null;
 const dirty=selectedOwner!==saved.owner_id||(environment.trim()||null)!==saved.environment||(criticality||null)!==saved.business_criticality;
 const known=members.data?.items.some(m=>m.id===owner);
 function changed(ownerValue:string,env:string,crit:string){onDirty((ownerValue==="keep"?saved.owner_id:ownerValue||null)!==saved.owner_id||(env.trim()||null)!==saved.environment||(crit||null)!==saved.business_criticality||!!reason.trim());}
 async function save(){if(blocked||pending.current||!dirty||!reason.trim()||error)return;pending.current=true;setBusy(true);onBusy(true);let success=false;
  const payload={expected_version:saved.version,environment:environment.trim()||null,business_criticality:criticality||null,rationale:reason.trim(),...(selectedOwner!==saved.owner_id?{owner_id:selectedOwner}:{})};
  try{await api.patch(path,payload);success=true;}
  catch(cause){const uncertain=!(cause instanceof ApiError)||cause.status===0||cause.status>=500||cause.status===408;setUnknown(uncertain);if(uncertain)onUnknown();setError(`${uncertain?"Outcome unknown; the save may have completed. Closing does not undo a completed save. ":""}${cause instanceof Error?cause.message:"Save failed"} Reload saved context and review history before saving again.`);}
  finally{pending.current=false;setBusy(false);onBusy(false);}
  if(success)onSaved();
 }
 return <form className="space-y-3" onSubmit={e=>{e.preventDefault();void save();}}>
  <label className="block" htmlFor={`${id}-search`}>Find asset owner</label><input id={`${id}-search`} type="search" value={query} disabled={blocked||busy||!!error} className={control} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/>
  <p className="text-xs text-white/60">Search organization members by name or email, then choose an owner. Searching alone does not change ownership.</p>
  {members.loading&&<p role="status">Loading owners...</p>}{members.error&&<p role="alert">{members.error} <button type="button" className="text-cyan underline" onClick={members.reload}>Retry owners</button></p>}
  <label className="block" htmlFor={`${id}-owner`}>Owner</label><select id={`${id}-owner`} value={owner} disabled={blocked||busy||!!error} className={control} onChange={e=>{setOwner(e.target.value);setSelectedLabel(e.target.selectedOptions[0].text);changed(e.target.value,environment,criticality);}}>
   <option value="keep">Keep current owner: {ownerText(saved)}</option><option value="">Unassigned</option>
   {owner!=="keep"&&owner&&!known&&<option value={owner}>{selectedLabel}</option>}
   {members.data?.items.map(m=><option key={m.id} value={m.id}>{m.name?`${m.name} (${m.email})`:m.email}</option>)}
  </select>
  <div className="flex gap-3 text-xs"><button type="button" disabled={blocked||busy||!!error||members.loading||offset===0} onClick={()=>setOffset(x=>x-50)}>Previous owners</button><button type="button" disabled={blocked||busy||!!error||members.loading||!members.data||offset+50>=members.data.total} onClick={()=>setOffset(x=>x+50)}>More owners</button></div>
  <label className="block" htmlFor={`${id}-environment`}>Organization-managed environment</label><input id={`${id}-environment`} maxLength={50} value={environment} disabled={blocked||busy||!!error} className={control} placeholder="Unknown" onChange={e=>{setEnvironment(e.target.value);changed(owner,e.target.value,criticality);}}/>
  <label className="block" htmlFor={`${id}-criticality`}>Business criticality</label><select id={`${id}-criticality`} value={criticality} disabled={blocked||busy||!!error} className={control} onChange={e=>{setCriticality(e.target.value as typeof criticality);changed(owner,environment,e.target.value);}}><option value="">Unknown</option>{Object.entries(BUSINESS_CRITICALITY).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>
  <label className="block" htmlFor={`${id}-reason`}>Change rationale</label><textarea id={`${id}-reason`} maxLength={2000} value={reason} disabled={blocked||busy||!!error} className={control} onChange={e=>{setReason(e.target.value);onDirty(dirty||!!e.target.value.trim());}}/>
  {error&&<p role="alert" className="text-red-300">{error}</p>}
  <footer className={DIALOG_FOOTER}><button ref={cancel} type="button" data-confirm-cancel className={DIALOG_NEUTRAL} disabled={blocked||busy} onClick={onClose}>{unknown?"Close and refresh":"Cancel"}</button><button className={DIALOG_PRIMARY} disabled={blocked||busy||!!error||!dirty||!reason.trim()}>{busy?"Saving...":"Save context"}</button></footer>
 </form>;
}
type Entry={id:string;actor_label:string;version:number;before:Record<string,string|null>;after:Record<string,string|null>;rationale:string;created_at:string};
function ContextHistory({path,disabled}:{path:string;disabled:boolean}){
 const [open,setOpen]=useState(false),[pages,setPages]=useState<number[]>([]);const before=pages.at(-1);
 const history=useApi<Entry[]>(open?`${path}/history?limit=20${before?`&before_version=${before}`:""}`:null);
 const fields:Record<string,string>={owner_id:"Owner",environment:"Environment",business_criticality:"Business criticality"};
 function value(row:Entry,side:"before"|"after",field:string){const v=row[side];return field==="owner_id"?v.owner_label||"Unassigned":field==="business_criticality"?BUSINESS_CRITICALITY[v[field]||""]||"Unknown":v[field]||"Unknown";}
 return <section aria-label="Asset context history" className="space-y-3 border-t border-white/15 pt-3"><button type="button" disabled={disabled} aria-expanded={open} className="text-cyan underline" onClick={()=>setOpen(x=>!x)}>{open?"Hide context history":"Show context history"}</button>
  {open&&<>{history.loading?<p role="status">Loading context history...</p>:history.error?<p role="alert">{history.error} <button type="button" onClick={history.reload}>Retry context history</button></p>:history.data?.length?<ol className="space-y-3">{history.data.map(row=><li key={row.id} className="space-y-1 rounded border border-white/15 p-3"><p>{row.actor_label} &middot; {formatDateTime(row.created_at)} &middot; Version {row.version}</p><p className="whitespace-pre-wrap">Rationale: {row.rationale}</p>{Object.entries(fields).filter(([field])=>row.before[field]!==row.after[field]).map(([field,label])=><p key={field}>{label}: {value(row,"before",field)} &rarr; {value(row,"after",field)}</p>)}</li>)}</ol>:<p>No context changes recorded.</p>}
   <div className="flex flex-wrap gap-3"><button type="button" disabled={disabled||history.loading||!pages.length} onClick={()=>setPages(x=>x.slice(0,-1))}>Newer context history</button><button type="button" disabled={disabled||history.loading||(history.data?.length||0)<20} onClick={()=>{const last=history.data?.at(-1);if(last)setPages(x=>[...x,last.version]);}}>Older context history</button></div>
  </>}
 </section>;
}
