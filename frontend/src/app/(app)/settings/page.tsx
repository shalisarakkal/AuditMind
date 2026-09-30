"use client";

import ImportProfilesPanel from "@/components/ImportProfilesPanel";
import IngestionSettingsPanel from "@/components/IngestionSettingsPanel";
import PurgeLogPanel from "@/components/PurgeLogPanel";
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
            How asset imports and findings uploads are handled for this organization, and how long archived items are kept.
            Settings marked Default follow the server-wide configuration.
          </p>
        </div>
        <IngestionSettingsPanel orgId={org.id} isAdmin={org.role === "admin"} />
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-medium text-white">Import profiles</h2>
          <p className="text-sm text-white/60">
            How each kind of export is read: the column for each field and the rules that raise findings. To read your own
            tool&apos;s export, copy the closest profile and adjust its columns and settings.
          </p>
        </div>
        <ImportProfilesPanel orgId={org.id} isAdmin={org.role === "admin"} />
      </section>

      {org.role === "admin" && (
        <section className="space-y-3">
          <div>
            <h2 className="text-lg font-medium text-white">Purge log</h2>
            <p className="text-sm text-white/60">
              Archived items deleted for good: purged by an admin, at the end of the retention period, or duplicates
              dropped when restoring.
            </p>
          </div>
          <PurgeLogPanel orgId={org.id} />
        </section>
      )}

      <section>
        <h2 className="text-lg font-medium text-white">Connectors &amp; AI</h2>
        <p className="mt-1 text-sm text-white/60">
          Connector configuration (cloud, SIEM, scanners) and Claude/RAG options arrive in a later phase.
        </p>
      </section>
    </div>
  );
}
