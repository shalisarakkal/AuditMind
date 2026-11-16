"use client";
import { useId, useState } from "react";
import { useApi } from "@/lib/useApi";
import type { Catalog, CatalogControls } from "@/lib/controlCatalog";

export const CATALOG_INPUT = "w-full rounded border border-white/20 bg-navy px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none focus:ring-1 focus:ring-cyan disabled:opacity-50";

export default function ControlCatalogBrowser({ catalogs, basePath, value, onChange, selected, onSelection, disabled = false }: {
  catalogs: Catalog[]; basePath: string; value: string; onChange(value: string): void; selected?: string[]; onSelection?(value: string[]): void; disabled?: boolean;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const controls = useApi<CatalogControls>(value ? `${basePath}/${value}` : null);
  const visible = controls.data?.controls.filter(c => `${c.reference} ${c.title} ${c.description}`.toLowerCase().includes(query.toLowerCase())) || [];
  const release = controls.data?.catalog;
  return <section aria-label="Versioned control catalog" className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
    <label className="block text-sm" htmlFor={`${id}-release`}>Catalog release</label>
    <select id={`${id}-release`} className={CATALOG_INPUT} value={value} disabled={disabled || !catalogs.length} onChange={e => { setQuery(""); onChange(e.target.value); }}>
      {!value && <option value="">Choose a release</option>}
      {catalogs.map(c => <option key={c.id} value={c.id}>{c.framework} · {c.edition}</option>)}
    </select>
    {!catalogs.length && <p>No catalog installed. A platform administrator can install the verified NIST baseline.</p>}
    {controls.loading && <p role="status">Loading controls…</p>}
    {controls.error && <p role="alert">{controls.error} <button type="button" className="text-cyan underline" disabled={disabled} onClick={controls.reload}>Retry controls</button></p>}
    {!controls.loading && !controls.error && release && <>
      <p className="text-sm text-white/70">{release.rights}</p>
      <details className="text-xs text-white/60"><summary>Catalog provenance</summary><p>{release.title}</p><p>{release.source}</p><p>SHA256: {release.content_hash}</p><p>Release ID: {release.id}</p></details>
      <label className="block text-sm" htmlFor={`${id}-search`}>Find a control</label>
      <input id={`${id}-search`} type="search" className={CATALOG_INPUT} value={query} disabled={disabled} onChange={e => setQuery(e.target.value)} />
      {onSelection && <p className="text-xs text-white/70">{selected?.length || 0} selected (maximum 20). Selected references: {controls.data?.controls.filter(c => selected?.includes(c.control_id)).map(c => c.reference).join(", ") || "None"}.</p>}
      <ul className="max-h-72 space-y-2 overflow-y-auto rounded border border-white/10 p-3">
        {visible.map(c => <li key={c.control_id} className="space-y-1 border-b border-white/10 pb-2 text-sm">
          {onSelection ? <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-cyan" checked={selected?.includes(c.control_id) || false} disabled={disabled || (!selected?.includes(c.control_id) && (selected?.length || 0) >= 20)} onChange={e => onSelection(e.target.checked ? [...(selected || []), c.control_id] : selected?.filter(id => id !== c.control_id) || [])} /><span>{c.title}</span></label> : <p>{c.title}</p>}
          <details><summary className="text-xs text-cyan">Read outcome {c.reference}</summary><p className="whitespace-pre-wrap text-white/75">{c.description}</p></details>
        </li>)}
      </ul>
      {!visible.length && <p>No controls match this search.</p>}
    </>}
  </section>;
}
