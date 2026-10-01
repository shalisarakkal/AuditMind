"use client";

import ImportProfilesPanel from "@/components/ImportProfilesPanel";
import Link from "next/link";

import IngestionSettingsPanel from "@/components/IngestionSettingsPanel";
import SecuritySettingsForm from "@/components/SecuritySettingsForm";
import { useApp } from "@/context/AppContext";

export default function SettingsPage() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-white">Settings</h1>
        <p className="mt-2 text-sm text-white/60">{org.name}</p>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-medium text-white">Ingestion</h2>
          <p className="text-sm text-white/60">
            How asset imports and findings uploads are handled for this organization, and how long archived items and
            Activity events are kept.
            Settings marked Default follow the server-wide configuration.
          </p>
        </div>
        <IngestionSettingsPanel orgId={org.id} isAdmin={org.role === "admin"} />
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-medium text-white">File formats</h2>
          <p className="text-sm text-white/60">
            How each kind of export is read: the column for each field and the rules that raise findings. To read your own
            tool&apos;s export, copy the closest format and adjust its columns and settings.
          </p>
        </div>
        <ImportProfilesPanel orgId={org.id} isAdmin={org.role === "admin"} />
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-medium text-white">Security</h2>
          <p className="text-sm text-white/60">
            How long a sign-in lasts, when an account locks, and the password rule. Settings marked Default follow the
            platform defaults set by the Sysadmin. Someone in several organizations gets the strictest of each.
          </p>
        </div>
        <SecuritySettingsForm path={`/orgs/${org.id}/security`} editable={org.role === "admin"} belowName="platform default" />
      </section>

      <section className="space-y-1">
        <h2 className="text-lg font-medium text-white">Purge log</h2>
        <p className="text-sm text-white/60">
          What was deleted for good (by an admin, or at the end of the retention period) is in Activity:{" "}
          <Link href="/activity?type=purge" className="text-cyan hover:underline">
            see purges
          </Link>
          .
        </p>
      </section>

      <section>
        <h2 className="text-lg font-medium text-white">Connectors &amp; AI</h2>
        <p className="mt-1 text-sm text-white/60">
          Connector configuration (cloud, SIEM, scanners) and Claude/RAG options arrive in a later phase.
        </p>
      </section>
    </div>
  );
}
