"use client";

import { Suspense } from "react";

import EventLog from "@/components/EventLog";
import { useApp } from "@/context/AppContext";

// The list reads its sort and filters from the page address.
export default function ActivityPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Activity />
    </Suspense>
  );
}

function Activity() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  return (
    <EventLog
      base={`/orgs/${org.id}/events`}
      scope={org.id}
      scopeName={org.name}
      note="Uploads, archives, restores and purges, sign-ins, and changes to settings and people. Nothing here can be changed or deleted; old events are removed after the retention period set in Settings."
    />
  );
}

