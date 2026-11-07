"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
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
  return <OrganizationDashboard key={selectedOrg!.id} orgId={selectedOrg!.id} />;
}

function OrganizationDashboard({ orgId }: { orgId: string }) {
  const [tab, setTab] = useState<"findings" | "evidence">("findings");
  const [securityRefresh, setSecurityRefresh] = useState("");
  const { state, error } = useDashboardState(orgId);
  const identity = state ? `${orgId}:${state.settings_version}:${state.scoring_mode}:${state.scoring_mode === "evidence_qualified" ? `${state.evidence_revision}:${state.evaluation_id}` : "baseline"}:${state.snapshot_enabled ?? false}:${state.snapshot_generated_at ?? ""}` : null;

  return (
    <div className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
      {!state && <DashboardTitle checking={!error} />}

      <StatusMessage loading={false} error={error} />
      {!state && !error && <DashboardLoading checking />}
      {state && identity && <CurrentDashboard key={identity} orgId={orgId} expected={state} onSnapshot={setSecurityRefresh} tab={tab} onTabChange={setTab} />}
      <DashboardSecuritySummary key={securityRefresh} />
    </div>
  );
}

function DashboardTitle({ checking = false }: { checking?: boolean }) {
  return <div className="min-w-0">
    <h1 className="text-2xl font-semibold text-white">Resilience dashboard</h1>
    {checking && <p className="mt-0.5 text-xs text-white/60">Checking current scoring mode.</p>}
  </div>;
}

function CurrentDashboard({ orgId, expected, onSnapshot, tab, onTabChange }: { orgId: string; expected: DashboardState; onSnapshot(value: string): void; tab: "findings" | "evidence"; onTabChange(value: "findings" | "evidence"): void }) {
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
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
      <DashboardTitle />
      <div className="flex flex-wrap items-center gap-3 text-xs">
      <p className="text-white/60">{data?.snapshot_generated_at ? `Last updated: ${formatDateTime(data.snapshot_generated_at)}` : response && "snapshot_state" in response ? response.snapshot_refresh_status === "failed" ? "Dashboard snapshot unavailable." : "Preparing the first saved Dashboard." : "Live Dashboard data"}</p>
      <button type="button" disabled={submitting || refreshing || loading} className="rounded-md border border-cyan px-3 py-1.5 text-sm text-cyan disabled:opacity-60"
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
    </div>
    {refreshing && <LoadingIndicator label={response?.snapshot_refresh_status === "pending" ? "Dashboard refresh queued." : "Refreshing Dashboard in the background."} detail={data ? "Previous results remain available." : "The first snapshot will appear when processing finishes."} />}
    {response?.snapshot_error && <p role="alert" className="text-sm text-red-300">{response.snapshot_error}</p>}
    {data?.snapshot_stale && <p role="status" className="text-sm text-white/70">Saved data may be out of date. Refresh to include recent changes; evidence-qualified scores require a matching current inventory.</p>}
    {loading && !data && <DashboardLoading />}
    {error && <button type="button" onClick={reload} className="text-sm text-cyan underline">Retry dashboard</button>}
    {matching ? <Dashboard data={data} tab={tab} onTabChange={onTabChange} /> : data && <p role="status">Dashboard inputs changed. Waiting for the latest scoring state; no stale scores are shown.</p>}</>;
}

