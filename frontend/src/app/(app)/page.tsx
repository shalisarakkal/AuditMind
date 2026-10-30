"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import LoadingIndicator from "@/components/LoadingIndicator";
import { enumLabel } from "@/lib/presentation";

import ScoreCard from "@/components/ScoreCard";
import DashboardLoading from "@/components/DashboardLoading";
import SecuritySummary from "@/components/SecuritySummary";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import {
  DOMAIN_LABELS,
  DOMAIN_ORDER,
  SCAN_STATUS_BADGES,
  SCAN_TYPE_LABELS,
  SEVERITY_BADGES,
  SEVERITY_ORDER,
  formatDateTime,
  riskTierStyle,
} from "@/lib/domain";
import type { DashboardSummary, DashboardPending } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useDashboardState, type DashboardState } from "@/lib/useDashboardState";

export default function DashboardPage() {
  const { selectedOrg } = useApp();
  return <OrganizationDashboard key={selectedOrg!.id} orgId={selectedOrg!.id} orgName={selectedOrg!.name} />;
}

function OrganizationDashboard({ orgId, orgName }: { orgId: string; orgName: string }) {
  const [securityRefresh, setSecurityRefresh] = useState("");
  const { state, error } = useDashboardState(orgId);
  const identity = state ? `${orgId}:${state.settings_version}:${state.scoring_mode}:${state.scoring_mode === "evidence_qualified" ? `${state.evidence_revision}:${state.evaluation_id}` : "baseline"}:${state.snapshot_enabled ?? false}:${state.snapshot_generated_at ?? ""}` : null;

  return (
    <div className="min-w-0 space-y-8 [overflow-wrap:anywhere]">
      <div>
        <h1 className="text-2xl font-semibold text-white">Resilience dashboard</h1>
        <p className="mt-1 text-sm text-white/60">
          {orgName} — {!state ? "checking current scoring mode." : state.scoring_mode === "evidence_qualified" ? "scores require current reviewed evidence." : "findings-based baseline; not qualified evidence coverage."}
        </p>
      </div>

      <StatusMessage loading={false} error={error} />
      {!state && !error && <DashboardLoading checking />}
      {state && identity && <CurrentDashboard key={identity} orgId={orgId} expected={state} onSnapshot={setSecurityRefresh} />}
      <DashboardSecuritySummary key={securityRefresh} />
    </div>
  );
}

function CurrentDashboard({ orgId, expected, onSnapshot }: { orgId: string; expected: DashboardState; onSnapshot(value: string): void }) {
  const { data: response, error, loading, reload } = useApi<DashboardSummary | DashboardPending>(`/orgs/${orgId}/dashboard`, { background: true, keepPreviousData: true });
  const data = response && !("snapshot_state" in response) ? response : null;
  const refreshing = response?.snapshot_refresh_status === "pending" || response?.snapshot_refresh_status === "running";
  const [submitting, setSubmitting] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  useEffect(() => {
    if (!refreshing || loading || error) return;
    const timer = setTimeout(reload, 2000);
    return () => clearTimeout(timer);
  }, [refreshing, loading, error, response, reload]);
  useEffect(() => {
    if (data?.snapshot_generated_at) onSnapshot(data.snapshot_generated_at);
  }, [data?.snapshot_generated_at, onSnapshot]);
  const matching = data && (data.scoring_mode ?? "findings_based") === expected.scoring_mode
    && (data.settings_version ?? 0) === expected.settings_version
    && (expected.scoring_mode !== "evidence_qualified" || (data.evidence_revision === expected.evidence_revision && (data.evaluation_id ?? null) === expected.evaluation_id));
  return <><StatusMessage loading={false} error={error ?? refreshError} />
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p className="text-white/60">{data?.snapshot_generated_at ? `Last updated: ${formatDateTime(data.snapshot_generated_at)}` : response && "snapshot_state" in response ? response.snapshot_refresh_status === "failed" ? "Dashboard snapshot unavailable." : "Preparing the first saved Dashboard." : "Live Dashboard data"}</p>
      <button type="button" disabled={submitting || refreshing || loading} className="rounded-md border border-cyan px-3 py-2 text-cyan disabled:opacity-60"
        onClick={async () => {
          if (submitting || refreshing) return;
          setSubmitting(true); setRefreshError(null);
          try {
            if (response?.snapshot_refresh_status) await api.post(`/orgs/${orgId}/dashboard/refresh`, {});
            reload();
          } catch (cause) { setRefreshError(cause instanceof Error ? cause.message : "Could not refresh Dashboard"); }
          finally { setSubmitting(false); }
        }}>{submitting || refreshing ? "Refreshing…" : "Refresh dashboard"}</button>
    </div>
    {refreshing && <LoadingIndicator label={response?.snapshot_refresh_status === "pending" ? "Dashboard refresh queued." : "Refreshing Dashboard in the background."} detail={data ? "Previous results remain available." : "The first snapshot will appear when processing finishes."} />}
    {response?.snapshot_error && <p role="alert" className="text-sm text-red-300">{response.snapshot_error}</p>}
    {data?.snapshot_stale && <p role="status" className="text-sm text-white/70">Saved data may be out of date. Refresh to include recent changes; evidence-qualified scores require a matching current inventory.</p>}
    {loading && !data && <DashboardLoading />}
    {error && <button type="button" onClick={reload} className="text-sm text-cyan underline">Retry dashboard</button>}
    {matching ? <Dashboard data={data} /> : data && <p role="status">Dashboard inputs changed. Waiting for the latest scoring state; no stale scores are shown.</p>}</>;
}

