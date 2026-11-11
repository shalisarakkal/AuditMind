"use client";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY, DIALOG_SECONDARY } from "./DialogActions";
import { useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { formatDateTime, scanTypeLabel } from "@/lib/domain";
import { sourceTimeInput, snapshotKindLabel, snapshotKinds, snapshotReason, type AbsenceReviewQueueItem, type AbsenceReviewQueuePage, type SnapshotView, type Comparison, type ReviewCandidate } from "@/lib/scanSnapshots";
import FindingActionDialog from "./FindingActionDialog";
import ConfirmPanel from "./ConfirmPanel";

const control = "mt-1 w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none focus:ring-1 focus:ring-cyan disabled:opacity-50";
const button = DIALOG_SECONDARY;
const primaryButton = DIALOG_PRIMARY;
const neutralButton = DIALOG_NEUTRAL;
const actionLayout = "grid grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center";

function Reasons({ values }: { values: string[] }) {
  return values.length ? <ul className="list-inside list-disc text-sm text-yellow-100">{values.map(value => <li key={value}>{snapshotReason(value)}</li>)}</ul> : null;
}

export function SnapshotDetails({ view, label }: { view: SnapshotView; label: string }) {
  const record = view.declaration, fields = record?.declaration;
  return <section aria-label={label} className="min-w-0 space-y-2 rounded border border-white/15 p-3 text-sm">
    <h3 className="break-words font-semibold">{label}: {view.scan.filename || view.scan.id}</h3>
    <p>{scanTypeLabel(view.scan.scan_type)} · Import status: {snapshotKindLabel(view.scan.status)}</p>
    <p>Import finished: {formatDateTime(view.scan.completed_at)}</p>
    <p>{record ? `Version ${record.version} · ${snapshotKindLabel(record.state)}` : "No declaration saved"}</p>
    {record && fields && <>
      <p>Source snapshot: {snapshotKindLabel(fields.snapshot_kind)}</p>
      <p>Source snapshot time: {fields.source_snapshot_at ? formatDateTime(fields.source_snapshot_at) : "Not provided"}</p>
      <p className="break-words">Tool: {fields.tool_name} · Instance: {fields.tool_instance_id} · Configuration: {fields.tool_configuration_id}</p>
      <p>Coverage: {fields.coverage_confirmed ? "Confirmed by declarer" : "Not confirmed"}</p>
      <p className="whitespace-pre-wrap break-words">Targets: {fields.targets.join(", ")}</p>
      <p className="whitespace-pre-wrap break-words">Exclusions: {fields.exclusions.join(", ") || "None declared"}</p>
      <p className="whitespace-pre-wrap break-words">Unreachable targets: {fields.unreachable_targets.join(", ") || "None declared"}</p>
      <p className="break-words">{record.actor_label} · {formatDateTime(record.created_at)}</p>
      <p className="whitespace-pre-wrap break-words">Rationale: {record.rationale}</p>
    </>}
    <Reasons values={[...view.declaration_blockers, ...view.complete_blockers]} />
    <details><summary>Technical scan identity</summary><p className="break-all">Scan ID: {view.scan.id}</p><p className="break-all">Import configuration: {view.scan.ingestion_config_fingerprint || "Not captured"}</p></details>
  </section>;
}

export default function ScanSnapshotDialog({ orgId, orgName, scanId, writer, onClose, onBaseline, baselineId, onCompare }: {
  orgId: string; orgName: string; scanId: string; writer: boolean; onClose(): void;
  onBaseline(name: string): void; baselineId?: string; onCompare(): void;
}) {
  const view = useApi<SnapshotView>(`/orgs/${orgId}/scans/${scanId}/snapshot`);
  const [editing, setEditing] = useState(false), [revoking, setRevoking] = useState(false);
  const [busy, setBusy] = useState(false), [stale, setStale] = useState(false);
  const [error, setError] = useState<string | null>(null), [reason, setReason] = useState("");
  const inFlight = useRef(false);
  const path = `/orgs/${orgId}/scans/${scanId}/snapshot`;
  async function write(body: Record<string, unknown>, revoke = false) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      if (revoke) await api.post(path + "/revoke", body); else await api.put(path, body);
      setEditing(false); setRevoking(false); setReason(""); view.reload();
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail as { code?: string; reasons?: unknown } | undefined : undefined;
      const extra = Array.isArray(detail?.reasons) ? detail.reasons.filter((value): value is string => typeof value === "string").map(snapshotReason).join("; ") : "";
      setError((err instanceof Error ? err.message : "Could not save declaration") + (extra ? `: ${extra}` : ""));
      if (err instanceof ApiError && err.status === 409 && detail?.code === "snapshot_version_conflict") setStale(true);
    } finally { inFlight.current = false; setBusy(false); }
  }
  function reload() { setStale(false); setEditing(false); setRevoking(false); setError(null); view.reload(); }
  const data = view.data;
  return <FindingActionDialog title="Scan snapshot" orgName={orgName} onClose={() => { if (!inFlight.current) onClose(); }}>
    <div aria-busy={busy} className="space-y-3">
      <p className="text-sm text-white/70">Declare what the source scan covered. Declarations are user assertions; they do not verify controls or change findings, workflow, scores or reports.</p>
      {view.loading ? <p role="status">Loading scan snapshot…</p> : view.error ? <p role="alert">{view.error} <button className={button} onClick={reload}>Retry snapshot</button></p> : data && <>
        <SnapshotDetails view={data} label="Upload" />
        {editing && <form key={data.declaration?.version || 0} onSubmit={event => {
          event.preventDefault(); const values = new FormData(event.currentTarget);
          const lines = (name: string) => String(values.get(name) || "").split(/\r?\n/).map(value => value.trim()).filter(Boolean);
          const entered = String(values.get("source_snapshot_at") || "");
          const sourceTime = entered ? new Date(entered) : null;
          if (sourceTime && !Number.isFinite(sourceTime.getTime())) { setError("Enter a valid source snapshot time."); return; }
          const originalTime = data.declaration?.declaration.source_snapshot_at;
          // datetime-local can omit zero seconds and cannot represent every
          // stored fraction or distinguish the repeated DST hour. Preserve an
          // unchanged source instant rather than silently reinterpreting it.
          const localEntered = entered.length === 16 ? `${entered}:00` : entered;
          const sourceValue = entered && originalTime && localEntered === sourceTimeInput(originalTime)
            ? originalTime : sourceTime?.toISOString() || null;
          void write({ expected_version: data.declaration?.version || 0,
            snapshot_kind: values.get("snapshot_kind"), tool_name: values.get("tool_name"), tool_instance_id: values.get("tool_instance_id"),
            tool_configuration_id: values.get("tool_configuration_id"), targets: lines("targets"), exclusions: lines("exclusions"),
            unreachable_targets: lines("unreachable_targets"), coverage_confirmed: values.get("coverage_confirmed") === "on", rationale: values.get("rationale"),
            source_snapshot_at: sourceValue });
        }}><fieldset disabled={busy || stale} className="space-y-3">
          <label className="block text-sm">Source snapshot type<select name="snapshot_kind" aria-label="Source snapshot type" className={control} defaultValue={data.declaration?.declaration.snapshot_kind || "partial"}>{snapshotKinds.map(kind => <option key={kind} value={kind}>{snapshotKindLabel(kind)}</option>)}</select></label>
          <label className="block text-sm">Source snapshot time<input type="datetime-local" name="source_snapshot_at" className={control} step="1" defaultValue={sourceTimeInput(data.declaration?.declaration.source_snapshot_at)} /></label>
          <p className="text-xs text-white/70">Use the time the source scan completed or snapshot was taken, not the upload time. Complete requires this time; unknown time can be left blank for a non-complete snapshot.</p>
          {([ ["tool_name", "Tool name"], ["tool_instance_id", "Tool instance ID"], ["tool_configuration_id", "Tool configuration ID"] ] as const).map(([name, label]) => <label key={name} className="block text-sm">{label}<input name={name} className={control} required maxLength={200} defaultValue={data.declaration?.declaration[name] || ""} /></label>)}
          <p className="text-xs text-white/70">Use stable tool and policy identifiers from your scanner. A filename is not a tool instance. Describe scope using CIDRs, host/resource IDs or named groups; one entry per line, up to 500 entries.</p>
          {([ ["targets", "Target scope"], ["exclusions", "Excluded scope"], ["unreachable_targets", "Unreachable targets"] ] as const).map(([name, label]) => <label key={name} className="block text-sm">{label}<textarea name={name} className={control} required={name === "targets"} maxLength={128000} rows={3} defaultValue={data.declaration?.declaration[name].join("\n") || ""} /></label>)}
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="coverage_confirmed" defaultChecked={data.declaration?.declaration.coverage_confirmed || false} />I confirm the source scan assessed every target in the declared scope, apart from listed exclusions.</label>
          <p className="text-xs text-white/70">Complete requires confirmed coverage, no unreachable targets and an import with no errors, skips or warnings. Use Partial, Incremental, Failed or Cancelled when appropriate.</p>
          <label className="block text-sm">Declaration rationale<textarea name="rationale" className={control} required maxLength={12000} rows={2} /></label>
          <footer className={DIALOG_FOOTER}><button type="button" className={neutralButton} onClick={() => { setEditing(false); setError(null); }}>Cancel editing</button><button type="submit" className={primaryButton}>{busy ? "Saving…" : "Save declaration"}</button></footer>
        </fieldset></form>}
        {revoking && <div className="space-y-3"><label className="block text-sm">Revocation rationale<textarea className={control} value={reason} onChange={e => setReason(e.target.value)} maxLength={12000} disabled={busy || stale} /></label>
          <ConfirmPanel label="Revoke scan declaration" message="Append a revocation? Existing declaration history is retained." confirmLabel="Revoke declaration" busy={busy || stale}
            onCancel={() => { setRevoking(false); setReason(""); }} onConfirm={() => {
              if (!reason.trim()) { setError("Provide a revocation rationale."); return; }
              void write({ expected_version: data.declaration?.version, rationale: reason.trim() }, true);
            }} /></div>}
      </>}
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {stale && <p className="text-sm">Reload before retrying. Reloading discards your draft. <button type="button" className={button} onClick={reload}>Reload saved declaration</button></p>}
      <footer aria-label="Snapshot actions" className="space-y-3 border-t border-white/15 pt-4">
        {data && !view.loading && !view.error && !editing && !revoking && <div className={actionLayout}>
          {writer && <button type="button" className={data.declaration ? button : primaryButton} disabled={busy || data.declaration_blockers.length > 0} onClick={() => setEditing(true)}>{data.declaration ? "Revise declaration" : "Declare snapshot"}</button>}
          {writer && data.declaration?.state === "declared" && <button type="button" className={button} onClick={() => setRevoking(true)}>Revoke declaration</button>}
          <button type="button" className={button} onClick={() => onBaseline(data.scan.filename || scanId)}>Use as baseline</button>
          {baselineId && baselineId !== scanId && <button type="button" className={button} onClick={onCompare}>Review against baseline</button>}
        </div>}
        <div className="flex justify-end">
          <button type="button" data-confirm-cancel disabled={busy} className={`${neutralButton} w-full sm:w-auto`} onClick={onClose}>Close</button>
        </div>
      </footer>
    </div>
  </FindingActionDialog>;
}

