"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import StatusMessage from "./StatusMessage";
import { DIALOG_PRIMARY } from "./DialogActions";

type Setting={enabled:boolean;version:number};
export default function ConsolidationSettings({orgId,editable}:{orgId:string;editable:boolean}) {
  const path=`/orgs/${orgId}/finding-consolidations/settings`;
  const saved=useApi<Setting>(path);
  return <section aria-label="Reviewed finding consolidation" className="min-w-0 space-y-3 rounded-xl border border-white/10 p-5">
    <h2 className="text-lg font-semibold">Reviewed finding consolidation</h2>
    <p className="text-sm text-white/70">Optional native Nessus pair review. An administrator can count an independently reviewed pair once while retaining both source records and histories. Disabled by default; separate from scoring settings. Turning this off blocks new consolidations and does not undo existing pairs.</p>
    <StatusMessage loading={saved.loading} error={saved.error}/>
    <button type="button" className="text-cyan underline" onClick={saved.reload}>Reload consolidation setting</button>
    {saved.data && <><p>New pair consolidation: {saved.data.enabled?"On":"Off"}.</p>{editable?<SettingForm key={saved.data.version} path={path} saved={saved.data} onSaved={saved.reload}/>:<p className="text-sm text-white/60">Read-only: an organization administrator manages this setting.</p>}</>}
  </section>;
}
function SettingForm({path,saved,onSaved}:{path:string;saved:Setting;onSaved():void}) {
  const [enabled,setEnabled]=useState(saved.enabled),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const pending=useRef(false);
  async function save(){if(pending.current)return;pending.current=true;setBusy(true);setError(null);
    try{await api.patch(path,{expected_version:saved.version,enabled});onSaved();}
    catch(cause){setError(cause instanceof Error?cause.message:"Could not save consolidation setting");}
    finally{pending.current=false;setBusy(false);}}
  return <form onSubmit={event=>{event.preventDefault();void save();}} className="space-y-3">
    <label className="flex items-center gap-2"><input type="checkbox" checked={enabled} disabled={busy||!!error} onChange={e=>setEnabled(e.target.checked)}/>Allow reviewed native pair consolidation</label>
    {error&&<p role="alert">{error} Reload the saved setting before retrying.</p>}
    <button className={DIALOG_PRIMARY} disabled={busy||!!error||enabled===saved.enabled}>{busy?"Saving...":"Save consolidation setting"}</button>
  </form>;
}
