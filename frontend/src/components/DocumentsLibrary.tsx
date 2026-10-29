"use client";

import { FormEvent, Fragment, Suspense, useEffect, useRef, useState } from "react";
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
  StatusBadge,
  TD,
  TH,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { api } from "@/lib/apiClient";
import { documentFileError } from "@/lib/uploadValidation";
import { formatDateTime } from "@/lib/domain";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";

type Version = { id: string; number: number; edition: string; source: string; content_kind: string; rights: string; content_hash: string; current: boolean; retired_at: string | null; purged_at: string | null; indexes: { id: string; status: string; publish_version: boolean; error_message: string | null }[] };
type Document = { id: string; org_id: string | null; title: string; framework: string | null; created_at: string; versions: Version[] };
type Settings = { embedding_target: string; report_target: string; effective_embedding: string; embedding_granted: boolean; report_granted: boolean };
const INPUT = "rounded border border-white/20 bg-navy p-2 text-sm";
const PRIMARY = "rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50";
const SECONDARY = "rounded-md border border-white/20 px-3 py-1.5 text-sm text-white/80 hover:bg-white/5 disabled:opacity-50";
const PAGE_SIZE = 100;
const PROCESSING_LABELS: Record<string, string> = { pending: "Queued", running: "Processing", ready: "Ready", failed: "Failed", cancelled: "Cancelled" };

function isReactivationPending(version: Version): boolean {
  return Boolean(version.retired_at && !version.purged_at && version.indexes.some(index => index.publish_version && ["pending", "running"].includes(index.status)));
}

type LibraryProps = { orgId?: string; orgName?: string; writable: boolean; platform?: boolean };

export default function DocumentsLibrary({ orgId, orgName, writable, platform = false }: LibraryProps) {
  return <Suspense fallback={<p className="text-sm text-white/60">Loading documents…</p>}>
    <DocumentsList key={`${platform ? "platform" : orgId}:${writable}`} orgId={orgId} orgName={orgName} writable={writable} platform={platform} />
  </Suspense>;
}

