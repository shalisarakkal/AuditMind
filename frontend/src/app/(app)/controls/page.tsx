"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useApp } from "@/context/AppContext";
import ControlMappingWorkspace from "@/components/ControlMappingWorkspace";

function Workspace() {
  const { selectedOrg } = useApp();
  const search = useSearchParams();
  if (!selectedOrg) return <p>Select an organization to review mappings.</p>;
  return <ControlMappingWorkspace key={`${selectedOrg.id}:${search.get("finding_id") || ""}:${search.get("rule_id") || ""}`} orgId={selectedOrg.id} orgName={selectedOrg.name} role={selectedOrg.role} initialFindingId={search.get("finding_id") || ""} initialRuleId={search.get("rule_id") || ""} />;
}

export default function ControlsPage() {
  return <Suspense fallback={<p role="status">Loading control mappings…</p>}><Workspace /></Suspense>;
}
