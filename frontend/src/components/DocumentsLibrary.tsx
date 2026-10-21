"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import ConfirmPanel from "@/components/ConfirmPanel";
import {
  ACTIONS_CELL,
  DateRangeFilter,
  EmptyRow,
  FILTER_CELL,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW,
  ROW_ACTION,
  ROW_ACTION_DANGER,
  ROW_ACTION_VIEW,
  SELECT_CELL,
  SelectBox,
  SelectPageBox,
  SelectionAction,
  SelectionBar,
  TD,
  TH,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { api } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";

type Version = { id: string; number: number; edition: string; source: string; content_kind: string; rights: string; content_hash: string; current: boolean; retired_at: string | null; purged_at: string | null; indexes: { id: string; status: string; publish_version: boolean; error_message: string | null }[] };
type Document = { id: string; org_id: string | null; title: string; framework: string | null; created_at: string; versions: Version[] };
type Settings = { embedding_target: string; report_target: string; effective_embedding: string; embedding_granted: boolean; report_granted: boolean };
const INPUT = "rounded border border-white/20 bg-navy p-2 text-sm";
const PAGE_SIZE = 100;

function isReactivationPending(version: Version): boolean {
  return version.indexes.some(index => index.publish_version && ["pending", "running"].includes(index.status));
}

export default function DocumentsLibrary({ orgId, writable, platform = false }: { orgId?: string; writable: boolean; platform?: boolean }) {
  return <Suspense fallback={<p className="text-sm text-white/60">Loading documents…</p>}>
    <DocumentsList orgId={orgId} writable={writable} platform={platform} />
  </Suspense>;
}

function DocumentsList({ orgId, writable, platform }: { orgId?: string; writable: boolean; platform: boolean }) {
  const base = platform ? "/platform/documents" : `/orgs/${orgId}/documents`;
  const list = useListState(PAGE_SIZE, orgId ?? "platform");
  const { data, error, loading, reload } = useApi<{ items: Document[]; total: number }>(`${base}?${list.apiQuery}`);
  const facets = useApi<{ framework: string[] }>(`${base}/facets`);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ version: Version; documentTitle: string } | null>(null);
  const [bulkAction, setBulkAction] = useState<"retire" | "remove" | null>(null);
  const [replacement, setReplacement] = useState<Document | null>(null);
  const [results, setResults] = useState<{ citation_id: string; title: string; content: string; source: string; version: string }[]>([]);
  const retireSelection = useSelection(list, orgId ?? "platform-retire");
  const removeSelection = useSelection(list, orgId ?? "platform-remove");
  const pageDocuments = (data?.items ?? []).filter(d => platform || d.org_id === orgId);
  const retireable = pageDocuments.flatMap(d => d.versions
    .filter(v => !v.retired_at && !v.purged_at)
    .map(v => ({ id: v.id, name: `${d.title} · v${v.number}` })));
  const removable = pageDocuments.flatMap(d => d.versions
    .filter(v => v.retired_at && !v.current && !v.purged_at && !isReactivationPending(v))
    .map(v => ({ id: v.id, name: `${d.title} · v${v.number}` })));
  const waiting = data?.items.some(d => d.versions.some(v => v.indexes.some(i => ["pending", "running"].includes(i.status))));
  useEffect(() => { if (!waiting) return; const timer = setInterval(reload, 4000); return () => clearInterval(timer); }, [waiting, reload]);

  async function execute(action: () => Promise<unknown>) {
    setBusy(true); setMessage("");
    try { await action(); reload(); } catch (err) { setMessage(err instanceof Error ? err.message : "Request failed"); }
    finally { setBusy(false); }
  }
  function reactivate(version: Version, documentTitle: string) {
    removeSelection.set([{ id: version.id, name: `${documentTitle} · v${version.number}` }], false);
    void execute(() => api.post(`${base}/versions/${version.id}/reactivate`));
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("file") as File;
    const fields: Record<string, string> = {};
    for (const [key, value] of values) if (key !== "file") fields[key] = String(value);
    if (replacement) fields.document_id = replacement.id;
    await execute(async () => { await api.upload(base, file, fields); form.reset(); setReplacement(null); });
  }
  async function changeSelected(action: "retire" | "remove") {
    const selection = action === "retire" ? retireSelection : removeSelection;
    if (busy || selection.count === 0) return;
    setBusy(true);
    setMessage("");
    try {
      await api.post(`${base}/bulk-${action === "retire" ? "retire" : "remove"}${action === "remove" ? "?confirmed=true" : ""}`, { ids: selection.ids });
      selection.clear();
      setBulkAction(null);
      reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : `Failed to ${action} selected document versions`);
    } finally {
      setBusy(false);
    }
  }
  function selectedVersions(names: string[]) {
    const shown = names.slice(0, 10);
    return <ul className="mt-1 list-disc pl-5 text-xs text-white/70">
      {shown.map((name, index) => <li key={`${name}-${index}`}>{name}</li>)}
      {names.length > shown.length && <li>and {names.length - shown.length} more</li>}
    </ul>;
  }
  return <div className="space-y-4">
    <PageHeader title={platform ? "Shared standards" : "Documents"} total={data?.total} noun="documents" orgName={platform ? "the shared library" : "this organization"} filtered={list.hasFilters} note="Only indexed, current sources are used for retrieval. Summaries are not official full standards." />
    {(message) && <p role="alert" className="text-red-300">{message}</p>}
    {!platform && orgId && <ConsentSettings key={orgId} orgId={orgId} writable={writable} />}
    {platform && <><EmbeddingSettings /><button disabled={busy} className={INPUT} onClick={() => execute(() => api.post(`${base}/load-baseline`))}>Queue baseline: NIST catalog and CIS/ISO source references</button></>}
    {writable && <details className="rounded border border-white/10 p-4" open={replacement ? true : undefined}>
      <summary>{replacement ? `New version of ${replacement.title}` : "Upload document"}</summary>
      <p className="mt-2 text-xs text-white/60">New versions preserve earlier content. Matching SHA-256 content and edition on this document reuses its existing version.</p>
      <form onSubmit={upload} className="mt-3 grid gap-3 sm:grid-cols-2">
        <label>Title<input className={`${INPUT} block w-full`} name="title" required maxLength={255} defaultValue={replacement?.title} key={`${replacement?.id ?? "new"}-title`} /></label>
        <label>Framework<select className={`${INPUT} block w-full`} name="framework" defaultValue={replacement?.framework ?? ""} key={`${replacement?.id ?? "new"}-framework`}><option value="">Organization policy / general</option>{["CIS", "NIST", "ISO"].map(f => <option key={f}>{f}</option>)}</select></label>
        <label>Edition / version<input className={`${INPUT} block w-full`} name="edition" required maxLength={100} /></label>
        <label>Source reference<input className={`${INPUT} block w-full`} name="source" required maxLength={1000} /></label>
        <label>Content kind<select className={`${INPUT} block w-full`} name="content_kind"><option value="original_summary">Original summary</option>{!platform && <option value="organization_policy">Organization policy</option>}<option value="official">Authorized official text</option><option value="reference">Reference only (not retrieval evidence)</option></select></label>
        <label>Usage rights / authorization<input className={`${INPUT} block w-full`} name="rights" required maxLength={2000} /></label>
        <label>UTF-8 text or Markdown, up to 10 MiB<input className="block" type="file" name="file" accept=".txt,.md,.markdown" required /></label>
        <div><button className={INPUT} disabled={busy}>Queue processing</button>{replacement && <button type="button" className="ml-3 underline" onClick={() => setReplacement(null)}>Cancel new version</button>}</div>
      </form>
    </details>}
    {confirm && <ConfirmPanel
      label="Remove retired document version"
      message={<>Permanently remove <strong>{confirm.documentTitle} · version {confirm.version.number}</strong>? Its text and embeddings will be deleted. Completed reports retain their captured excerpts and provenance.</>}
      confirmLabel={busy ? "Removing…" : "Remove permanently"}
      onConfirm={() => void execute(async () => { await api.post(`${base}/versions/${confirm.version.id}/purge?confirmed=true`); setConfirm(null); })}
      onCancel={() => setConfirm(null)}
      busy={busy}
      danger
    />}
    <ListToolbar list={list} label="documents">
      <DateRangeFilter list={list} label="Added" />
    </ListToolbar>
    <SelectionBar selection={retireSelection}>
      <SelectionAction onClick={() => setBulkAction("retire")} disabled={busy}>Retire selected</SelectionAction>
    </SelectionBar>
    <SelectionBar selection={removeSelection}>
      <SelectionAction onClick={() => setBulkAction("remove")} disabled={busy} danger>Remove selected permanently</SelectionAction>
    </SelectionBar>
    {bulkAction && (() => {
      const selection = bulkAction === "retire" ? retireSelection : removeSelection;
      const names = selection.names(selection.ids);
      return <ConfirmPanel
        label={bulkAction === "retire" ? "Retire selected document versions" : "Remove selected document versions"}
        message={<>
          {bulkAction === "retire"
            ? <>Retire {selection.count} selected {selection.count === 1 ? "version" : "versions"}?</>
            : <>Permanently remove {selection.count} selected {selection.count === 1 ? "version" : "versions"}? Their text and embeddings will be deleted. Completed reports retain captured excerpts and provenance.</>}
          {selectedVersions(names)}
        </>}
        confirmLabel={busy ? (bulkAction === "retire" ? "Retiring…" : "Removing…") : (bulkAction === "retire" ? "Retire versions" : "Remove permanently")}
        onConfirm={() => void changeSelected(bulkAction)}
        onCancel={() => setBulkAction(null)}
        busy={busy}
        danger={bulkAction === "remove"}
      />;
    })()}
    <StatusMessage loading={loading && !data} error={error} />
    <ListTable><thead className={THEAD}>
      <tr>
        <th className={SELECT_CELL}>
          <div className="space-y-2">
            <label className="flex items-center gap-1 text-[10px] normal-case tracking-normal"><SelectPageBox selection={retireSelection} rows={retireable} />Retire</label>
            <label className="flex items-center gap-1 text-[10px] normal-case tracking-normal"><SelectPageBox selection={removeSelection} rows={removable} />Remove</label>
          </div>
        </th>
        <SortHeader label="Document" column="title" list={list} />
        <SortHeader label="Framework" column="framework" list={list} />
        <SortHeader label="Versions and processing" column="version" list={list} />
        <SortHeader label="Added" column="created" list={list} defaultSort="created" defaultOrder="desc" />
        <th className={`${TH} text-right`}>Actions</th>
      </tr>
      <tr>
        <th className={FILTER_CELL} />
        <th className={FILTER_CELL}><TextFilter name="title" label="title" list={list} /></th>
        <th className={FILTER_CELL}><PickFilter name="framework" label="framework" list={list} options={facetOptions(facets.data?.framework, { "": "Policy" })} /></th>
        <th className={FILTER_CELL}><TextFilter name="version" label="versions and processing" list={list} /></th>
        <th className={FILTER_CELL} />
        <th className={FILTER_CELL} />
      </tr>
    </thead>
      <tbody>{loading && !data ? <tr><td colSpan={6} className="px-4 py-8 text-center text-white/50">Loading documents…</td></tr> :
        error ? null : !data?.items.length ? <EmptyRow colSpan={6} noun="documents" filtered={list.hasFilters} /> :
          data.items.map(d => <tr key={d.id} className={ROW}>
            <td className={SELECT_CELL}><div className="space-y-3">{d.versions.map(v => <div key={v.id}>
              {!v.retired_at && !v.purged_at && (platform || d.org_id === orgId) && <SelectBox selection={retireSelection} id={v.id} name={`${d.title} · v${v.number} (retire)`} />}
              {v.retired_at && !v.current && !v.purged_at && !isReactivationPending(v) && (platform || d.org_id === orgId) && <SelectBox selection={removeSelection} id={v.id} name={`${d.title} · v${v.number} (remove)`} />}
            </div>)}</div></td>
            <td className={TD}>{d.title}<p className="text-xs text-white/50">{d.org_id ? "Organization" : "Shared"}</p></td>
            <td className={TD}>{d.framework ?? "Policy"}</td>
            <td className={TD}>{d.versions.map(v => <div key={v.id} className="mb-3">
              <strong>v{v.number} · {v.edition}</strong> — {v.purged_at ? "Removed" : v.retired_at ? "Retired" : v.current ? "Current" : "Unpublished"}
              <p className="text-xs">{v.content_kind} · {v.source}</p><p className="text-xs">Rights: {v.rights}</p>
              <p className="break-all text-xs text-white/50">SHA-256: {v.content_hash}</p>
              {v.indexes.map(i => <p key={i.id} className={`text-xs ${i.status === "ready" ? "text-emerald-300" : i.status === "failed" ? "text-red-300" : i.status === "running" ? "text-cyan" : "text-white/60"}`}>{i.publish_version && ["pending", "running"].includes(i.status) ? "reactivating · " : ""}{i.status}{i.error_message ? `: ${i.error_message}` : ""}</p>)}
            </div>)}</td>
            <td className={TD}>{formatDateTime(d.created_at)}</td>
            <td className={ACTIONS_CELL}>{d.versions.map(v => <div key={v.id} className="mb-3 flex flex-wrap justify-end gap-3">
              <button className={ROW_ACTION_VIEW} onClick={() => execute(async () => { const p = await api.get<{ content: string }>(`${base}/versions/${v.id}`); setPreview(p.content); })}>Preview v{v.number}</button>
              {writable && (platform || d.org_id === orgId) && !v.purged_at && <>{!v.retired_at && <><button disabled={busy} className={ROW_ACTION} onClick={() => execute(() => api.post(`${base}/versions/${v.id}/reindex`))}>Index / retry</button><button disabled={busy} className={ROW_ACTION} onClick={() => execute(() => api.post(`${base}/versions/${v.id}/retire`))}>Retire</button></>}{v.retired_at && !v.current && <><button disabled={busy || isReactivationPending(v)} className={ROW_ACTION} onClick={() => reactivate(v, d.title)}>{isReactivationPending(v) ? "Reactivating…" : `Reactivate v${v.number}`}</button>{!isReactivationPending(v) && <button className={ROW_ACTION_DANGER} onClick={() => setConfirm({ version: v, documentTitle: d.title })}>Remove</button>}</>}</>}
            </div>)}{writable && (platform || d.org_id === orgId) && <button className={ROW_ACTION} onClick={() => setReplacement(d)}>New version</button>}</td>
          </tr>)}
      </tbody></ListTable>
    <Pager offset={list.offset} limit={PAGE_SIZE} total={data?.total ?? 0} onChange={list.setOffset} />
    {preview !== null && <section className="w-full min-w-0 max-w-full overflow-hidden"><button className="underline" onClick={() => setPreview(null)}>Close preview</button><pre className="max-h-96 w-full min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded bg-black/20 p-4">{preview}</pre></section>}
    {!platform && <form onSubmit={e => { e.preventDefault(); const query = String(new FormData(e.currentTarget).get("query")); void execute(async () => { const r = await api.post<{ items: typeof results }>(`${base}/search`, { query }); setResults(r.items); }); }} className="space-y-3"><label>Search permitted evidence<input name="query" required maxLength={1200} className={`${INPUT} ml-3`} /></label><button disabled={busy} className={`${INPUT} ml-3`}>Search</button>{results.map(r => <article key={r.citation_id} className="w-full min-w-0 max-w-full overflow-hidden rounded border border-white/10 p-3"><h3>{r.title} — {r.version}</h3><p className="break-words text-xs [overflow-wrap:anywhere]">{r.source} · {r.citation_id}</p><p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{r.content}</p></article>)}</form>}
  </div>;
}

