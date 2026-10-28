"use client";

import Link from "next/link";
import { enumLabel } from "@/lib/presentation";

import ScoreCard from "@/components/ScoreCard";
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
import type { DashboardSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useDashboardState, type DashboardState } from "@/lib/useDashboardState";

export default function DashboardPage() {
  const { selectedOrg } = useApp();
  return <OrganizationDashboard key={selectedOrg!.id} orgId={selectedOrg!.id} orgName={selectedOrg!.name} />;
}

function OrganizationDashboard({ orgId, orgName }: { orgId: string; orgName: string }) {
  const { state, error } = useDashboardState(orgId);
  const identity = state ? `${orgId}:${state.settings_version}:${state.scoring_mode}:${state.scoring_mode === "evidence_qualified" ? `${state.evidence_revision}:${state.evaluation_id}` : "baseline"}` : null;

  return (
    <div className="min-w-0 space-y-8 [overflow-wrap:anywhere]">
      <div>
        <h1 className="text-2xl font-semibold text-white">Resilience dashboard</h1>
        <p className="mt-1 text-sm text-white/60">
          {orgName} — {!state ? "checking current scoring mode." : state.scoring_mode === "evidence_qualified" ? "scores require current reviewed evidence." : "findings-based baseline; not qualified evidence coverage."}
        </p>
      </div>

      <StatusMessage loading={!state && !error} error={error} />
      {state && identity && <CurrentDashboard key={identity} orgId={orgId} expected={state} />}
    </div>
  );
}

function CurrentDashboard({ orgId, expected }: { orgId: string; expected: DashboardState }) {
  const { data, error, loading } = useApi<DashboardSummary>(`/orgs/${orgId}/dashboard`);
  const matching = data && (data.scoring_mode ?? "findings_based") === expected.scoring_mode
    && (data.settings_version ?? 0) === expected.settings_version
    && (expected.scoring_mode !== "evidence_qualified" || (data.evidence_revision === expected.evidence_revision && (data.evaluation_id ?? null) === expected.evaluation_id));
  return <><StatusMessage loading={loading && !data} error={error} />
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

      <DashboardSecuritySummary />
    </>
  );
}

function DashboardSecuritySummary() {
  const { selectedOrg } = useApp();
  return <SecuritySummary key={selectedOrg!.id} orgId={selectedOrg!.id} />;
}
