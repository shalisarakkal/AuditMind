"use client";

import Link from "next/link";
import StatusMessage from "./StatusMessage";
import { useApi } from "@/lib/useApi";

type Summary = { window_start: string; window_end: string; counts: Record<string, number> };
const cards = [{ type: "member_added", label: "Members added" },
  { type: "role_changed", label: "Role changes" }, { type: "purge", label: "Completed purges" }];

export default function SecuritySummary({ orgId }: { orgId: string }) {
  const { data, loading, error, reload } = useApi<Summary>(`/orgs/${orgId}/dashboard/security-summary`);
  return <section aria-label="Security summary" className="space-y-3">
    <div className="flex flex-wrap items-baseline justify-between gap-3">
      <h2 className="text-lg font-medium text-white">Security summary · Last 7 days</h2>
      <Link href="/activity" className="text-sm text-cyan hover:underline">All activity</Link>
    </div>
    <p className="text-xs text-white/60">Completed organization actions started in the rolling seven-day period. Purges count operations, not deleted records.</p>
    <StatusMessage loading={loading && !data} error={error} />
    {error && <button type="button" onClick={reload} className="text-sm text-cyan underline">Retry security summary</button>}
    {data && <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">{cards.map(card => {
      const query = new URLSearchParams({ org: orgId, type: card.type, result: "completed", window_start: data.window_start, window_end: data.window_end });
      return <Link key={card.type} aria-label={`${card.label} ${data.counts[card.type].toLocaleString()}`} href={`/activity?${query}`} className="rounded-xl border border-white/10 bg-white/5 p-4 hover:border-cyan focus:outline-none focus:ring-2 focus:ring-cyan">
        <span className="block text-sm text-white/70">{card.label}</span>
        <span className="block text-2xl font-semibold text-white">{data.counts[card.type].toLocaleString()}</span>
      </Link>;
    })}</div>}
    <p className="text-xs text-white/60">Failed sign-ins are not summarized here: organization attribution is not guaranteed. Routine sign-ins and worker events remain in Activity.</p>
  </section>;
}