export function ScanSnapshotComparisonDialog({ orgId, orgName, baselineId, currentId, writer = false, onClose }: {
  orgId: string; orgName: string; baselineId: string; currentId: string; writer?: boolean; onClose(): void;
}) {
  const baseline = useApi<SnapshotView>(`/orgs/${orgId}/scans/${baselineId}/snapshot`);
  const current = useApi<SnapshotView>(`/orgs/${orgId}/scans/${currentId}/snapshot`);
  const [result, setResult] = useState<Comparison | null>(null), [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null), [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const loading = baseline.loading || current.loading;
  const errorText = baseline.error || current.error || error;
  async function compare(offset = 0, append = false) {
    if (inFlight.current || !baseline.data?.declaration || !current.data?.declaration) return;
    inFlight.current = true; setBusy(true); if (!append) setResult(null); setError(null);
    try {
      const next = await api.post<Comparison>(`/orgs/${orgId}/scans/snapshot-comparison`, {
        baseline_scan_id: baselineId, current_scan_id: currentId,
        baseline_version: baseline.data.declaration.version, current_version: current.data.declaration.version,
        candidate_offset: offset, candidate_limit: result?.candidate_limit ?? 50,
      });
      if (append && result?.review_token !== next.review_token) {
        setResult(null);
        throw new Error("Scan review changed while loading candidates. Compare scans again before continuing.");
      }
      setResult(previous => append && previous
        ? { ...next, candidate_offset: previous.candidate_offset,
          review_candidates: [...previous.review_candidates, ...next.review_candidates] }
        : next);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not review scans"); if (err instanceof ApiError && err.status === 409) setStale(true); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function saveToQueue() {
    if (inFlight.current || !result?.absence_eligible || !result.review_token || !result.candidate_count
        || !baseline.data?.declaration || !current.data?.declaration) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const saved = await api.post<Comparison>(`/orgs/${orgId}/scans/snapshot-comparison/queue`, {
        baseline_scan_id: baselineId, current_scan_id: currentId,
        baseline_version: baseline.data.declaration.version, current_version: current.data.declaration.version,
        candidate_offset: 0, candidate_limit: result.candidate_limit, review_token: result.review_token,
      });
      setResult(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save review queue");
      if (err instanceof ApiError && err.status === 409) setStale(true);
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <FindingActionDialog title="Review scan snapshots" orgName={orgName} onClose={() => { if (!inFlight.current) onClose(); }}>
    <div aria-busy={busy} className="space-y-3">
      <p className="text-sm text-white/70">Comparing scans is read-only and uses complete declarations and current administrator-reviewed native Nessus identities. Saving candidates records a historical review snapshot that remains after source records are purged. A candidate is not proof of remediation or a workflow decision. It does not change findings, workflow, archive state or scores.</p>
      {loading ? <p role="status">Loading comparison snapshots…</p> : <>
        {baseline.data && <SnapshotDetails view={baseline.data} label="Baseline" />}
        {current.data && <SnapshotDetails view={current.data} label="Current" />}
      </>}
      {errorText && <p role="alert" className="text-sm text-red-300">{errorText}</p>}
      {result && <section aria-label="Comparison result" className="space-y-2 rounded border border-white/15 p-3 text-sm">
        <p className="font-semibold">{result.declared_metadata_matches ? "Declared scan metadata matches" : "Snapshots have compatibility blockers"}</p>
        <p>Reviewed: {formatDateTime(result.reviewed_at)}</p>
        <Reasons values={result.blocking_reasons} />
        <p className="font-semibold">Candidate review {result.absence_eligible ? "available" : "blocked"}</p>
        <Reasons values={result.absence_blockers} />
        {!result.blocking_reasons.length && !result.absence_blockers.some(reason => reason.endsWith("scan_observation_limit_exceeded")) &&
          <p>Identity review coverage: baseline {result.baseline_reviewable_observations} reviewable / {result.baseline_unreviewable_observations} unreviewable; current {result.current_reviewable_observations} reviewable / {result.current_unreviewable_observations} unreviewable. Ambiguous baseline identities excluded: {result.ambiguous_baseline_identity_count}.</p>}
        {result.review_queue_batch_id && <p role="status">Saved {result.review_queue_item_count} candidate{result.review_queue_item_count === 1 ? "" : "s"} to the durable review queue. This does not change finding state.</p>}
        {Object.entries(result.scope_differences).map(([key, values]) => <p key={key} className="break-words">{key.replaceAll("_", " ").replace(/^./, c => c.toUpperCase())}: {values.join(", ") || "None"}</p>)}
        {result.absence_eligible && <div className="space-y-3 border-t border-white/15 pt-3">
          <h3 className="font-semibold">Findings to review ({result.candidate_count})</h3>
          <p className="text-white/70">These active findings have a current reviewed identity in the baseline but no matching identity in the current scan. Missing observations alone never resolve or archive a finding.</p>
          {result.candidate_count === 0 && <p>{result.baseline_reviewable_observations === 0 ? "No baseline observations have a current reviewed identity supported by this comparison." : "No review candidates were found."}</p>}
          <ul className="space-y-2">
            {result.review_candidates.map(candidate => <ReviewCandidateRow key={candidate.finding_id} candidate={candidate} orgId={orgId} />)}
          </ul>
          {result.candidate_offset + result.review_candidates.length < result.candidate_count && <button type="button" className={button} disabled={busy || stale} onClick={() => void compare(result.candidate_offset + result.review_candidates.length, true)}>{busy ? "Loading…" : "Load more candidates"}</button>}
          {writer && !result.review_queue_batch_id && <button type="button" className={button} disabled={busy || stale || !result.review_token || !result.candidate_count} onClick={() => void saveToQueue()}>{busy ? "Saving…" : "Save candidates to review queue"}</button>}
        </div>}
      </section>}
      {!loading && (!baseline.data?.declaration || !current.data?.declaration) && <p className="text-sm">Both uploads need a saved declaration before review.</p>}
      <footer aria-label="Comparison actions" className="space-y-3 border-t border-white/15 pt-4">
      <div className={actionLayout}>
        <button type="button" className={primaryButton} disabled={loading || busy || stale || !!baseline.error || !!current.error || !baseline.data?.declaration || !current.data?.declaration} onClick={() => void compare()}>{busy ? "Reviewing…" : "Compare scans and build review list"}</button>
        <button type="button" className={button} disabled={busy} onClick={() => { setResult(null); setError(null); setStale(false); baseline.reload(); current.reload(); }}>Reload snapshots</button>
      </div>
      <div className="flex justify-end"><button type="button" className={`${neutralButton} w-full sm:w-auto`} data-confirm-cancel disabled={busy} onClick={onClose}>Close</button></div>
      </footer>
    </div>
  </FindingActionDialog>;
}

export function ScanSnapshotQueueDialog({ orgId, orgName, writer, onClose }: {
  orgId: string; orgName: string; writer: boolean; onClose(): void;
}) {
  const [state, setState] = useState<"pending" | "kept_active" | "all">("pending");
  const [offset, setOffset] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const [conflict, setConflict] = useState(false);
  const limit = 50;
  const queue = useApi<AbsenceReviewQueuePage>(
    `/orgs/${orgId}/scans/absence-review-queue?state=${state}&limit=${limit}&offset=${offset}`);

  async function decide(item: AbsenceReviewQueueItem) {
    const rationale = drafts[item.id]?.trim();
    if (!rationale || inFlight.current || queue.loading || queue.error || conflict) return;
    inFlight.current = true;
    setBusyId(item.id); setError(null);
    try {
      await api.post<AbsenceReviewQueueItem>(`/orgs/${orgId}/scans/absence-review-queue/${item.id}/decision`, {
        expected_version: item.decision_version,
        action: item.state === "pending" ? "keep_active" : "reopen",
        rationale,
      });
      setDrafts(values => ({ ...values, [item.id]: "" }));
      setOffset(0);
      queue.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update review queue");
      if (err instanceof ApiError && err.status === 409) setConflict(true);
    } finally { inFlight.current = false; setBusyId(null); }
  }

  const first = queue.data && queue.data.total ? offset + 1 : 0;
  const last = queue.data ? Math.min(offset + queue.data.items.length, queue.data.total) : 0;
  return <FindingActionDialog title="Absence review queue" orgName={orgName} onClose={() => { if (!inFlight.current) onClose(); }}>
    <div aria-busy={busyId !== null} className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
      <p className="text-sm text-white/70">Saved candidates are historical review snapshots retained after source-record purge, not proof of remediation. Keeping a finding active or reopening a queue item records a review only; neither action changes finding workflow, archive state or scores. Suppression and automatic reconciliation are not available here.</p>
      <label className="block text-sm">Show
        <select className={control} disabled={busyId !== null} value={state} onChange={event => { setState(event.target.value as typeof state); setOffset(0); setError(null); setConflict(false); }}>
          <option value="pending">Pending review</option>
          <option value="kept_active">Kept active</option>
          <option value="all">All saved candidates</option>
        </select>
      </label>
      {queue.loading && !queue.data && <p role="status">Loading saved review queue…</p>}
      {queue.loading && queue.data && <p role="status">Refreshing saved review queue…</p>}
      {queue.error && <p role="alert">{queue.error} <button type="button" className="text-cyan underline" onClick={queue.reload}>Retry queue</button></p>}
      {error && <p role="alert">{error}</p>}
      <button type="button" className={button} disabled={busyId !== null || queue.loading} onClick={() => { setError(null); setConflict(false); queue.reload(); }}>Reload queue</button>
      {conflict && <p className="text-sm">Reload and review the current queue before retrying. If the finding changed, build a fresh scan comparison. Your rationale is retained.</p>}
      {queue.data && queue.data.items.length === 0 && <p>No candidates in this queue view.</p>}
      {queue.data && <ul className="space-y-3">
        {queue.data.items.map(item => {
          const candidate = item.candidate;
          const baselineName = item.comparison.baseline.scan.filename || item.comparison.baseline.scan.id;
          const currentName = item.comparison.current.scan.filename || item.comparison.current.scan.id;
          return <li key={item.id} className="space-y-2 rounded border border-white/15 p-3 text-sm">
            <p className="break-words font-medium">{candidate.description || candidate.category || "Finding"} · {candidate.severity}</p>
            <p>{candidate.domain.replaceAll("_", " ")} · Workflow at review: {candidate.workflow_status}</p>
            <p className="break-all text-xs text-white/70">Finding ID: {candidate.finding_id}</p>
            <p>Baseline: {baselineName} · Current: {currentName}</p>
            <p>Saved {formatDateTime(item.created_at)} · Baseline observation recorded {formatDateTime(candidate.baseline_recorded_at)}</p>
            {item.rationale && <p role="status">{item.state === "kept_active" ? "Kept active" : "Review reopened"} by {item.actor_label} on {formatDateTime(item.decided_at)}: {item.rationale}</p>}
            <Link className="text-cyan underline" href={`/findings?${new URLSearchParams({ org: orgId, finding_id: candidate.finding_id })}`}>Open finding</Link>
            {writer && <form className="space-y-2" onSubmit={event => { event.preventDefault(); void decide(item); }}>
              <label className="block text-sm">{item.state === "pending" ? "Review rationale" : "Reason to reopen review"}
                <textarea className={control} rows={2} required maxLength={12000} disabled={busyId !== null || queue.loading || !!queue.error || conflict} value={drafts[item.id] || ""}
                  onChange={event => setDrafts(values => ({ ...values, [item.id]: event.target.value }))} />
              </label>
              <button type="submit" className={button} disabled={busyId !== null || queue.loading || !!queue.error || conflict || !drafts[item.id]?.trim()}>
                {busyId === item.id ? "Saving…" : item.state === "pending" ? "Keep finding active" : "Reopen review"}
              </button>
            </form>}
          </li>;
        })}
      </ul>}
      {queue.data && <div className="flex items-center justify-between gap-3 text-sm">
        <span>Showing {first}–{last} of {queue.data.total}</span>
        <div className="flex gap-2">
          <button type="button" className={button} disabled={busyId !== null || offset === 0 || queue.loading} onClick={() => setOffset(value => Math.max(0, value - limit))}>Previous</button>
          <button type="button" className={button} disabled={busyId !== null || last >= queue.data.total || queue.loading} onClick={() => setOffset(value => value + limit)}>Next</button>
        </div>
      </div>}
      <footer className={DIALOG_FOOTER}>
        <button type="button" data-confirm-cancel disabled={busyId !== null} className={`${neutralButton} w-full sm:w-auto`} onClick={onClose}>Close</button>
      </footer>
    </div>
  </FindingActionDialog>;
}

function ReviewCandidateRow({ candidate, orgId }: { candidate: ReviewCandidate; orgId: string }) {
  return <li className="min-w-0 rounded border border-white/15 p-3">
    <p className="break-words font-medium">{candidate.description || candidate.category || "Finding"} · {candidate.severity}</p>
    <p>{candidate.domain.replaceAll("_", " ")} · Workflow: {candidate.workflow_status}</p>
    <p className="break-all text-xs text-white/70">Finding ID: {candidate.finding_id}</p>
    <p className="text-xs text-white/70">Baseline observations: {candidate.reviewable_baseline_observation_count} · latest recorded {formatDateTime(candidate.baseline_recorded_at)}</p>
    <Link className="text-cyan underline" href={`/findings?${new URLSearchParams({ org: orgId, finding_id: candidate.finding_id })}`}>Open finding</Link>
  </li>;
}
