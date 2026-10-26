"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { browserTimezone, formatDeadline, changedWorkflowFields, historyValue, WORKFLOW_LABELS, WORKFLOW_OPTIONS, type Workflow, type WorkflowHistory } from "@/lib/findingWorkflow";
import { formatDateTime } from "@/lib/domain";
import { useDebounced } from "@/lib/useDebounced";
import FindingReference from "./FindingReference";

type Props = { orgId: string; orgName: string; role: string; ids: string[]; names?: string[]; onClose(): void; onSaved(): void };
type Member = { id: string; name: string | null; email: string; status: string };
const control = "mt-1 w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none focus:ring-1 focus:ring-cyan disabled:opacity-50";

export default function FindingWorkflowDialog({ orgId, orgName, role, ids, names, onClose, onSaved }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const heading = useId();
  const writer = role === "admin" || role === "auditor";
  const [snapshots, setSnapshots] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [needsReload, setNeedsReload] = useState(false);
  const [status, setStatus] = useState("");
  const [assignee, setAssignee] = useState("keep");
  const [selectedAssigneeLabel, setSelectedAssigneeLabel] = useState("");
  const [dueMode, setDueMode] = useState("keep");
  const [dueDate, setDueDate] = useState("");
  const [reviewMode, setReviewMode] = useState("keep");
  const [reviewDate, setReviewDate] = useState("");
  const [entryTimezone] = useState(browserTimezone);
  const [rationale, setRationale] = useState("");
  const [verification, setVerification] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const settledMemberSearch = useDebounced(memberSearch);
  const [memberOffset, setMemberOffset] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);
  const notesOnly = role !== "admin" && snapshots.some(row => row.status === "accepted_risk");
  const allAccepted = snapshots.length > 0 && snapshots.every(row => (status || row.status) === "accepted_risk");
  const anyAccepted = snapshots.some(row => (status || row.status) === "accepted_risk");
  const reviewError = !notesOnly && ((reviewMode === "set" && !allAccepted)
    ? "To set a risk review date, every selected finding must remain or become Accepted risk. Narrow your selection or explicitly change their status."
    : reviewMode === "clear" && anyAccepted ? "Accepted-risk findings must retain an unexpired review deadline. Keep or set that date, or change their status." : null);
  const members = useApi<{ items: Member[]; total: number }>(writer && !notesOnly
    ? `/orgs/${orgId}/members?limit=50&offset=${memberOffset}&q=${encodeURIComponent(settledMemberSearch)}&search_scope=identity&status=active&status=locked&status=must_change_password` : null);
  const history = useApi<WorkflowHistory[]>(ids.length === 1
    ? `/orgs/${orgId}/findings/${ids[0]}/workflow/history?limit=20&offset=${historyOffset}` : null);

  useEffect(() => {
    const element = dialog.current!;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal(); close.current?.focus();
    return () => { element.close(); if (previous?.isConnected) previous.focus(); };
  }, []);

  useEffect(() => {
    let current = true;
    setLoading(true); setLoadError(null);
    async function load() {
      const rows: Workflow[] = [];
      // Bound both target count and request concurrency, including cross-page selections.
      if (ids.length === 0 || ids.length > 100) throw new Error("Select between 1 and 100 findings.");
      for (let start = 0; start < ids.length; start += 5) {
        rows.push(...await Promise.all(ids.slice(start, start + 5).map(id => api.get<Workflow>(`/orgs/${orgId}/findings/${id}/workflow`))));
      }
      if (current) { setSnapshots(rows); setNeedsReload(false); if (refresh > 0) setError(null); }
    }
    load().catch(err => current && setLoadError(err instanceof Error ? err.message : "Could not load workflow"))
      .finally(() => current && setLoading(false));
    return () => { current = false; };
  }, [orgId, ids, refresh]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!writer || inFlight.current || loading || loadError || needsReload || reviewError) return;
    if (!rationale.trim()) { setError("Provide a rationale or note."); return; }
    if (!notesOnly && (dueMode === "set" || reviewMode === "set") && !entryTimezone) { setError("Could not detect your browser timezone. Check browser settings before setting a deadline."); return; }
    const patch: Record<string, unknown> = { rationale: rationale.trim() };
    if (verification.trim()) patch.verification = verification.trim();
    if (!notesOnly) {
      if (status) patch.status = status;
      if (assignee !== "keep") patch.assignee_id = assignee === "clear" ? null : assignee;
      if (dueMode !== "keep") patch.due_date = dueMode === "clear" ? null : dueDate;
      if (reviewMode !== "keep") patch.risk_review_date = reviewMode === "clear" ? null : reviewDate;
      if (dueMode === "set" || reviewMode === "set") patch.deadline_timezone = entryTimezone;
    }
    inFlight.current = true; setBusy(true); setError(null); dialog.current?.focus();
    try {
      if (snapshots.length === 1) await api.patch(`/orgs/${orgId}/findings/${snapshots[0].finding_id}/workflow`, { ...patch, expected_version: snapshots[0].version });
      else await api.post(`/orgs/${orgId}/findings/workflow/bulk`, { patch, targets: snapshots.map(row => ({ finding_id: row.finding_id, expected_version: row.version })) });
      onSaved(); onClose();
    } catch (err) {
      const uncertain = !(err instanceof ApiError) || err.status === 409 || err.status >= 500;
      setNeedsReload(uncertain);
      setError((err instanceof Error ? err.message : "Update failed") + (uncertain ? ". Reload latest state and history, review your retained draft, then submit again. No automatic retry was made." : ""));
    } finally { inFlight.current = false; setBusy(false); }
  }

  return <dialog ref={dialog} tabIndex={-1} aria-labelledby={heading} aria-modal="true"
    onCancel={event => { event.preventDefault(); if (!inFlight.current) onClose(); }}
    onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)"));
      const first = controls[0], last = controls.at(-1);
      if (!first || !last) { event.preventDefault(); event.currentTarget.focus(); }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === event.currentTarget)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === event.currentTarget)) { event.preventDefault(); first.focus(); }
    }}
    className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto rounded-xl border border-white/20 bg-navy p-5 text-white shadow-xl backdrop:bg-black/75">
    <header className="flex items-start justify-between gap-4">
      <div><h2 id={heading} className="text-lg font-semibold">Finding workflow</h2><p className="text-sm text-white/70">{orgName} · {ids.length} {ids.length === 1 ? "finding" : "findings"}</p></div>
      <button ref={close} type="button" aria-label="Close finding workflow" disabled={busy} onClick={onClose} className="rounded p-1 text-white underline">Close</button>
    </header>
    <p className="my-3 text-sm text-amber-200">Workflow status does not change scores or saved reports. Verification notes are user assertions, not automatic evidence qualification.</p>
    {names && <details className="mb-3 text-sm" open={ids.length === 1}><summary>Selected findings</summary><ul className="break-words">{names.map((name, index) => <li key={ids[index]}>{name}</li>)}</ul></details>}
    <details className="mb-3 text-xs"><summary>Technical finding IDs</summary><p>Unique internal identifiers of the findings being edited, not CVE or scanner IDs. Follow a link to locate a finding; save or discard your draft first.</p><ul className="break-all">{ids.map(id => <li key={id}><FindingReference orgId={orgId} id={id} copy /></li>)}</ul></details>
    {loading && <p role="status">Loading workflow…</p>}
    {loadError && <p role="alert">{loadError}</p>}
    {(loadError || needsReload) && <button type="button" disabled={busy || loading} className="text-cyan underline" onClick={() => { setRefresh(v => v + 1); history.reload(); }}>Reload latest state</button>}
    {error && <p role="alert" className="my-3 text-red-300">{error}</p>}
    {!loading && !loadError && snapshots.length > 1 && <section aria-label="Selection summary" className="my-3 rounded border border-white/20 p-3 text-sm">
      <h3 className="font-semibold">Current selection</h3>
      <p>{WORKFLOW_OPTIONS.map(option => ({ label: option.label, count: snapshots.filter(row => row.status === option.value).length })).filter(item => item.count).map(item => `${item.count} ${item.label}`).join(" · ")}</p>
      <p className="mt-2 text-white/70">Keep preserves each finding’s own value. Explicit changes apply to every selected finding. If any finding is incompatible, nothing is saved; no findings are silently skipped. Open an individual finding to read its saved notes and history.</p>
    </section>}
    {ids.length === 1 && <a href={`#${heading}-history`} className="my-3 block text-sm text-cyan underline" onClick={event => { event.preventDefault(); const section = document.getElementById(`${heading}-history`); section?.scrollIntoView({ block: "start" }); section?.focus(); }}>Saved notes and history{history.data ? ` (${history.data.length} on this page)` : ""}</a>}
    {!loading && !loadError && snapshots.length === 1 && <dl className="my-3 grid grid-cols-2 gap-2 break-words text-sm">
      <dt>Current status</dt><dd>{WORKFLOW_LABELS[snapshots[0].status]}</dd>
      <dt>Current assignee</dt><dd>{snapshots[0].assignee_id ? (snapshots[0].assignee_available && snapshots[0].assignee_label?.trim() ? snapshots[0].assignee_label : "Assignee unavailable") : "Unassigned"}</dd>
      <dt>Current due date</dt><dd>{formatDeadline(snapshots[0].due_date, snapshots[0].due_expires_at)}</dd>
      <dt>Current risk review date</dt><dd>{formatDeadline(snapshots[0].risk_review_date, snapshots[0].risk_review_expires_at)}</dd>
      {([['latest_rationale', 'Latest rationale or note'], ['latest_verification', 'Latest verification note']] as const).map(([key, label]) => <div key={key} className="col-span-2">
        <dt className="font-semibold">{label}</dt><dd className="whitespace-pre-wrap">{snapshots[0][key]?.text || "None recorded"}</dd>
        {snapshots[0][key] && <dd className="text-xs text-white/70">{snapshots[0][key].actor_label} · {formatDateTime(snapshots[0][key].created_at)}</dd>}
      </div>)}
    </dl>}
    {!writer && <p role="note" className="my-3">Read-only access: an organization admin or auditor manages remediation.</p>}
    {writer && <form onSubmit={save} aria-label="Update finding workflow" aria-busy={busy} className="space-y-3">
      <fieldset disabled={busy || loading || !!loadError || needsReload} className="space-y-3">
        <legend className="sr-only">Workflow changes</legend>
        {notesOnly ? <p>Accepted-risk findings: auditors may add notes only. Ask an organization admin to change workflow fields.</p> : <>
          <label className="block text-sm">New status<select aria-label="New status" className={control} value={status} onChange={e => setStatus(e.target.value)}><option value="">Keep current status</option>{WORKFLOW_OPTIONS.filter(option => role === "admin" || option.value !== "accepted_risk").map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label className="block text-sm">Find assignee<input aria-describedby={`${heading}-assignee-help`} className={control} value={memberSearch} onChange={e => { setMemberSearch(e.target.value); setMemberOffset(0); }} /></label>
          <p id={`${heading}-assignee-help`} className="text-xs text-white/70">Search organization members by name or email, then choose an Assignee below. Searching alone does not change the assignment.</p>
          {members.error && <p role="alert">Could not load assignees: {members.error} <button type="button" className="text-cyan underline" onClick={members.reload}>Retry assignees</button></p>}
          {members.loading && <p role="status">Loading assignees…</p>}
          {!members.loading && !members.error && members.data?.total === 0 && <p role="status" className="text-sm text-white/70">No matching organization members.</p>}
          <label className="block text-sm">Assignee<select aria-label="Assignee" className={control} value={assignee} onChange={e => { setAssignee(e.target.value); setSelectedAssigneeLabel(e.target.selectedOptions[0]?.textContent || ""); }}>
            <option value="keep">Keep current assignee</option><option value="clear">Unassigned</option>
            {assignee !== "keep" && assignee !== "clear" && (members.loading || !members.data?.items.some(m => m.id === assignee)) && <option value={assignee}>{selectedAssigneeLabel || "Selected assignee"}</option>}
            {!members.loading && members.data?.items.filter(member => member.status !== "deactivated").map(member => <option key={member.id} value={member.id}>{member.name?.trim() || member.email}</option>)}
          </select></label>
          <div className="flex gap-3 text-xs"><button type="button" disabled={memberOffset === 0 || members.loading} onClick={() => setMemberOffset(v => v - 50)}>Previous assignees</button><button type="button" disabled={members.loading || !members.data || memberOffset + 50 >= members.data.total} onClick={() => setMemberOffset(v => v + 50)}>More assignees</button></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">Due date action<select aria-label="Due date action" className={control} value={dueMode} onChange={e => setDueMode(e.target.value)}><option value="keep">Keep due date</option><option value="set">Set due date</option><option value="clear">Clear due date</option></select></label>
            {dueMode === "set" && <label className="text-sm">Due date<input type="date" className={control} required value={dueDate} onChange={e => setDueDate(e.target.value)} /></label>}
            {role === "admin" && <label className="text-sm">Risk review action<select aria-label="Risk review action" className={control} value={reviewMode} onChange={e => setReviewMode(e.target.value)}><option value="keep">Keep risk review date</option><option value="set" disabled={!allAccepted}>Set risk review date</option><option value="clear" disabled={anyAccepted}>Clear risk review date</option></select></label>}
            {role === "admin" && reviewMode === "set" && <label className="text-sm">Risk review date<input type="date" className={control} required value={reviewDate} onChange={e => setReviewDate(e.target.value)} /></label>}
          </div>
        </>}
        {role === "admin" && !notesOnly && !allAccepted && <p className="text-xs text-white/70">Set risk review date is available only when every selected finding remains or becomes Accepted risk.</p>}
        {reviewError && <p role="alert" className="text-sm text-red-300">{reviewError}</p>}
        <label className="block text-sm">Add rationale or note<textarea aria-label="Rationale or note" className={control} required maxLength={2000} value={rationale} onChange={e => setRationale(e.target.value)} /></label>
        <p className="text-xs text-white/70">Required for audit traceability. These empty fields add a new entry; saved notes are in Workflow history.</p>
        <label className="block text-sm">Add verification note<textarea aria-label="Verification note" className={control} maxLength={2000} value={verification} onChange={e => setVerification(e.target.value)} /></label>
        <p className="text-xs text-white/70">Deadline dates include the entire selected day and cannot precede the finding's creation date. Keep preserves saved deadlines. Accepted risk requires an admin and an unexpired review deadline; today is allowed. Mitigated, Resolved and False positive transitions require verification.</p>
        <button type="submit" disabled={!!reviewError} className="rounded-md bg-cyan px-4 py-2 text-sm font-semibold text-navy disabled:opacity-50">{busy ? "Saving…" : ids.length === 1 ? "Save workflow" : `Apply to ${ids.length} findings`}</button>
      </fieldset>
    </form>}
    {ids.length === 1 && <section id={`${heading}-history`} tabIndex={-1} aria-label="Workflow history" className="mt-5 border-t border-white/15 pt-3">
      <h3 className="font-semibold">Workflow history</h3>
      {history.loading ? <p role="status">Loading history…</p> : history.error ? <p role="alert">{history.error} <button className="text-cyan underline" type="button" onClick={history.reload}>Retry history</button></p> : history.data?.length ? <ol className="space-y-3">{history.data.map(entry => <li key={entry.id} className="rounded border border-white/15 p-3 text-sm">
        <p>{entry.actor_label} · {formatDateTime(entry.created_at)} · Version {entry.version}</p>
        <p className="whitespace-pre-wrap break-words"><span className="font-semibold">Rationale or note: </span>{entry.rationale}</p>{entry.verification && <p className="whitespace-pre-wrap break-words"><span className="font-semibold">Verification note: </span>{entry.verification}</p>}
        {changedWorkflowFields(entry).length ? <details><summary>Recorded changes</summary><dl>{changedWorkflowFields(entry).map(key => <div key={key} className="break-words"><dt className="inline">{key === "assignee_id" ? "Assignee" : key.replaceAll("_", " ")}: </dt><dd className="inline">{historyValue(entry, "before", key)} → {historyValue(entry, "after", key)}</dd></div>)}</dl></details> : <p className="text-xs text-white/70">Note added — no workflow fields changed.</p>}
      </li>)}</ol> : <p className="text-sm text-white/70">No workflow history yet.</p>}
      <div className="mt-3 flex gap-4 text-sm"><button type="button" disabled={busy || history.loading || historyOffset === 0} onClick={() => setHistoryOffset(v => v - 20)}>Newer history</button><button type="button" disabled={busy || history.loading || (history.data?.length ?? 0) < 20} onClick={() => setHistoryOffset(v => v + 20)}>Older history</button></div>
    </section>}
  </dialog>;
}
