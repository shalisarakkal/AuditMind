"use client";

import { useEffect, useRef, useState } from "react";
import { evidenceOperation, type EvidenceProgress } from "@/lib/evidenceProgress";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { DOMAIN_LABELS, DOMAIN_ORDER } from "@/lib/domain";
import type { Domain } from "@/lib/types";
import FindingActionDialog from "./FindingActionDialog";

type Observation = { objective: string; source_type: "finding" | "document_version"; source_id: string; source_sha256: string; observed_at: string };
type Qualification = { domain: Domain; version: number; status: string; scope: string; rationale: string; inventory_sha256: string | null; observations: Observation[]; review_note: string | null; expires_at: string | null };
type Inventory = { inventory_sha256: string; asset_count: number; finding_count: number };
type Evaluation = { evaluated_at?: string; assessment_status: string; qualified_domain_count: number; domains: { domain: Domain; eligible: boolean; reason_code: string; version: number | null }[] };
type Confirmation = { title: string; description: string; label: string; domain: Domain; perform(): Promise<void> };
const field = "w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-white";
const button = "rounded-md border border-cyan px-3 py-2 text-sm text-cyan disabled:opacity-40";
const words = (value: string) => value.replaceAll("_", " ");

export default function EvidenceScoringSettings({ orgId, editable }: { orgId: string; editable: boolean }) {
  const base = `/orgs/${orgId}/scoring`;
  const profiles = useApi<{ profiles: Record<Domain, string[]> }>(`${base}/profiles`);
  const records = useApi<Qualification[]>(`${base}/qualifications`);
  const [domain, setDomain] = useState<Domain>("identity_access");
  const [draft, setDraft] = useState<Qualification | null>(null);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [scope, setScope] = useState("");
  const [rationale, setRationale] = useState("");
  const [observations, setObservations] = useState<Observation[]>([]);
  const [sourceType, setSourceType] = useState<Observation["source_type"]>("finding");
  const [sourceId, setSourceId] = useState("");
  const [objective, setObjective] = useState("");
  const [observed, setObserved] = useState("");
  const [note, setNote] = useState("");
  const [expires, setExpires] = useState("");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [opened, setOpened] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const confirmationTrigger = useRef<HTMLElement | null>(null);
  function ask(action: Confirmation) {
    confirmationTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setConfirmation(action);
  }
  function cancelConfirmation() {
    const trigger = confirmationTrigger.current;
    setConfirmation(null);
    // The background fieldset must be enabled again before restoring focus.
    window.requestAnimationFrame(() => { if (trigger?.isConnected) trigger.focus(); });
  }
  const [progress, setProgress] = useState<EvidenceProgress | null>(null);
  const [scanKind, setScanKind] = useState<"inventory" | "evaluation" | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(0);
  const operation = useRef<AbortController | null>(null);
  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setElapsed(Math.floor((performance.now() - started.current) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);
  async function scan<T>(kind: "inventory" | "evaluation") {
    const controller = new AbortController();
    operation.current = controller;
    setScanKind(kind);
    setProgress({ phase: "connecting", processed: 0, total: null });
    try {
      return await evidenceOperation<T>(`${base}/progress/${kind}`, controller.signal,
        value => setProgress(current => ({ ...current, ...value })));
    } catch (cause) {
      if (controller.signal.aborted) throw new Error("Operation cancelled. No scoring changes were made.");
      throw cause;
    } finally { operation.current = null; }
  }
  const run = async (action: () => Promise<void>) => {
    started.current = performance.now(); setElapsed(0);
    setBusy(true); setError(""); setMessage(""); setProgress(null); setScanKind(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setElapsed(Math.floor((performance.now() - started.current) / 1000)); setBusy(false); }
  };
  async function load() {
    const latest = await api.get<Qualification[]>(`${base}/qualifications`);
    const row = latest.find(r => r.domain === domain) ?? null;
    setDraft(row); setScope(row?.scope ?? ""); setRationale(row?.rationale ?? "");
    setObservations(row?.observations ?? []); setInventory(null);
    setObjective(""); setSourceId(""); setObserved(""); setSourceType("finding");
    setOpened(true); setNote(""); setExpires(""); setAttested(false); setMessage(""); setError("");
  }
  const dirty = editable && opened && (
    scope !== (draft?.scope ?? "") || rationale !== (draft?.rationale ?? "") ||
    JSON.stringify(observations) !== JSON.stringify(draft?.observations ?? []) ||
    (inventory != null && inventory.inventory_sha256 !== draft?.inventory_sha256) ||
    !!(note || expires || attested || objective || sourceId || observed || sourceType !== "finding")
  );
  function requestDomain(next?: Domain) {
    const perform = async () => {
      if (next) { setDomain(next); setOpened(false); }
      else await load();
    };
    if (!dirty) { void run(perform); return; }
    ask({ title: "Discard unsaved edits?", domain,
      description: next ? `Discard edits to ${DOMAIN_LABELS[domain]} and switch to ${DOMAIN_LABELS[next]}? No changes will be saved.`
        : "Discard unsaved edits and load the latest saved domain qualification? No changes will be saved.",
      label: next ? "Discard and switch" : "Discard and reload", perform });
  }
  const blocked = busy || confirmation !== null;
  const locked = !editable || draft?.status === "approved";
  const scanFeedback = progress && <div className="space-y-2 text-sm" role="status" aria-label={scanKind === "evaluation" ? "Organization evaluation progress" : "Inventory loading progress"}>
    <p>{busy ? "Processing" : error ? "Stopped" : "Finished"}: {words(progress.phase)} · {(progress.processed ?? 0).toLocaleString()} / {progress.total == null ? "counting records" : progress.total.toLocaleString()} records · {elapsed}s elapsed</p>
    {busy && <p className="text-white/60">Counts update after each completed batch. Counting, preparing the scan and checking qualifications may take time between updates.</p>}
    {progress.total != null && progress.total > 0 && <progress aria-label="Inventory records processed" className="w-full accent-cyan" max={progress.total} value={progress.processed ?? 0} />}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {message && <p className="text-cyan">{message}</p>}
    {busy && <button type="button" className={button} onClick={() => { operation.current?.abort(); }}>Cancel operation</button>}
  </div>;
  return <section className="min-w-0 space-y-4 rounded-xl border border-white/15 p-5">
    <h2 className="text-lg font-medium">Scoring and evidence review</h2>
    <label className="flex items-center gap-2"><input type="checkbox" disabled checked={false} readOnly /> Evidence-qualified scoring (not yet available)</label>
    <p className="text-sm text-white/60">Review evidence coverage here without changing Dashboard scores or saved reports. Approval is not a statement that controls pass. No AI calls are made.</p>
    {!editable && <p className="text-sm text-white/60">Read-only: an organization administrator manages qualifications.</p>}
    {(profiles.error || records.error || (!scanKind && error)) && <p role="alert" className="text-red-300">{(!scanKind && error) || profiles.error || records.error}</p>}
    {message && !scanKind && <p role="status" className="text-cyan">{message}</p>}
    <section aria-label="Organization-wide evidence evaluation" className="space-y-3 rounded-lg border border-white/15 p-4">
      <h3 className="font-medium">Organization-wide evaluation</h3>
      <p className="text-sm text-white/60">Checks all seven domains across this organization. The domain selected below does not limit this evaluation. Unsaved edits are not included; Dashboard scores are unchanged.</p>
      <button className={button} type="button" disabled={blocked} onClick={() => run(async () => { setEvaluation(null); setEvaluation(await scan<Evaluation>("evaluation")); })}>Evaluate evidence across all domains</button>
      {scanKind === "evaluation" && scanFeedback}
      {evaluation ? <div className="space-y-2"><p>Coverage assessment: {words(evaluation.assessment_status)} · {evaluation.qualified_domain_count} of 7 domains qualified. Dashboard scores are unchanged.</p>
        {evaluation.evaluated_at && <p className="text-sm text-white/60">Last evaluated: {new Date(evaluation.evaluated_at).toLocaleString()}. Results reflect that completed evaluation.</p>}
        <ul>{evaluation.domains.map(d => <li key={d.domain}>{DOMAIN_LABELS[d.domain]}: {words(d.reason_code)}{d.eligible ? " (eligible)" : " (not eligible)"}</li>)}</ul>
      </div> : <p className="text-sm text-white/60">Current eligibility has not been evaluated. A saved approval alone does not establish current coverage.</p>}
    </section>
    <section aria-label="Domain qualification" className="min-w-0 space-y-4">
      {busy && !progress && <p role="status">Working…</p>}
      <fieldset disabled={blocked} className="min-w-0 space-y-4 disabled:opacity-60">
      <legend className="font-medium">Domain qualification</legend>
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-0 flex-1">Domain<select className={field} value={domain} onChange={e => requestDomain(e.target.value as Domain)}>
          {DOMAIN_ORDER.map(d => <option key={d} value={d}>{DOMAIN_LABELS[d]}</option>)}
        </select></label>
        <button type="button" className={button} disabled={!records.data || !profiles.data} onClick={() => requestDomain()}>Open / reload domain</button>
      </div>
      <p className="text-sm text-white/60">Opens the latest saved qualification for the selected domain, or an empty draft if none exists. Reload does not save, approve, evaluate or change scores. A discard warning appears only for unsaved edits.</p>
      {opened && <>
        <p>Saved status: {draft?.status ?? "No draft"} · Version {draft?.version ?? 0}</p>
        {draft?.review_note && <p className="whitespace-pre-wrap break-words">Review note: {draft.review_note}</p>}
        {draft?.expires_at && <p>Review expires: {new Date(draft.expires_at).toLocaleString()}</p>}
        <p className="text-sm text-white/60">Required objectives: {profiles.data?.profiles[domain].map(words).join(", ")}. Only current organization-policy document versions or findings in this domain can be bound.</p>
        <label className="block">Scope description<input className={field} value={scope} maxLength={2000} disabled={locked} onChange={e => setScope(e.target.value)} /></label>
        <label className="block">Evidence rationale<textarea className={field} value={rationale} maxLength={4000} disabled={locked} onChange={e => setRationale(e.target.value)} /></label>
        <p className="text-sm text-white/60">Inventory binding covers the entire organization. Loading or evaluating scans the inventory and may take time for large organizations; these actions do not run automatically.</p>
        <button className={button} type="button" disabled={locked} onClick={() => run(async () => { setInventory(await scan<Inventory>("inventory")); setMessage("Current inventory loaded. Save the draft to bind it."); })}>Load current inventory</button>
      </>}
      </fieldset>
      {opened && scanKind === "inventory" && scanFeedback}
      {opened && <fieldset disabled={blocked} className="min-w-0 space-y-4 disabled:opacity-60">
        <legend className="sr-only">Domain evidence and review actions</legend>
        {inventory && <p>{inventory.asset_count.toLocaleString()} assets · {inventory.finding_count.toLocaleString()} findings</p>}
        <p className="text-sm text-white/60">Saved inventory binding: {draft?.inventory_sha256 ? "Present" : "Not bound"}</p>
        <fieldset disabled={locked} className="min-w-0 space-y-3 rounded-md border border-white/15 p-3">
          <legend>Add an evidence observation</legend>
          <label className="block">Objective<select className={field} value={objective} onChange={e => setObjective(e.target.value)}><option value="">Choose an objective</option>{profiles.data?.profiles[domain].map(o => <option key={o} value={o}>{words(o)}</option>)}</select></label>
          <label className="block">Source type<select className={field} value={sourceType} onChange={e => setSourceType(e.target.value as Observation["source_type"])}><option value="finding">Finding ID</option><option value="document_version">Document version ID</option></select></label>
          <label className="block">Source UUID<input className={field} value={sourceId} onChange={e => setSourceId(e.target.value)} /></label>
          <label className="block">Observed at<input className={field} type="datetime-local" value={observed} onChange={e => setObserved(e.target.value)} /></label>
          <button className={button} type="button" disabled={!objective || !sourceId.trim() || !observed} onClick={() => run(async () => {
            const source = await api.get<{ source_sha256: string; domain?: Domain }>(`${base}/${sourceType === "finding" ? "source-findings" : "source-documents"}/${encodeURIComponent(sourceId.trim())}`);
            if (source.domain && source.domain !== domain) throw new Error("Choose a finding in this domain.");
            const item = { objective, source_type: sourceType, source_id: sourceId.trim(), source_sha256: source.source_sha256, observed_at: new Date(observed).toISOString() };
            if (observations.some(o => o.objective === item.objective && o.source_type === item.source_type && o.source_id === item.source_id)) throw new Error("That observation is already added.");
            setObservations([...observations, item]); setObjective(""); setSourceId(""); setObserved(""); setSourceType("finding"); setMessage("Source validated and added to the unsaved draft.");
          })}>Validate source and add</button>
        </fieldset>
        <ul className="space-y-2">{observations.map((o, i) => <li key={`${o.objective}-${o.source_id}-${i}`} className="break-words rounded border border-white/10 p-3 text-sm">
          {words(o.objective)} · {words(o.source_type)} · {new Date(o.observed_at).toLocaleString()}
          <details><summary>Source details</summary><p className="break-all">{o.source_id}</p><p className="break-all">SHA-256: {o.source_sha256}</p></details>
          {!locked && <button type="button" className="text-cyan" onClick={() => setObservations(observations.filter((_, n) => n !== i))}>Remove observation</button>}
        </li>)}</ul>
        <button className={button} type="button" disabled={locked || !scope.trim() || !rationale.trim()} onClick={() => run(async () => {
          const saved = await api.put<Qualification>(`${base}/qualifications/${domain}`, { expected_version: draft?.version ?? 0, scope, rationale, observations, inventory_sha256: inventory?.inventory_sha256 ?? draft?.inventory_sha256 ?? null });
          setDraft(saved); setScope(saved.scope); setRationale(saved.rationale); setObservations(saved.observations); setInventory(null); setEvaluation(null); records.reload(); setMessage("Draft saved. Review the saved version before approving.");
        })}>Save draft</button>
        {editable && draft && <div className="space-y-3 border-t border-white/15 pt-4">
          <p className="text-sm text-white/60">Review actions apply to saved version {draft.version} only, not unsaved edits. All three objectives need fresh evidence; expiry must be within 90 days of every observation.</p>
          <label className="block">Review / revocation note<textarea className={field} value={note} maxLength={4000} onChange={e => setNote(e.target.value)} /></label>
          {draft.status === "draft" && <>
            <label className="block">Review expiry<input className={field} type="datetime-local" value={expires} onChange={e => setExpires(e.target.value)} /></label>
            <label className="flex items-start gap-2"><input type="checkbox" checked={attested} onChange={e => setAttested(e.target.checked)} /> I reviewed operational evidence, confirmed coverage of the entire bound inventory, and reviewed conflicts.</label>
            {(["approve", "conflicting"] as const).map(decision => <button key={decision} className={button} type="button" disabled={!attested || !expires || !note.trim() || !draft.inventory_sha256} onClick={() => ask({
              title: decision === "approve" ? "Approve saved evidence?" : "Record material conflict?", domain,
              description: `Confirm ${DOMAIN_LABELS[domain]} evidence, saved version ${draft.version}. This does not change scores. Unsaved edits are not included.`,
              label: decision === "approve" ? "Approve saved evidence" : "Record material conflict", perform: async () => {
              const saved = await api.post<Qualification>(`${base}/qualifications/${domain}/review`, { expected_version: draft.version, inventory_sha256: draft.inventory_sha256, decision, expires_at: new Date(expires).toISOString(), note, operational_review: true, covers_entire_inventory: true, conflicts_reviewed: true });
              setDraft(saved); setNote(""); setExpires(""); setAttested(false); records.reload(); setEvaluation(null); setMessage("Review recorded. Evaluate evidence across all domains to check eligibility.");
            } })}>{decision === "approve" ? "Approve saved evidence" : "Record material conflict"}</button>)}
          </>}
          {["approved", "conflicting"].includes(draft.status) && <button className={button} type="button" disabled={!note.trim()} onClick={() => ask({
            title: "Revoke qualification?", domain, description: `Revoke ${DOMAIN_LABELS[domain]} evidence, saved version ${draft.version}? This does not change scores.`,
            label: "Revoke qualification", perform: async () => {
            setDraft(await api.post<Qualification>(`${base}/qualifications/${domain}/revoke`, { expected_version: draft.version, note })); setNote(""); setExpires(""); setAttested(false); records.reload(); setEvaluation(null); setMessage("Qualification revoked.");
          } })}>Revoke qualification</button>}
        </div>}
      </fieldset>}
    </section>
    {confirmation && <FindingActionDialog title={confirmation.title} orgName={DOMAIN_LABELS[confirmation.domain]} onClose={cancelConfirmation}>
      <p className="mb-4 text-sm text-white/80">{confirmation.description}</p>
      <div className="flex flex-wrap gap-3">
        <button type="button" data-confirm-cancel className={button} onClick={cancelConfirmation}>Cancel</button>
        <button type="button" className="rounded-md bg-cyan px-3 py-2 text-sm text-navy" onClick={() => {
          const action = confirmation; setConfirmation(null); void run(action.perform);
        }}>{confirmation.label}</button>
      </div>
    </FindingActionDialog>}
  </section>;
}
