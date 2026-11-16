"use client";
import type { MappingDecision } from "@/lib/controlCatalog";
import { formatDateTime } from "@/lib/domain";

export default function MappingDecisionView({ decision, title }: { decision: MappingDecision; title: string }) {
  return <section aria-label={title} className="min-w-0 space-y-2 rounded border border-white/15 p-4 [overflow-wrap:anywhere]">
    <h3 className="font-semibold">{title}</h3><p>{decision.catalog.framework} · {decision.catalog.edition} · Review version {decision.version}</p>
    <p className="text-xs text-white/65">{decision.actor_label} · {formatDateTime(decision.created_at)}</p>
    <p className="whitespace-pre-wrap">Rationale: {decision.rationale}</p>
    <ul className="space-y-2">{decision.controls.map(c => <li key={c.control_id}><p>{c.title}</p><p className="text-sm text-white/70">{c.description}</p></li>)}</ul>
    <details className="text-xs text-white/60"><summary>Catalog provenance</summary><p>{decision.catalog.source}</p><p>{decision.catalog.rights}</p><p>SHA256: {decision.catalog.content_hash}</p><p>Release ID: {decision.catalog.id}</p></details>
  </section>;
}