function DocumentsList({ orgId, orgName, writable, platform = false }: LibraryProps) {
  const base = platform ? "/platform/documents" : `/orgs/${orgId}/documents`;
  const list = useListState(PAGE_SIZE, orgId ?? "platform");
  const { data, error, loading, reload } = useApi<{ items: Document[]; total: number }>(`${base}?${list.apiQuery}`);
  const facets = useApi<{ framework: string[] }>(`${base}/facets`);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{ documentId: string; versionId: string; scope: string } | null>(null);
  const previewScope = `${list.filterKey}:${list.offset}:${list.sort}:${list.order}`;
  useEffect(() => { setPreview(null); }, [previewScope]);
  const [confirm, setConfirm] = useState<{ version: Version; documentTitle: string } | null>(null);
  const [bulkAction, setBulkAction] = useState<"retire" | "remove" | null>(null);
  const [replacement, setReplacement] = useState<Document | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const uploadTitle = useRef<HTMLInputElement>(null);
  const canManage = (document: Document) => writable && (platform ? document.org_id === null : document.org_id === orgId);
  const columns = writable ? 6 : 5;
  useEffect(() => { if (uploadOpen) uploadTitle.current?.focus(); }, [uploadOpen, replacement]);
  const retireSelection = useSelection(list, orgId ?? "platform-retire");
  const removeSelection = useSelection(list, orgId ?? "platform-remove");
  const pageDocuments = (data?.items ?? []).filter(canManage);
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
    if (!writable || busy) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = (form.elements.namedItem("file") as HTMLInputElement).files?.[0];
    if (!file) { setFileError("Choose a UTF-8 text or Markdown file."); return; }
    const invalid = documentFileError(file);
    setFileError(invalid);
    if (invalid) return;
    const fields: Record<string, string> = {};
    for (const [key, value] of values) if (key !== "file") fields[key] = String(value);
    if (replacement) fields.document_id = replacement.id;
    await execute(async () => { await api.upload(base, file, fields); form.reset(); setReplacement(null); setUploadOpen(false); });
  }
  async function changeSelected(action: "retire" | "remove") {
    const selection = action === "retire" ? retireSelection : removeSelection;
    if (!writable || busy || selection.count === 0) return;
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
    <PageHeader title={platform ? "Shared standards" : "Documents"} total={data?.total} noun="documents" orgName={platform ? "the shared library" : (orgName ?? "this organization")} filtered={list.hasFilters} note="Only indexed, current sources are used for retrieval. Summaries are not official full standards."
      action={writable && <button type="button" className={PRIMARY} disabled={busy} onClick={() => { setFileError(null); setReplacement(null); setUploadOpen(true); }}>Upload document</button>} />
    {(message) && <p role="alert" className="text-red-300">{message}</p>}
    {!platform && orgId && <ConsentSettings key={orgId} orgId={orgId} writable={writable} />}
    {platform && writable && <><EmbeddingSettings /><button disabled={busy} className={SECONDARY} onClick={() => execute(() => api.post(`${base}/load-baseline`))}>Queue baseline: NIST catalog and CIS/ISO source references</button></>}
    {writable && uploadOpen && <section aria-labelledby="document-upload-heading" className="rounded-lg border border-white/10 p-4">
      <h2 id="document-upload-heading" className="text-lg font-medium">{replacement ? `New version of ${replacement.title}` : "Upload document"}</h2>
      <p className="mt-2 text-sm text-white/70">Upload authorized UTF-8 text or Markdown. Earlier versions are preserved; identical content and edition reuse the existing version.</p>
      <form onSubmit={upload} aria-label="Upload document" className="mt-3 grid gap-3 sm:grid-cols-2">
        <label>Title<input ref={uploadTitle} className={`${INPUT} block w-full`} name="title" required maxLength={255} defaultValue={replacement?.title} key={`${replacement?.id ?? "new"}-title`} /></label>
        <label>Framework<select className={`${INPUT} block w-full`} name="framework" defaultValue={replacement?.framework ?? ""} key={`${replacement?.id ?? "new"}-framework`}><option value="">Organization policy / general</option>{["CIS", "NIST", "ISO"].map(f => <option key={f}>{f}</option>)}</select></label>
        <label>Edition / version<input className={`${INPUT} block w-full`} name="edition" required maxLength={100} /></label>
        <label>Source reference<input className={`${INPUT} block w-full`} name="source" required maxLength={1000} /></label>
        <label>Content kind<select className={`${INPUT} block w-full`} name="content_kind"><option value="original_summary">Original summary</option>{!platform && <option value="organization_policy">Organization policy</option>}<option value="official">Authorized official text</option><option value="reference">Reference only (not retrieval evidence)</option></select></label>
        <label>Usage rights / authorization<input className={`${INPUT} block w-full`} name="rights" required maxLength={2000} /></label>
        <label>UTF-8 text or Markdown, up to 10 MiB<input key={replacement?.id ?? "new-document"} className="block" type="file" name="file" accept=".txt,.md,.markdown" required
          aria-invalid={fileError ? true : undefined} aria-describedby={fileError ? "document-file-error" : undefined}
          onChange={event => { const selected = event.target.files?.[0]; setFileError(selected ? documentFileError(selected) : null); }} /></label>
        {fileError && <p id="document-file-error" role="alert" className="text-sm text-red-300 [overflow-wrap:anywhere] sm:col-span-2">{fileError}</p>}
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2"><button className={PRIMARY} disabled={busy || !!fileError}>{busy ? "Queueing…" : "Queue processing"}</button><button type="button" className={SECONDARY} disabled={busy} onClick={() => { setFileError(null); setReplacement(null); setUploadOpen(false); }}>Cancel upload</button></div>
      </form>
    </section>}
    {writable && confirm && <ConfirmPanel
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
    {writable && <><SelectionBar selection={retireSelection}>
      <SelectionAction onClick={() => setBulkAction("retire")} disabled={busy}>Retire selected</SelectionAction>
    </SelectionBar>
    <SelectionBar selection={removeSelection}>
      <SelectionAction onClick={() => setBulkAction("remove")} disabled={busy} danger>Remove selected permanently</SelectionAction>
    </SelectionBar></>}
    {writable && bulkAction && (() => {
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
        {writable && <th className={SELECT_CELL}>
          <div className="space-y-2">
            <label className="flex items-center gap-1 text-[10px] normal-case tracking-normal"><SelectPageBox selection={retireSelection} rows={retireable} />Retire</label>
            <label className="flex items-center gap-1 text-[10px] normal-case tracking-normal"><SelectPageBox selection={removeSelection} rows={removable} />Remove</label>
          </div>
        </th>}
        <SortHeader label="Document" column="title" list={list} />
        <SortHeader label="Framework" column="framework" list={list} />
        <SortHeader label="Versions and processing" column="version" list={list} />
        <SortHeader label="Added" column="created" list={list} defaultSort="created" defaultOrder="desc" />
        <th className={`${TH} text-right`}>Actions</th>
      </tr>
      <tr>
        {writable && <th className={FILTER_CELL} />}
        <th className={FILTER_CELL}><TextFilter name="title" label="title" list={list} /></th>
        <th className={FILTER_CELL}><PickFilter name="framework" label="framework" list={list} options={facetOptions(facets.data?.framework, { "": "Policy" })} /></th>
        <th className={FILTER_CELL}><TextFilter name="version" label="versions and processing" list={list} /></th>
        <th className={FILTER_CELL} />
        <th className={FILTER_CELL} />
      </tr>
    </thead>
      <tbody>{loading && !data ? <tr><td colSpan={columns} className="px-4 py-8 text-center text-white/50">Loading documents…</td></tr> :
        error ? null : !data?.items.length ? <EmptyRow colSpan={columns} noun="documents" filtered={list.hasFilters} /> :
          data.items.map(d => <Fragment key={d.id}><tr className={ROW}>
            {writable && <td className={SELECT_CELL}><div className="space-y-3">{d.versions.map(v => <div key={v.id}>
              {!v.retired_at && !v.purged_at && canManage(d) && <SelectBox selection={retireSelection} id={v.id} name={`${d.title} · v${v.number} (retire)`} />}
              {v.retired_at && !v.current && !v.purged_at && !isReactivationPending(v) && canManage(d) && <SelectBox selection={removeSelection} id={v.id} name={`${d.title} · v${v.number} (remove)`} />}
            </div>)}</div></td>}
            <td className={TD}>{d.title}<p className="text-xs text-white/50">{d.org_id ? "Organization" : "Shared"}</p></td>
            <td className={TD}>{d.framework ?? "Policy"}</td>
            <td className={TD}>{d.versions.map(v => <div key={v.id} className="mb-3">
              <strong>v{v.number} · {v.edition}</strong>{" "}<StatusBadge status={!v.purged_at && !v.retired_at && v.current ? "completed" : "pending"} label={v.purged_at ? "Removed" : v.retired_at ? "Retired" : v.current ? "Current" : "Unpublished"} />
              <details className="mt-2 text-xs"><summary className="cursor-pointer text-white underline">Version details v{v.number}</summary>
                <p className="mt-2 break-words">{v.content_kind.replaceAll("_", " ")} · {v.source}</p><p className="break-words">Rights: {v.rights}</p>
                <p className="break-all text-white/70">SHA-256: {v.content_hash}</p>
              </details>
              {v.indexes.map(i => <div key={i.id} className="mt-2 space-y-1"><StatusBadge status={i.status === "ready" ? "completed" : i.status}
                label={isReactivationPending(v) && i.publish_version && ["pending", "running"].includes(i.status) ? "Reactivating…" : (PROCESSING_LABELS[i.status] ?? i.status)} />
                {i.error_message && <p className="break-words text-xs text-red-300">{i.error_message}</p>}</div>)}
            </div>)}</td>
            <td className={TD}>{formatDateTime(d.created_at)}</td>
            <td className={ACTIONS_CELL}>{d.versions.map(v => <div key={v.id} className="mb-3 flex flex-wrap justify-end gap-3">
              <button type="button" className={ROW_ACTION_VIEW} disabled={!!v.purged_at}
                id={`document-preview-toggle-${v.id}`}
                aria-expanded={preview?.scope === previewScope && preview.versionId === v.id}
                aria-controls={`document-preview-${v.id}`}
                onClick={() => setPreview(preview?.scope === previewScope && preview.versionId === v.id ? null : { documentId: d.id, versionId: v.id, scope: previewScope })}>
                {preview?.scope === previewScope && preview.versionId === v.id ? "Hide preview" : "Preview"} v{v.number}
              </button>
              {canManage(d) && !v.purged_at && <>{!v.retired_at && <><button disabled={busy} className={ROW_ACTION} onClick={() => execute(() => api.post(`${base}/versions/${v.id}/reindex`))}>Index / retry</button><button disabled={busy} className={ROW_ACTION} onClick={() => execute(() => api.post(`${base}/versions/${v.id}/retire`))}>Retire</button></>}{v.retired_at && !v.current && <><button disabled={busy || isReactivationPending(v)} className={ROW_ACTION} onClick={() => reactivate(v, d.title)}>{isReactivationPending(v) ? "Reactivating…" : `Reactivate v${v.number}`}</button>{!isReactivationPending(v) && <button disabled={busy} className={ROW_ACTION_DANGER} onClick={() => setConfirm({ version: v, documentTitle: d.title })}>Remove</button>}</>}</>}
            </div>)}{canManage(d) && <button disabled={busy} className={ROW_ACTION} onClick={() => { setFileError(null); setReplacement(d); setUploadOpen(true); }}>New version</button>}</td>
          </tr>{preview?.scope === previewScope && preview.documentId === d.id && d.versions.filter(v => v.id === preview.versionId && !v.purged_at).map(v => <tr key={v.id}>
            <td colSpan={columns} className="px-4 pb-3"><DocumentPreview key={`${base}:${v.id}`} base={base} version={v} title={d.title} onClose={() => { setPreview(null); document.getElementById(`document-preview-toggle-${v.id}`)?.focus(); }} /></td>
          </tr>)}</Fragment>)}
      </tbody></ListTable>
    <Pager offset={list.offset} limit={PAGE_SIZE} total={data?.total ?? 0} onChange={list.setOffset} />
    {!platform && <EvidenceSearch base={base} />}
  </div>;
}

function DocumentPreview({ base, version, title, onClose }: { base: string; version: Version; title: string; onClose(): void }) {
  const { data, loading, error, reload } = useApi<{ content: string | null }>(`${base}/versions/${version.id}`);
  return <section id={`document-preview-${version.id}`} aria-label={`Preview of ${title} · v${version.number}`} className="min-w-0 max-w-full overflow-hidden rounded-lg border border-white/10 bg-white/5 p-4">
    <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
      <h2 className="break-words text-sm font-medium text-white">{title} · v{version.number} · {version.edition}</h2>
      <button type="button" className={ROW_ACTION_VIEW} onClick={onClose}>Close preview</button>
    </div>
    {loading && <p role="status" className="text-sm text-white/60">Loading preview…</p>}
    {error && <div role="alert" className="text-sm text-red-300"><p>{error}</p><button type="button" className={ROW_ACTION_VIEW} onClick={reload}>Retry preview</button></div>}
    {!loading && !error && data && (data.content ? <pre role="region" aria-label={`Document text for ${title} · v${version.number}`} tabIndex={0} className="max-h-96 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words text-sm text-white/80 [overflow-wrap:anywhere]">{data.content}</pre> : <p className="text-sm text-white/60">No preview text is available for this version.</p>)}
  </section>;
}

function ConsentSettings({ orgId, writable }: { orgId: string; writable: boolean }) {
  const base = `/orgs/${orgId}/documents/settings`;
  const { data, error, loading, reload } = useApi<Settings>(base);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<{ purpose: "embedding" | "report"; granted: boolean; target: string } | null>(null);
  const inFlight = useRef(false);
  async function change(purpose: "embedding" | "report", granted: boolean, target: string) {
    if (!writable || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setMessage("");
    try { await api.put(`${base}/consent`, { purpose, granted, target }); setConfirmation(null); reload(); }
    catch (err) { setMessage(err instanceof Error ? err.message : "Consent update failed"); reload(); }
    finally { setBusy(false); inFlight.current = false; }
  }
  return <details className="rounded-lg border border-white/10 p-4">
    <summary className="cursor-pointer text-sm font-medium">Data processing consent</summary>
    <div className="mt-3 space-y-4 text-sm">
      {loading && <p role="status">Loading processing approvals…</p>}
      {(error || message) && <div role="alert" className="text-red-300"><p>{error || message}</p><button type="button" className={SECONDARY} onClick={reload}>Retry approval check</button></div>}
      {data && <>
        <p className="text-white/70">These approvals are separate. Revocation stops future calls, not data already sent. Approval does not configure credentials, indexes or a worker.</p>
        {(["report", "embedding"] as const).map(purpose => {
          const report = purpose === "report";
          const target = report ? data.report_target : data.embedding_target;
          const local = !report && (target === "local" || target.startsWith("local:"));
          const granted = report ? data.report_granted : data.embedding_granted;
          return <section key={purpose} aria-label={report ? "AI report processing" : "Embedding processing"} className="space-y-2 rounded-lg border border-white/10 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-medium">{report ? "AI report processing" : "Embedding processing"}</h2><StatusBadge status={granted && !local ? "completed" : "pending"} label={local ? "Local processing" : granted ? "Approved" : "Not approved"} /></div>
            <p className="text-white/70">{report ? "Sends sampled findings and permitted evidence excerpts to the AI provider." : local ? "Uses the local index; external embedding approval is not required for this target." : "Sends document text and search queries to the embedding provider. Without approval, this organization uses the local index."}</p>
            <details><summary className="cursor-pointer text-xs text-white underline">Processing target</summary><p className="mt-1 break-all text-xs text-white/70">{target}</p></details>
            {writable && !local && <button type="button" disabled={busy || loading || Boolean(error)} className={granted ? SECONDARY : PRIMARY} onClick={() => setConfirmation({ purpose, granted: !granted, target })}>{granted ? "Revoke" : "Approve"} {report ? "external AI reports" : "external embeddings"}</button>}
          </section>;
        })}
        <p className="break-words text-xs text-white/70">Current retrieval: {data.effective_embedding}</p>
        {!writable && <p className="text-xs text-white/70">Only an organization administrator can change processing approvals.</p>}
      </>}
      {writable && confirmation && <ConfirmPanel label="Confirm processing approval change"
        message={<>{confirmation.granted ? "Approve" : "Revoke"} external {confirmation.purpose === "report" ? "AI report" : "embedding"} processing for this organization?<span className="block break-all text-xs">Target: {confirmation.target}</span>{confirmation.granted ? "Confirm that you are authorized to send the described data to this target." : "This cannot recall data already sent."}</>}
        confirmLabel={busy ? "Saving…" : confirmation.granted ? "Approve processing" : "Revoke processing"}
        onConfirm={() => void change(confirmation.purpose, confirmation.granted, confirmation.target)} onCancel={() => { if (!busy) setConfirmation(null); }} busy={busy} />}
    </div>
  </details>;
}

type SearchResult = { citation_id: string; title: string; content: string; source: string; version: string };

function EvidenceSearch({ base }: { base: string }) {
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const query = String(new FormData(event.currentTarget).get("query") ?? "").trim();
    if (!query) return;
    inFlight.current = true;
    setBusy(true); setError(""); setResults(null);
    try { setResults((await api.post<{ items: SearchResult[] }>(`${base}/search`, { query })).items); }
    catch (err) { setError(err instanceof Error ? err.message : "Evidence search failed"); }
    finally { setBusy(false); inFlight.current = false; }
  }
  return <section aria-labelledby="evidence-search-heading" className="space-y-3 rounded-lg border border-white/10 p-4">
    <h2 id="evidence-search-heading" className="text-lg font-medium">Search permitted evidence</h2>
    <p className="text-sm text-white/70">Searches indexed, current evidence, not the document-list filters. No matches can mean that eligible sources have not been indexed.</p>
    <form onSubmit={search} aria-label="Search permitted evidence" className="flex flex-wrap items-end gap-3">
      <label className="min-w-0 flex-1 text-sm">Evidence query<input name="query" required maxLength={1200} disabled={busy} className={`${INPUT} mt-1 block w-full`} /></label>
      <button disabled={busy} className={PRIMARY}>{busy ? "Searching…" : "Search"}</button>
    </form>
    {busy && <p role="status">Searching permitted evidence…</p>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {results !== null && <p role="status" className="text-sm text-white/70">{results.length === 0 ? "No matching permitted evidence found." : `${results.length} evidence ${results.length === 1 ? "result" : "results"}`}</p>}
    {results?.map(result => <article key={result.citation_id} className="w-full min-w-0 max-w-full overflow-hidden rounded-lg border border-white/10 p-3"><h3 className="font-medium">{result.title} — {result.version}</h3><p className="break-words text-xs text-white/70 [overflow-wrap:anywhere]">{result.source} · {result.citation_id}</p><p className="whitespace-pre-wrap break-words text-sm [overflow-wrap:anywhere]">{result.content}</p></article>)}
  </section>;
}

function EmbeddingSettings() {
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  return <details className="rounded border border-white/10 p-4">
    <summary className="cursor-pointer text-sm font-medium">Platform embedding configuration</summary>
    <p className="mt-3 text-sm text-white/70">Local BGE-M3 is the default. Model setup is performed on the server, never downloaded by a page request. External credentials stay on the server. Reindex current sources after selecting a different model.</p>
    <form aria-label="Embedding configuration" className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={async e => {
      e.preventDefault();
      if (inFlight.current) return;
      const f = new FormData(e.currentTarget);
      inFlight.current = true; setBusy(true); setError(""); setMessage("");
      try {
        await api.put("/platform/documents/embedding-profile", {
          provider: f.get("provider"), model: f.get("model"), revision: f.get("revision"),
          dimensions: Number(f.get("dimensions")), approve_shared_external_processing: f.get("approve") === "on",
        });
        setMessage("Profile selected. Organization consent is still required for external processing.");
      } catch (err) { setError(err instanceof Error ? err.message : "Configuration failed"); }
      finally { inFlight.current = false; setBusy(false); }
    }}>
      <label className="text-sm">Provider<select name="provider" disabled={busy} className={`${INPUT} mt-1 block w-full`}>
        <option value="local">Local BGE-M3</option><option value="openai">OpenAI</option><option value="voyage">Voyage</option>
      </select></label>
      <label className="text-sm">Model<input name="model" required disabled={busy} defaultValue="BAAI/bge-m3" className={`${INPUT} mt-1 block w-full`} /></label>
      <label className="text-sm">Model revision<input name="revision" required disabled={busy} defaultValue="5617a9f61b028005a4858fdac845db406aefb181" className={`${INPUT} mt-1 block w-full`} /></label>
      <label className="text-sm">Vector dimensions<input name="dimensions" type="number" min={1} max={4096} required disabled={busy} defaultValue={1024} className={`${INPUT} mt-1 block w-full`} /></label>
      <label className="text-sm sm:col-span-2"><input type="checkbox" disabled={busy} name="approve" /> Approve external processing of shared standards and queries</label>
      <div><button disabled={busy} className={PRIMARY}>{busy ? "Saving…" : "Select profile"}</button></div>
    </form>
    {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}
