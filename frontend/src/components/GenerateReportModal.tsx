"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { useApi } from "@/lib/useApi";

type Props = {
  isOpen: boolean;
  orgId: string;
  orgName: string;
  canApprove: boolean;
  mode?: "ai" | "rule_based_test";
  onClose(): void;
  onGenerate(payload: { title: string; frameworks: string[] }, mode: "ai" | "rule_based_test"): Promise<void>;
};

const FRAMEWORKS = [
  ["CIS", "CIS Critical Security Controls v8", "Asset inventory, access control, vulnerability management"],
  ["NIST", "NIST CSF 2.0", "Govern, Identify, Protect, Detect, Respond, Recover"],
  ["ISO", "ISO/IEC 27001:2022", "Organizational, people, physical and technological controls"],
];

export function GenerateReportModal(props: Props) {
  // Each opening checks consent afresh; do not reuse another organization's state.
  return props.isOpen ? <ReportGenerationDialog key={props.orgId} {...props} /> : null;
}

function ReportGenerationDialog({ orgId, orgName, canApprove, mode = "ai", onClose, onGenerate }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  const headingId = useId();
  const descriptionId = useId();
  const helpId = useId();
  const prerequisiteId = useId();
  const [title, setTitle] = useState(() => `Cyber Resilience Audit - ${new Date().toLocaleDateString("en-US", { month: "short", year: "numeric" })}`);
  const [frameworks, setFrameworks] = useState(["CIS", "NIST", "ISO"]);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const consent = useApi<{ report_granted: boolean; report_target: string }>(mode === "ai" ? `/orgs/${orgId}/documents/settings` : null);
  const ready = mode === "rule_based_test" || (!consent.loading && !consent.error && consent.data?.report_granted === true);

  useEffect(() => {
    const element = dialog.current!;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    titleInput.current?.focus();
    return () => {
      element.close();
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (inFlight.current || !ready) return;
    if (!title.trim()) { setError("Please provide a report title."); titleInput.current?.focus(); return; }
    if (mode === "ai" && frameworks.length === 0) { setError("Select at least one framework."); return; }
    inFlight.current = true;
    setSubmitting(true);
    // Keep keyboard focus in the modal when all form controls become disabled.
    dialog.current?.focus();
    setError(null);
    try {
      await onGenerate({ title: title.trim(), frameworks: mode === "ai" ? frameworks : [] }, mode);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to queue report generation");
      // Backend authorization still handles revocation after the initial check.
      if (mode === "ai") consent.reload();
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  return (
    <dialog ref={dialog} tabIndex={-1} aria-labelledby={headingId} aria-describedby={descriptionId} aria-modal="true"
      onKeyDown={event => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex='0']"));
        const first = controls[0];
        const last = controls.at(-1);
        if (!first || !last) { event.preventDefault(); event.currentTarget.focus(); return; }
        if (event.shiftKey && (document.activeElement === first || document.activeElement === event.currentTarget)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === event.currentTarget)) { event.preventDefault(); first.focus(); }
      }}
      onCancel={event => { event.preventDefault(); if (!inFlight.current) onClose(); }}
      className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg overflow-y-auto rounded-xl border border-white/10 bg-navy p-0 text-white shadow-xl backdrop:bg-black/75 backdrop:backdrop-blur-sm">
      <header className="flex items-start justify-between gap-4 border-b border-white/10 p-6">
        <div>
          <h2 id={headingId} className="text-lg font-semibold">{mode === "ai" ? "Generate AI audit report" : "Generate rule-based test report"}</h2>
          <p id={descriptionId} className="mt-1 text-sm text-white/70">For {orgName}</p>
        </div>
        <button type="button" aria-label="Close report generation" disabled={submitting} onClick={onClose}
          className="rounded-md p-1 text-white/70 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan disabled:opacity-50">×</button>
      </header>
      <form onSubmit={handleSubmit} aria-busy={submitting}>
        <div className="space-y-5 p-6">
          {mode === "ai" && <section id={prerequisiteId} aria-label="AI report prerequisites" className="space-y-2 rounded-lg border border-white/20 p-3 text-sm">
            {consent.loading ? <p role="status">Checking report processing approval…</p> : consent.error ? <div role="alert" className="text-red-300">
              <p>Could not check report processing approval: {consent.error}</p>
              <button type="button" onClick={consent.reload} className="mt-2 text-cyan hover:underline">Retry approval check</button>
            </div> : !consent.data?.report_granted ? <>
              <p className="text-amber-200">External AI report processing is not approved for {orgName}.</p>
              <p>{canApprove ? "Review and approve processing in Documents → Data processing consent if authorized." : "Ask an organization admin to review processing approval in Documents → Data processing consent."}</p>
              <Link href={`/documents?org=${encodeURIComponent(orgId)}`} className="inline-block text-cyan underline">Review consent in Documents</Link>
            </> : <>
              <p>External AI report processing is approved for the current target.</p>
              <p className="break-words text-xs text-white/70">{consent.data.report_target}</p>
            </>}
            <p className="text-xs text-white/70">AI reports send sampled findings and permitted evidence excerpts to an external provider. Provider credentials, indexed evidence and a running worker must also be configured. Approval does not enable these automatically.</p>
          </section>}
          {error && <p role="alert" className="rounded-lg border border-red-400/30 bg-red-400/5 p-3 text-sm text-red-300">{error}</p>}
          <div>
            <label htmlFor={`${headingId}-title`} className="block text-sm font-medium text-white/80">Report title</label>
            <input ref={titleInput} id={`${headingId}-title`} value={title} onChange={event => setTitle(event.target.value)} required disabled={submitting}
              className="mt-2 w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none focus:ring-1 focus:ring-cyan disabled:opacity-60" />
          </div>
          {mode === "ai" ? <fieldset disabled={submitting} aria-describedby={helpId}>
            <legend className="text-sm font-medium text-white/80">Frameworks</legend>
            <p id={helpId} className="mt-1 text-xs text-white/70">Choose the frameworks supported by your permitted evidence. Selecting one does not install its standards or certify compliance.</p>
            <div className="mt-3 space-y-2">
              {FRAMEWORKS.map(([value, label, help]) => <label key={value} className="flex cursor-pointer items-start gap-3 rounded-lg border border-white/10 p-3 hover:bg-white/5">
                <input type="checkbox" checked={frameworks.includes(value)} onChange={() => setFrameworks(previous => previous.includes(value) ? previous.filter(item => item !== value) : [...previous, value])}
                  className="mt-1 accent-cyan focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan" />
                <span><span className="block text-sm font-medium">{label}</span><span className="block text-xs text-white/70">{help}</span></span>
              </label>)}
            </div>
          </fieldset> : <p role="note" className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">Test-only preview. This report uses deterministic finding scores; it does not use AI or an external provider, and it does not evaluate CIS, NIST, or ISO controls.</p>}
        </div>
        <footer className="sticky bottom-0 flex flex-wrap justify-end gap-3 border-t border-white/10 bg-navy p-4">
          <button type="button" disabled={submitting} onClick={onClose} className="rounded-md px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white disabled:opacity-50">Cancel</button>
          <button type="submit" disabled={submitting || !ready} aria-describedby={mode === "ai" ? prerequisiteId : undefined}
            className="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50">
            {submitting ? "Queueing…" : mode === "ai" ? "Generate Report" : "Generate Test Report"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
