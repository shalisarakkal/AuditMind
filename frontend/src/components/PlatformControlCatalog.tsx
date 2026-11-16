"use client";
import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import type { Catalogs } from "@/lib/controlCatalog";
import ControlCatalogBrowser from "./ControlCatalogBrowser";
import { DIALOG_NEUTRAL, DIALOG_PRIMARY } from "./DialogActions";

export default function PlatformControlCatalog() {
  const catalogs = useApi<Catalogs>("/platform/control-catalogs");
  const [release, setRelease] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  async function install() {
    if (pending.current || error) return;
    pending.current = true; setBusy(true);
    try { await api.post("/platform/control-catalogs/baseline", {}); catalogs.reload(); }
    catch (cause) {
      const uncertain = !(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500 || cause.status === 408;
      setError(`${uncertain ? "Outcome unknown; the installation may have finished. " : "Installation refused. "}${cause instanceof Error ? cause.message : "Installation failed"}. Reload releases before trying again.`);
    }
    finally { pending.current = false; setBusy(false); }
  }
  return <div className="min-w-0 space-y-5 [overflow-wrap:anywhere]">
    <h1 className="text-2xl font-semibold">Control catalog</h1>
    <p className="text-sm text-white/70">Install retained control releases independently of the AI knowledge base. The verified bundled NIST CSF 2.0 source contains 106 current outcomes; withdrawn entries are not offered. No AI or embedding calls are made.</p>
    <p className="text-sm text-white/70">CIS/ISO full text is not included. A control reference is not a compliance pass or certification. Existing scores and report snapshots are unchanged.</p>
    <div className="flex flex-wrap gap-3"><button type="button" className={DIALOG_NEUTRAL} disabled={busy || catalogs.loading} onClick={() => { setError(null); catalogs.reload(); }}>Reload catalog releases</button><button type="button" className={DIALOG_PRIMARY} disabled={busy || catalogs.loading || !!error || !catalogs.data?.available} onClick={() => void install()}>{busy ? "Installing…" : "Install verified NIST baseline"}</button></div>
    {busy && <p role="status">Installing the catalog transaction. Leaving this page does not cancel the request.</p>}
    {error && <p role="alert">{error}</p>}
    {catalogs.loading ? <p role="status">Loading catalog releases…</p> : catalogs.error ? <p role="alert">{catalogs.error}</p> : !catalogs.data?.available ? <p role="status">Control catalog requires coordinated database activation.</p> : <ControlCatalogBrowser catalogs={catalogs.data.items} basePath="/platform/control-catalogs" value={release || catalogs.data.items[0]?.id || ""} onChange={setRelease} />}
  </div>;
}