function Dashboard({ data, tab, onTabChange }: { data: DashboardSummary; tab: "findings" | "evidence"; onTabChange(value: "findings" | "evidence"): void }) {
  const tabsId = useId();
  const baseline = data.findings_baseline;
  const score = baseline ? baseline.overall_score : data.overall_score;
  const tier = baseline ? baseline.overall_tier : data.overall_tier;
  const style = riskTierStyle(score == null ? null : tier);
  const domains = [...(baseline?.domains ?? data.domains)].sort((a, b) => DOMAIN_ORDER.indexOf(a.domain) - DOMAIN_ORDER.indexOf(b.domain));

  return (
    <>
      <div role="tablist" aria-label="Dashboard assessment view" className="flex flex-wrap gap-2 border-b border-white/15 pb-2">
        {(["findings", "evidence"] as const).map((value, index) => <button key={value} type="button" role="tab"
          id={`${tabsId}-${value}-tab`} aria-controls={`${tabsId}-${value}-panel`} aria-selected={tab === value} tabIndex={tab === value ? 0 : -1}
          className={`rounded-md border px-4 py-2 text-sm font-medium ${tab === value ? "border-cyan bg-cyan text-navy" : "border-white/20 text-white/70 hover:text-white"}`}
          onClick={() => onTabChange(value)} onKeyDown={event => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : (index + 1) % 2;
            onTabChange(next === 0 ? "findings" : "evidence");
            event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
          }}>{value === "findings" ? "Findings-based" : "Evidence-based"}</button>)}
      </div>
      <section role="tabpanel" id={`${tabsId}-evidence-panel`} aria-labelledby={`${tabsId}-evidence-tab`} hidden={tab !== "evidence"} tabIndex={0} className="min-w-0 space-y-4">
        {tab === "evidence" && <EvidenceDashboard data={data} />}
      </section>
      <section role="tabpanel" id={`${tabsId}-findings-panel`} aria-labelledby={`${tabsId}-findings-tab`} hidden={tab !== "findings"} tabIndex={0} className="min-w-0 space-y-4">
      {data.status_scoring?.not_assessed && data.scoring_mode !== "evidence_qualified" && <p role="status" className="text-sm text-white/70">Verified exclusions leave no current-risk findings. This does not establish evidence coverage; scores are not assessed.</p>}
      {data.status_scoring?.exclusions_deferred && <p role="status" className="text-sm text-white/70">Inventory changed since this snapshot. Exclusions are withheld until the Dashboard is refreshed.</p>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="min-w-0 rounded-xl bg-navy-cyan-gradient p-4 md:min-h-[10rem]">
          <p className="text-sm text-white/80">{baseline ? "Findings-based resilience baseline" : "Overall Resilience Score"}</p>
          <p className={`mt-1 ${score == null ? "text-2xl font-medium" : "text-4xl font-bold"} ${style.text}`} data-testid="overall-score">
            {score == null ? "Not assessed" : Math.round(score)}
          </p>
          {score != null && <p className={`mt-1 text-sm tracking-wide ${style.text}`}>{tier ? enumLabel(tier) : "Unassigned"} risk tier</p>}
          {baseline && <p className="mt-2 text-xs text-white/80">Recorded finding risk; not proof of control effectiveness or complete evidence coverage.</p>}
        </div>
        <InventoryRiskSummary data={data} />
      </div>

      <section>
        <h2 className="mb-2 text-lg font-medium text-white">{baseline ? "Per-domain findings-based baselines" : "Per-domain scores"}</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {domains.map((d) => (
            <ScoreCard key={d.domain} label={DOMAIN_LABELS[d.domain]} score={d.score} tier={d.tier}
              unscoredLabel={d.evidence_status === "conflicting" ? "Review required" : d.evidence_status === "limited" ? "Insufficient evidence" : "Not assessed"}
              title={d.justification} />
          ))}
        </div>
      </section>
      </section>

      {tab === "evidence" && <p className="text-xs text-white/60">Known finding risks, independent of evidence qualification.</p>}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-lg font-medium text-white">Top issues</h2>
          {data.risk_top_stale ? <p className="text-sm text-white/60">Scoring evidence changed. Refresh Dashboard to update top issues.</p> : data.top_findings.length === 0 && data.status_scoring?.excluded_findings ? <p className="text-sm text-white/60">No current-risk findings in this snapshot. Recorded findings remain available on the Findings page.</p> : data.top_findings.length === 0 ? (
            <p className="text-sm text-white/60">
              No findings yet. <Link href="/findings" className="text-cyan underline">Upload findings</Link> to
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

function InventoryRiskSummary({ data }: { data: DashboardSummary }) {
  const total = SEVERITY_ORDER.reduce((sum, severity) => sum + data.findings_by_severity[severity], 0);
  return <section aria-label="Inventory and finding risk" className="min-w-0 rounded-xl border border-white/10 bg-white/5 p-4 md:min-h-[10rem]">
    <h2 className="text-sm font-medium text-white/80">Inventory and finding risk</h2>
    <p className="mt-1 text-sm text-white/60">{data.asset_count} assets · {total} findings</p>
    <ul className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2">
      {SEVERITY_ORDER.map(severity => <li key={severity} className="flex items-center justify-between text-sm">
        <span className={`rounded px-2 py-0.5 text-xs capitalize ${SEVERITY_BADGES[severity]}`}>{severity}</span>
        <span className="font-semibold text-white">{data.findings_by_severity[severity]}</span>
      </li>)}
    </ul>
    {typeof data.status_scoring?.current_risk_findings === "number" && <p className="mt-2 text-xs text-white/70">Current-risk findings: {data.status_scoring.current_risk_findings.toLocaleString()}. Verified exclusions: {data.status_scoring.excluded_findings.toLocaleString()}. Recorded totals include excluded findings.</p>}
  </section>;
}

function EvidenceDashboard({ data }: { data: DashboardSummary }) {
  if (data.scoring_mode !== "evidence_qualified") return <div className="grid grid-cols-1 gap-3 md:grid-cols-2"><section className="min-w-0 space-y-3 rounded-xl border border-white/10 p-4 md:min-h-[10rem]">
    <h2 className="text-lg font-semibold">Evidence-based assessment is disabled</h2>
    <p className="text-sm text-white/70">An organization admin can enable evidence-qualified scoring in Settings. This tab does not enable it or start an evaluation.</p>
    <Link href="/settings" className="inline-block text-sm text-cyan underline">Open Settings</Link>
  </section><InventoryRiskSummary data={data} /></div>;
  const style = riskTierStyle(data.overall_score == null ? null : data.overall_tier);
  const domains = [...data.domains].sort((a, b) => DOMAIN_ORDER.indexOf(a.domain) - DOMAIN_ORDER.indexOf(b.domain));
  return <>
    <p className="text-sm text-white/60">Evidence-qualified scores require current, approved coverage. Inventory and finding counts do not establish that coverage.</p>
    {data.evaluation_state !== "current" && <p role="status" className="text-sm text-white/70">A current evidence evaluation is required. <Link href="/settings" className="text-cyan underline">Open Settings</Link> to review and evaluate evidence. Viewing this tab does not start evaluation.</p>}
    {data.overall_reason === "scope_mismatch" && <p role="status" className="text-sm text-white/70">Qualified domain scopes differ. An evidence-qualified overall score cannot be assigned.</p>}
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
    <section aria-label="Evidence-qualified assessment" className="min-w-0 rounded-xl bg-navy-cyan-gradient p-4 md:min-h-[10rem]">
      <h2 className="text-sm text-white/80">Evidence-qualified resilience assessment</h2>
      <p data-testid="evidence-overall-score" className={`mt-1 ${data.overall_score == null ? "text-2xl font-medium" : "text-4xl font-bold"} ${style.text}`}>
        {data.overall_score == null ? "Overall assessment: Not assessed" : Math.round(data.overall_score)}
      </p>
      {data.overall_score != null && <p className={`mt-1 text-sm ${style.text}`}>{data.overall_tier ? enumLabel(data.overall_tier) : "Unassigned"} risk tier</p>}
      <p className="mt-2 text-sm text-white/80">{data.qualified_domain_count ?? 0} of 7 domains qualified.</p>
      {data.qualification_evaluated_at && <p className="mt-1 text-xs text-white/70">Last evaluated: {formatDateTime(data.qualification_evaluated_at)}</p>}
    </section>
    <InventoryRiskSummary data={data} />
    </div>
    <section>
      <h2 className="mb-3 text-lg font-medium">Per-domain evidence-qualified scores</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {domains.map(domain => {
          const label = domain.assessment_status === "evidence_qualified" ? "Qualified" : domain.evidence_status === "conflicting" ? "Review required" : data.evaluation_state !== "current" ? "Evaluation required" : "Insufficient evidence";
          return <ScoreCard key={domain.domain} label={DOMAIN_LABELS[domain.domain]} score={domain.score} tier={domain.tier}
            unscoredLabel={domain.evidence_status === "conflicting" ? "Review required" : "Not assessed"} title={domain.justification}>
            <div className="mt-3 border-t border-white/10 pt-2 text-xs text-white/70">
              <p>Evidence coverage: {label}</p>
              <p>Evidence-qualified score: {domain.score == null ? "Not assessed" : `${Math.round(domain.score)}/100`}</p>
              {domain.evidence_reason && <p className="mt-1">Reason: {enumLabel(domain.evidence_reason)}</p>}
              {domain.qualification_scope && <p>Scope: {domain.qualification_scope}</p>}
              {domain.reviewed_at && <p>Reviewed: {formatDateTime(domain.reviewed_at)}</p>}
              {domain.expires_at && <p>Expires: {formatDateTime(domain.expires_at)}</p>}
            </div>
          </ScoreCard>;
        })}
      </div>
    </section>
  </>;
}

function DashboardSecuritySummary() {
  const { selectedOrg } = useApp();
  return <SecuritySummary key={selectedOrg!.id} orgId={selectedOrg!.id} />;
}
