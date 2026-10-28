"use client";

import { useApp } from "@/context/AppContext";
import type { MyOrganization } from "@/lib/types";

/** What the selected org lets the user do, under the picker. */
function access(org: MyOrganization): string {
  if (org.access === "sysadmin") return "Sysadmin: read-only";
  if (org.archived) return `Archived: read-only (your role: ${org.member_role ?? org.role})`;
  return `Your role: ${org.role}`;
}

export default function OrgPicker() {
  const { orgs, selectedOrg, selectOrg } = useApp();
  if (orgs.length === 0) return null;

  return (
    <div className="space-y-2">
      <label htmlFor="org-picker" className="block text-xs tracking-wide text-white/50">
        Organization
      </label>
      <select
        id="org-picker"
        value={selectedOrg?.id ?? ""}
        onChange={(e) => selectOrg(e.target.value)}
        className="w-full rounded-md border border-white/15 bg-navy px-2 py-1.5 text-sm text-white focus:border-cyan focus:outline-none"
      >
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.archived ? `${org.name} (archived)` : org.name}
          </option>
        ))}
      </select>
      {selectedOrg && <p className="text-xs text-white/50">{access(selectedOrg)}</p>}
    </div>
  );
}
