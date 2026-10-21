"use client";

import { useRef, useState } from "react";

type Props = {
  isOpen: boolean;
  mode?: "ai" | "rule_based_test";
  onClose: () => void;
  onGenerate: (payload: { title: string; frameworks: string[] }, mode: "ai" | "rule_based_test") => Promise<void>;
};

export function GenerateReportModal({ isOpen, mode = "ai", onClose, onGenerate }: Props) {
  const [title, setTitle] = useState(() => `Cyber Resilience Audit - ${new Date().toLocaleDateString("en-US", { month: "short", year: "numeric" })}`);
  const [cis, setCis] = useState(true);
  const [nist, setNist] = useState(true);
  const [iso, setIso] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    if (!title.trim()) {
      setError("Please provide a report title.");
      return;
    }

    const frameworks: string[] = [];
    if (cis) frameworks.push("CIS");
    if (nist) frameworks.push("NIST");
    if (iso) frameworks.push("ISO");

    if (mode === "ai" && frameworks.length === 0) {
      setError("Select at least one compliance framework.");
      return;
    }

    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await onGenerate({ title: title.trim(), frameworks: mode === "ai" ? frameworks : [] }, mode);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to queue report generation");
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-[#0e1626] p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <h2 className="text-lg font-semibold text-white">
            {mode === "ai" ? "Generate AI Cyber Resilience Audit Report" : "Generate Rule-Based Test Report"}
          </h2>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white transition-colors"
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-5">
          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="report-title" className="block text-xs font-medium uppercase tracking-wider text-white/70">
              Report Title
            </label>
            <input
              id="report-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/30 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400"
              placeholder="e.g. Q4 Executive Cyber Resilience Audit"
            />
          </div>

          {mode === "ai" ? <div>
            <label className="block text-xs font-medium uppercase tracking-wider text-white/70">
              Compliance Frameworks (RAG Standards)
            </label>
            <p className="mt-1 text-xs text-white/50">
              Claude evaluates active findings and assets against selected standards from pgvector knowledge base.
            </p>

            <div className="mt-3 space-y-2.5">
              <label className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-2.5 hover:bg-white/[0.04] cursor-pointer">
                <input
                  type="checkbox"
                  checked={cis}
                  onChange={(e) => setCis(e.target.checked)}
                  className="rounded border-white/20 bg-white/10 text-cyan-500 focus:ring-cyan-400"
                />
                <div>
                  <div className="text-sm font-medium text-white">CIS Critical Security Controls v8</div>
                  <div className="text-xs text-white/50">Asset inventory, access control, vulnerability management</div>
                </div>
              </label>

              <label className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-2.5 hover:bg-white/[0.04] cursor-pointer">
                <input
                  type="checkbox"
                  checked={nist}
                  onChange={(e) => setNist(e.target.checked)}
                  className="rounded border-white/20 bg-white/10 text-cyan-500 focus:ring-cyan-400"
                />
                <div>
                  <div className="text-sm font-medium text-white">NIST CSF 2.0</div>
                  <div className="text-xs text-white/50">Govern, Identify, Protect, Detect, Respond, Recover</div>
                </div>
              </label>

              <label className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-2.5 hover:bg-white/[0.04] cursor-pointer">
                <input
                  type="checkbox"
                  checked={iso}
                  onChange={(e) => setIso(e.target.checked)}
                  className="rounded border-white/20 bg-white/10 text-cyan-500 focus:ring-cyan-400"
                />
                <div>
                  <div className="text-sm font-medium text-white">ISO/IEC 27001:2022</div>
                  <div className="text-xs text-white/50">Annex A technological, organizational, and physical controls</div>
                </div>
              </label>
            </div>
          </div> : (
            <div role="note" className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">
              Test-only preview. This report uses deterministic finding scores; it does not use AI or an external
              provider, and it does not evaluate CIS, NIST, or ISO controls.
            </div>
          )}

          <div className="flex justify-end gap-3 border-t border-white/10 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-lg px-4 py-2 text-sm text-white/70 hover:bg-white/5 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-2 rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-black border-t-transparent" />
                  <span>Queueing...</span>
                </>
              ) : (
                mode === "ai" ? "Generate Report" : "Generate Test Report"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
