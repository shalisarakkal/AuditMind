"use client";

import Link from "next/link";

import ScoreCard from "@/components/ScoreCard";
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
} from "@/lib/domain";
import { CriticalityBadge } from "@/components/ListPage";
import { eventLabel, eventSummary } from "@/lib/activity";
import type { ActivityEvent, DashboardSummary, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function DashboardPage() {
  const { selectedOrg } = useApp();
  const { data, error, loading } = useApi<DashboardSummary>(`/orgs/${selectedOrg!.id}/dashboard`);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-white">Resilience Dashboard</h1>
        <p className="mt-1 text-sm text-white/60">
          {selectedOrg!.name} — scores are calculated live from current findings.
        </p>
      </div>

      <StatusMessage loading={loading && !data} error={error} />
      {data && <Dashboard data={data} />}
    </div>
  );
}

function Dashboard({ data }: { data: DashboardSummary }) {
  const domains = [...data.domains].sort((a, b) => DOMAIN_ORDER.indexOf(a.domain) - DOMAIN_ORDER.indexOf(b.domain));
  const totalFindings = SEVERITY_ORDER.reduce((sum, s) => sum + data.findings_by_severity[s], 0);

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl bg-navy-cyan-gradient p-6 lg:col-span-2">
          <p className="text-sm text-white/80">Overall Resilience Score</p>
          <p className="mt-2 text-5xl font-bold text-white" data-testid="overall-score">
            {Math.round(data.overall_score)}
          </p>
          <p className="mt-1 text-sm uppercase tracking-wide text-white/80">{data.overall_tier} risk tier</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-6">
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
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {domains.map((d) => (
            <ScoreCard key={d.domain} label={DOMAIN_LABELS[d.domain]} score={d.score} tier={d.tier} title={d.justification} />
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
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

      <RecentActivity />
    </>
  );
}

const RECENT_EVENTS = 8;

/** The latest events, linked to Activity. */
function RecentActivity() {
  const { selectedOrg } = useApp();
  const { data } = useApi<Page<ActivityEvent>>(`/orgs/${selectedOrg!.id}/events?limit=${RECENT_EVENTS}`);
  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-medium text-white">Recent activity</h2>
        <Link href="/activity" className="text-sm text-cyan hover:underline">
          All activity
        </Link>
      </div>
      {data && data.items.length === 0 && <p className="text-sm text-white/60">Nothing has happened yet.</p>}
      {data && data.items.length > 0 && (
        <ul className="divide-y divide-white/10 rounded-xl border border-white/10 bg-white/5">
          {data.items.map((event) => (
            <li key={event.id} className="flex items-center justify-between gap-3 p-3 text-sm">
              <div className="min-w-0">
                <p className="truncate text-white">
                  {eventLabel(event)}
                  {event.item && <span className="text-white/70">: {event.item}</span>}
                </p>
                <p className="truncate text-xs text-white/50">
                  {event.actor_label} · {formatDateTime(event.started_at)}
                  {eventSummary(event) && ` · ${eventSummary(event)}`}
                </p>
              </div>
              <CriticalityBadge criticality={event.criticality} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
