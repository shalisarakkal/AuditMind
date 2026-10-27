"use client";
import { useApp } from "@/context/AppContext";
import { OrganizationIdentity } from "./OrganizationLogo";

export default function ApplicationHeader() {
  const { selectedOrg } = useApp();
  return <header className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
    {selectedOrg ? <OrganizationIdentity key={selectedOrg.id} orgId={selectedOrg.id} name={selectedOrg.name} /> : <span className="text-sm text-white/70">Platform</span>}
  </header>;
}
