"use client";
import { useId, useRef, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import type { Catalog, ControlMapping } from "@/lib/controlCatalog";
import { DOMAIN_LABELS } from "@/lib/domain";
import FindingActionDialog from "./FindingActionDialog";
import MappingDecisionView from "./ControlMappingDecision";
import ControlCatalogBrowser, { CATALOG_INPUT } from "./ControlCatalogBrowser";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY } from "./DialogActions";

export default function ControlMappingDialog({ orgId, orgName, mapping, catalogs, action, onClose, onChanged }: {
  orgId: string; orgName: string; mapping: ControlMapping; catalogs: Catalog[]; action: "propose" | "approve" | "withdraw"; onClose(): void; onChanged(): void;
}) {
  const id = useId(), pending = useRef(false);
  const initial = mapping.proposal || mapping.effective;
  const [release, setRelease] = useState(initial?.catalog.id || catalogs[0]?.id || "");
  const [selected, setSelected] = useState(initial?.controls.map(c => c.control_id) || []);
  const [reason, setReason] = useState(action === "propose" && mapping.proposal ? mapping.proposal.rationale : "");
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), [unknown, setUnknown] = useState(false);
  const title = action === "propose" ? "Propose control mapping" : action === "approve" ? "Approve control mapping" : "Withdraw control mapping";
  const unchanged = action === "propose" && mapping.proposal && release === mapping.proposal.catalog.id && reason.trim() === mapping.proposal.rationale && [...selected].sort().join() === mapping.proposal.controls.map(c => c.control_id).sort().join();
  const resource = mapping.context_kind === "rule" && mapping.rule_id ? `/orgs/${orgId}/control-rules/${mapping.rule_id}` : mapping.finding_id ? `/orgs/${orgId}/findings/${mapping.finding_id}/control-mapping` : null;
  const valid = !!resource && !!reason.trim() && !unchanged && (action !== "propose" || (!!release && selected.length > 0 && selected.length <= 20));
  function close() { if (!pending.current) { if (error) onChanged(); onClose(); } }
  async function submit() {
    if (pending.current || !valid || error || !resource) return;
    pending.current = true; setBusy(true);
    const key = { source: mapping.source, domain: mapping.domain, category: mapping.category, expected_version: mapping.version, rationale: reason.trim() };
    let saved = false;
    try {
      await api.post(`${resource}/${action === "propose" ? "proposals" : action}`, {
        ...key, ...(action === "propose" ? { catalog_id: release, control_ids: selected } : action === "approve" ? { proposal_version: mapping.proposal?.version } : {}),
      });
      saved = true;
    } catch (cause) {
      const uncertain = !(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500 || cause.status === 408;
      setUnknown(uncertain);
      setError(`${uncertain ? "Outcome unknown; this review may have committed. " : ""}${cause instanceof Error ? cause.message : "Review failed"} Close and reload the saved mapping before trying again. Closing does not undo a submitted review.`);
    } finally { pending.current = false; setBusy(false); }
    if (saved) { onChanged(); onClose(); }
  }
  return <FindingActionDialog title={title} orgName={orgName} onClose={close}>
    <form aria-busy={busy} className="min-w-0 space-y-4 text-sm [overflow-wrap:anywhere]" onSubmit={e => { e.preventDefault(); void submit(); }}>
      <p>This reviews relevance for every finding in this organization with this exact source, domain and category. It does not change finding status, scores or saved reports, or certify compliance.</p>
      <dl className="grid gap-1 sm:grid-cols-2"><dt>Source</dt><dd>{mapping.source || "Not provided"}</dd><dt>Domain</dt><dd>{DOMAIN_LABELS[mapping.domain]}</dd><dt>Category</dt><dd>{mapping.category || "Not provided (uncategorised)"}</dd></dl>
      <p className="text-xs text-white/60">Mapping generation {mapping.version}</p>
      {action === "propose" ? <ControlCatalogBrowser catalogs={catalogs} basePath={`/orgs/${orgId}/control-catalogs`} value={release} selected={selected} onSelection={setSelected} onChange={value => { setRelease(value); setSelected([]); }} disabled={busy || !!error} /> : <>
        <p>{action === "approve" ? "Review the exact proposed controls before approving." : "Withdraw the effective mapping and any pending proposal. Findings will display Unmapped."}</p>
        {action === "approve" && mapping.proposal && <MappingDecisionView decision={mapping.proposal} title="Proposal to approve" />}
        {action === "withdraw" && mapping.effective && <MappingDecisionView decision={mapping.effective} title="Effective mapping to withdraw" />}
        {action === "withdraw" && mapping.proposal && <MappingDecisionView decision={mapping.proposal} title="Pending proposal to withdraw" />}
      </>}
      <label className="block" htmlFor={`${id}-reason`}>Review rationale</label>
      <textarea id={`${id}-reason`} maxLength={2000} className={CATALOG_INPUT} value={reason} disabled={busy || !!error} onChange={e => setReason(e.target.value)} />
      {error && <p role="alert" className="text-red-300">{error}</p>}
      <footer className={DIALOG_FOOTER}><button data-confirm-cancel type="button" className={DIALOG_NEUTRAL} disabled={busy} onClick={close}>{error || unknown ? "Close and reload" : "Cancel"}</button><button className={DIALOG_PRIMARY} disabled={busy || !!error || !valid}>{busy ? "Saving review…" : action === "propose" ? "Save proposal" : action === "approve" ? "Approve mapping" : "Withdraw mapping"}</button></footer>
    </form>
  </FindingActionDialog>;
}
