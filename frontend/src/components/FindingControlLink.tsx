"use client";
import { useRouter } from "next/navigation";
import { useId } from "react";
import type { ControlMappingSummary } from "@/lib/controlCatalog";
import { ROW_ACTION_VIEW } from "./ListPage";

export default function FindingControlLink({ orgId, findingId, summary, disabled }: { orgId: string; findingId: string; summary?: ControlMappingSummary | null; disabled: boolean }) {
  const router = useRouter();
  const id = useId();
  const label = !summary ? "Not loaded" : !summary.available ? "Not available" : `${summary.status === "mapped" ? "Mapped" : "Unmapped"}${summary.proposal_pending ? " · Proposal pending" : ""}`;
  return <span className="inline-flex max-w-36 flex-col items-end gap-1"><button type="button" aria-describedby={id} disabled={disabled} title={disabled ? "Clear selection or wait for the current operation before using row actions." : "Review versioned category-to-control mappings"} className={`${ROW_ACTION_VIEW} disabled:opacity-50`} onClick={() => router.push(`/controls?org=${orgId}&finding_id=${findingId}`)}>Controls</button><span id={id} className="whitespace-normal text-right text-xs text-white/65">{label}</span></span>;
}
