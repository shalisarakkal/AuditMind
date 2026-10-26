"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useApp } from "@/context/AppContext";

export default function FindingLookupPage() {
  return <Suspense fallback={<p role="status">Loading finding reference…</p>}><Lookup /></Suspense>;
}

function Lookup() {
  const params = useSearchParams();
  const router = useRouter();
  const { orgs, orgsLoading, orgsError, selectedOrg, selectOrg } = useApp();
  const orgId = params.get("org");
  const findingId = params.get("finding_id");
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const valid = !!orgId && !!findingId && uuid.test(orgId) && uuid.test(findingId);
  const allowed = valid && orgs.some(org => org.id === orgId);
  useEffect(() => {
    if (!allowed || orgsLoading || orgsError) return;
    if (selectedOrg?.id !== orgId) selectOrg(orgId!);
    else router.replace(`/findings?${new URLSearchParams({ org: orgId!, finding_id: findingId! })}`);
  }, [allowed, orgsLoading, orgsError, selectedOrg?.id, orgId, findingId, selectOrg, router]);
  if (!valid) return <p role="alert">Invalid finding reference.</p>;
  if (orgsError) return <p role="alert">Could not verify organization access. Reload and try again.</p>;
  if (!orgsLoading && !allowed) return <p role="alert">This organization is unavailable or you do not have access.</p>;
  return <p role="status">Opening finding in its organization…</p>;
}