function ConsentSettings({ orgId, writable }: { orgId: string; writable: boolean }) {
  const base = `/orgs/${orgId}/documents/settings`;
  const { data, error, reload } = useApi<Settings>(base);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function change(purpose: "embedding" | "report", granted: boolean, target: string) {
    setBusy(true);
    try { await api.put(`${base}/consent`, { purpose, granted, target }); reload(); setMessage(""); }
    catch (err) { setMessage(err instanceof Error ? err.message : "Consent update failed"); }
    finally { setBusy(false); }
  }
  return <details className="rounded border border-white/10 p-4"><summary>Data processing consent</summary>{(error || message) && <p role="alert">{error || message}</p>}{data && <div className="space-y-3 text-sm"><p>Current retrieval: {data.effective_embedding}</p><p>External embeddings send document text and search queries to {data.embedding_target}. Without approval, this organization uses the local index.</p><p>AI reports send sampled findings and retrieved excerpts to {data.report_target}. Approval is separate from embeddings. Revocation stops future calls, not data already sent.</p>{writable && <>{!data.embedding_target.startsWith("local:") && <button disabled={busy} className={INPUT} onClick={() => change("embedding", !data.embedding_granted, data.embedding_target)}>{data.embedding_granted ? "Revoke" : "Approve"} external embeddings</button>}<button disabled={busy} className={`${INPUT} ml-3`} onClick={() => change("report", !data.report_granted, data.report_target)}>{data.report_granted ? "Revoke" : "Approve"} external AI reports</button></>}</div>}</details>;
}

