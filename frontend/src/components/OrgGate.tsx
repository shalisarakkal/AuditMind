"use client";

import { usePathname } from "next/navigation";

import { useApp } from "@/context/AppContext";
import { ACCOUNT_PATH, PLATFORM_PATH } from "@/lib/paths";

/** Pages that don't belong to an org: they work with none selected (a new
 * Sysadmin has none, nor does someone removed from their last org). */
function orgFree(path: string): boolean {
  return path === ACCOUNT_PATH || path === PLATFORM_PATH || path.startsWith(`${PLATFORM_PATH}/`);
}

/** Holds pages back until an org is selected, so they can rely on one. */
export default function OrgGate({ children }: { children: React.ReactNode }) {
  const { selectedOrg, orgsLoading, orgsError } = useApp();
  const path = usePathname() ?? "";

  if (orgFree(path)) return <>{children}</>;
  if (orgsError) return <p className="text-sm text-red-300">Couldn&apos;t load your organizations: {orgsError}</p>;
  if (!selectedOrg) {
    return (
      <p className="text-sm text-white/60">
        {orgsLoading ? "Loading…" : "You don't belong to any organization. Ask your administrator to add you."}
      </p>
    );
  }
  // Remount pages on org switch so no state carries across orgs.
  return (
    <div key={selectedOrg.id}>
      {selectedOrg.archived && (
        <p role="status" className="mb-6 rounded-lg border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm text-amber-100">
          {selectedOrg.name} is archived, so it&apos;s read-only. Only the Sysadmin can restore it.
        </p>
      )}
      {children}
    </div>
  );
}
