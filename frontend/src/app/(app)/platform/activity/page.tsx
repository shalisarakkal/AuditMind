"use client";

import { Suspense } from "react";

import EventLog from "@/components/EventLog";
import { SysadminOnly } from "@/components/SysadminOnly";

/** What the Sysadmin did (organizations, accounts, security defaults) and
 * the background worker: events of no one organization. */
export default function PlatformActivityPage() {
  return (
    <SysadminOnly>
      <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
        <EventLog
          base="/platform/events"
          scope="platform"
          scopeName="the platform"
          title="Platform activity"
          note="Organizations created, archived and purged; accounts renamed, reset, unlocked or deactivated; changes to the security defaults; the background worker. What happens inside an organization is in its own Activity."
        />
      </Suspense>
    </SysadminOnly>
  );
}