function EmbeddingSettings() {
  const [message, setMessage] = useState("");
  return <details className="rounded border border-white/10 p-4">
    <summary>Platform embedding configuration</summary>
    <p className="text-sm">Local BGE-M3 is the default. Model setup is performed on the server, never downloaded by a page request. External credentials stay on the server. Reindex current sources after selecting a different model.</p>
    <form className="mt-3 flex flex-wrap gap-3" onSubmit={async e => {
      e.preventDefault();
      const f = new FormData(e.currentTarget);
      try {
        await api.put("/platform/documents/embedding-profile", {
          provider: f.get("provider"), model: f.get("model"), revision: f.get("revision"),
          dimensions: Number(f.get("dimensions")), approve_shared_external_processing: f.get("approve") === "on",
        });
        setMessage("Profile selected. Organization consent is still required for external processing.");
      } catch (err) { setMessage(err instanceof Error ? err.message : "Configuration failed"); }
    }}>
      <select aria-label="Provider" name="provider" className={INPUT}>
        <option value="local">Local BGE-M3</option><option value="openai">OpenAI</option><option value="voyage">Voyage</option>
      </select>
      <input aria-label="Model" name="model" required defaultValue="BAAI/bge-m3" className={INPUT} />
      <input aria-label="Model revision" name="revision" required defaultValue="5617a9f61b028005a4858fdac845db406aefb181" className={INPUT} />
      <input aria-label="Vector dimensions" name="dimensions" type="number" required defaultValue={1024} className={INPUT} />
      <label><input type="checkbox" name="approve" /> Approve external processing of shared standards and queries</label>
      <button className={INPUT}>Select profile</button>
    </form>
    {message && <p role="status">{message}</p>}
  </details>;
}