function Dashboard({ data }: { data: DashboardSummary }) {
  const style = riskTierStyle(data.overall_score == null ? null : data.overall_tier);
  const domains = [...data.domains].sort((a, b) => DOMAIN_ORDER.indexOf(a.domain) - DOMAIN_ORDER.indexOf(b.domain));
  const totalFindings = SEVERITY_ORDER.reduce((sum, s) => sum + data.findings_by_severity[s], 0);

  return (
    <>
      <p className="text-sm text-white/60">{data.scoring_mode === "evidence_qualified"
        ? `Evidence-qualified scoring · ${data.qualified_domain_count ?? 0} of 7 domains qualified${data.qualification_evaluated_at ? ` · Last evaluated: ${formatDateTime(data.qualification_evaluated_at)}` : ""}`
        : "Findings-based baseline"}</p>
      {data.scoring_mode === "evidence_qualified" && data.evaluation_state !== "current" && <p role="status" className="text-sm text-white/70">A current evidence evaluation is required. <Link className="text-cyan underline" href="/settings">Open Settings</Link> to evaluate evidence. Unverified scores remain hidden.</p>}
      {data.overall_reason === "scope_mismatch" && <p role="status" className="text-sm text-white/70">Qualified domain scopes differ. An overall score cannot be assigned.</p>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="min-w-0 rounded-xl bg-navy-cyan-gradient p-4 sm:p-6 lg:col-span-2">
          <p className="text-sm text-white/80">Overall Resilience Score</p>
          <p className={`mt-2 ${data.overall_score == null ? "text-2xl font-medium" : "text-5xl font-bold"} ${style.text}`} data-testid="overall-score">
            {data.overall_score == null ? "Not assessed" : Math.round(data.overall_score)}
          </p>
          {data.overall_score != null && <p className={`mt-1 text-sm tracking-wide ${style.text}`}>{data.overall_tier ? enumLabel(data.overall_tier) : "Unassigned"} risk tier</p>}
        </div>
        <div className="min-w-0 rounded-xl border border-white/10 bg-white/5 p-4 sm:p-6">
          <p className="text-sm text-white/60">
            {data.asset_count} assets · {totalFindings} findings
          </p>
          <ul className="mt-3 space-y-1.5">
            {SEVERITY_ORDER.map((s) => (
              <li key={s} className="flex items-center justify-between text-sm">
                <span className={`rounded px-2 py-0.5 text-xs capitalize ${SEVERITY_BADGES[s]}`}>{s}</span>
                <span className="font-semibold text-white">{data.findings_by_severity[s]}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <section>
        <h2 className="mb-3 text-lg font-medium text-white">Per-domain scores</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {domains.map((d) => (
            <ScoreCard key={d.domain} label={DOMAIN_LABELS[d.domain]} score={d.score} tier={d.tier}
              unscoredLabel={d.evidence_status === "conflicting" ? "Review required" : d.evidence_status === "limited" ? "Insufficient evidence" : "Not assessed"}
              title={`${d.justification}${d.evidence_reason ? ` Evidence: ${d.evidence_reason.replaceAll("_", " ")}.` : ""}${d.qualification_scope ? ` Scope: ${d.qualification_scope}.` : ""}`} />
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-lg font-medium text-white">Top issues</h2>
          {data.top_findings.length === 0 ? (
            <p className="text-sm text-white/60">
              No findings yet. <Link href="/findings" className="text-cyan hover:underline">Upload findings</Link> to
              see your top issues.
            </p>
          ) : (
            <ul className="divide-y divide-white/10 rounded-xl border border-white/10 bg-white/5">
              {data.top_findings.map((f) => (
                <li key={f.id} className="flex items-start gap-3 p-3">
                  <span className={`mt-0.5 rounded px-2 py-0.5 text-xs capitalize ${SEVERITY_BADGES[f.severity]}`}>
                    {f.severity}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm text-white">{f.description ?? f.category ?? "Finding"}</p>
                    <p className="text-xs text-white/50">{DOMAIN_LABELS[f.domain]}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-lg font-medium text-white">Recent uploads</h2>
          {data.recent_scans.length === 0 ? (
            <p className="text-sm text-white/60">Nothing uploaded yet.</p>
          ) : (
            <ul className="divide-y divide-white/10 rounded-xl border border-white/10 bg-white/5">
              {data.recent_scans.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3 p-3 text-sm">
                  <div className="min-w-0">
                    <p className="truncate text-white">{s.filename ?? SCAN_TYPE_LABELS[s.scan_type] ?? s.scan_type}</p>
                    <p className="text-xs text-white/50">
                      {SCAN_TYPE_LABELS[s.scan_type] ?? s.scan_type} · {formatDateTime(s.started_at)}
                    </p>
                  </div>
                  <span className={`rounded px-2 py-0.5 text-xs capitalize ${SCAN_STATUS_BADGES[s.status]}`}>{s.status}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

    </>
  );
}

function DashboardSecuritySummary() {
  const { selectedOrg } = useApp();
  return <SecuritySummary key={selectedOrg!.id} orgId={selectedOrg!.id} />;
}
