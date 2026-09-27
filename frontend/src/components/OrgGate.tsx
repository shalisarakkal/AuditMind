"use client";

import { useApp } from "@/context/AppContext";

/** Holds pages back until an org is selected, so they can rely on one. */
export default function OrgGate({ children }: { children: React.ReactNode }) {
  const { selectedOrg, orgsLoading, orgsError } = useApp();

  if (orgsError) return <p className="text-sm text-red-300">Couldn&apos;t load your organizations: {orgsError}</p>;
  if (!selectedOrg) {
    return (
      <p className="text-sm text-white/60">
        {orgsLoading ? "Loading…" : "You don't belong to any organization yet. Create one from the sidebar."}
      </p>
    );
  }
  // Remount pages on org switch so no state carries across orgs.
  return <div key={selectedOrg.id}>{children}</div>;
}
