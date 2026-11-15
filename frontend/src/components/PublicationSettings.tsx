"use client";
import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { DIALOG_PRIMARY } from "./DialogActions";
export type PublicationSetting={available:boolean;enabled:boolean;version:number;reason:string|null};
export default function PublicationSettings({orgId,editable}:{orgId:string;editable:boolean}) {
 const path=`/orgs/${orgId}/observation-publication/settings`;
 const saved=useApi<PublicationSetting>(path);const [reload,setReload]=useState(0);
 function refresh(){setReload(value=>value+1);saved.reload();}
 return <section aria-label="Scanner-field publication setting" className="min-w-0 space-y-3 rounded-xl border border-white/10 p-5 [overflow-wrap:anywhere]">
  <h2 className="text-lg font-semibold">Scanner-field publication</h2>
  <p className="text-sm text-white/70">Off by default. An organization administrator can publish reviewed native scanner fields onto one finding. Original ownership and workflow remain. Scores may change and evidence coverage is invalidated; saved reports stay unchanged. Turning this off blocks new publications and still permits authorized Undo.</p>
  {saved.loading&&<p role="status">Loading publication setting...</p>}
  {saved.error&&<p role="alert">{saved.error}</p>}
  <button type="button" className="text-cyan underline" disabled={saved.loading} onClick={refresh}>Reload publication setting</button>
  {!saved.loading&&!saved.error&&saved.data&&<><p>New scanner-field publication: {saved.data.enabled?"On":"Off"}.</p>
   {!saved.data.available?<p role="status">{saved.data.reason}</p>:editable?<SettingForm key={`${saved.data.version}:${reload}`} path={path} saved={saved.data} onSaved={refresh}/>:<p className="text-sm text-white/70">Read-only: an organization administrator manages this setting.</p>}
  </>}
 </section>;
}
function SettingForm({path,saved,onSaved}:{path:string;saved:PublicationSetting;onSaved():void}) {
 const [enabled,setEnabled]=useState(saved.enabled),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
 const pending=useRef(false);
 async function save(){if(pending.current)return;pending.current=true;setBusy(true);setError(null);let success=false;
  try{await api.patch(path,{expected_version:saved.version,enabled});success=true;}
  catch(cause){const uncertain=!(cause instanceof ApiError)||cause.status===0||cause.status>=500||cause.status===408;setError(`${uncertain?"Outcome unknown. ":""}${cause instanceof Error?cause.message:"Setting save failed"} Reload the saved setting before trying again.`);}
  finally{pending.current=false;setBusy(false);}
  if(success)onSaved();
 }
 return <form className="space-y-3" onSubmit={event=>{event.preventDefault();void save();}}>
  <label className="flex items-start gap-2"><input type="checkbox" disabled={busy||!!error} checked={enabled} onChange={event=>setEnabled(event.target.checked)}/><span>Allow reviewed scanner-field publication</span></label>
  {error&&<p role="alert">{error}</p>}
  <button className={DIALOG_PRIMARY} disabled={busy||!!error||enabled===saved.enabled}>{busy?"Saving...":"Save publication setting"}</button>
 </form>;
}
