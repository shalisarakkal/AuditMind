"use client";

import { useState } from "react";

import ImportProfileEditor from "@/components/ImportProfileEditor";
import { inputClass } from "@/components/PairRows";
import { api } from "@/lib/apiClient";
import type { ImportProfile } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Props = { orgId: string; isAdmin: boolean };

/** The import profiles: built-ins (read-only) and this org's own copies,
 * which admins create by copying one and then adjust. */
export default function ImportProfilesPanel({ orgId, isAdmin }: Props) {
  const { data: profiles, error, loading, reload } = useApi<ImportProfile[]>(`/orgs/${orgId}/import-profiles`);
  const [copying, setCopying] = useState<{ from: ImportProfile; name: string } | null>(null);
  const [editing, setEditing] = useState<ImportProfile | null>(null);
  const [deleting, setDeleting] = useState<ImportProfile | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const createCopy = () =>
    run(async () => {
      const created = await api.post<ImportProfile>(`/orgs/${orgId}/import-profiles`, {
        name: copying!.name,
        copy_from: copying!.from.key,
      });
      setCopying(null);
      reload();
      setEditing(created);
    });

  const remove = () =>
    run(async () => {
      await api.delete(`/orgs/${orgId}/import-profiles/${deleting!.key}`);
      if (editing?.key === deleting!.key) setEditing(null);
      setDeleting(null);
      reload();
    });

  if (loading && !profiles) return <p className="text-sm text-white/60">Loading file formats…</p>;
  if (error) return <p className="text-sm text-red-300">{error}</p>;
  if (!profiles) return null;

  return (
    <div className="space-y-4">
      {!isAdmin && <p className="text-sm text-white/60">Only organization admins can change file formats.</p>}
      {actionError && <p className="text-sm text-red-300">{actionError}</p>}

      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-left text-sm">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/50">
            <tr>
              <th className="px-4 py-2">Format</th>
              <th className="px-4 py-2">Reads</th>
              <th className="px-4 py-2">Columns</th>
              {isAdmin && <th className="px-4 py-2" />}
            </tr>
          </thead>
          <tbody>
            {profiles.map((profile) => (
              <tr key={profile.key} className="border-t border-white/10 align-top text-white/80">
                <td className="px-4 py-2 text-white">
                  {profile.name}
                  {profile.builtin && <span className="ml-2 rounded bg-white/10 px-1.5 py-0.5 text-xs text-white/60">Built-in</span>}
                </td>
                <td className="px-4 py-2">{reads(profile)}</td>
                <td className="px-4 py-2 text-xs text-white/60">{Object.values(profile.column_map).join(", ")}</td>
                {isAdmin && (
                  <td className="whitespace-nowrap px-4 py-2 text-right">
                    <RowButton label={`Copy ${profile.name}`} onClick={() => setCopying({ from: profile, name: `${profile.name} (copy)` })}>
                      Copy
                    </RowButton>
                    {!profile.builtin && (
                      <>
                        <RowButton label={`Edit ${profile.name}`} onClick={() => setEditing(profile)}>
                          Edit
                        </RowButton>
                        <RowButton label={`Delete ${profile.name}`} onClick={() => setDeleting(profile)}>
                          Delete
                        </RowButton>
                      </>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {copying && (
        <div role="group" aria-label="Copy format" className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-white/5 p-3 text-sm">
          <span className="text-white/60">Copy {copying.from.name} as</span>
          <input
            aria-label="New format name"
            value={copying.name}
            onChange={(e) => setCopying({ ...copying, name: e.target.value })}
            className={`w-64 ${inputClass}`}
          />
          <button
            type="button"
            disabled={busy || !copying.name.trim()}
            onClick={() => void createCopy()}
            className="rounded-md bg-cyan px-3 py-1 font-medium text-navy disabled:opacity-60"
          >
            Create copy
          </button>
          <button type="button" onClick={() => setCopying(null)} className="text-xs text-white/60 hover:text-white">
            Cancel
          </button>
        </div>
      )}

      {deleting && (
        <div role="group" aria-label="Delete format" className="flex flex-wrap items-center gap-2 rounded-lg border border-red-400/30 bg-red-400/5 p-3 text-sm">
          <span className="text-white">Delete {deleting.name}? Past uploads keep their reports.</span>
          <button
            type="button"
            disabled={busy}
            onClick={() => void remove()}
            className="rounded-md bg-red-400/80 px-3 py-1 font-medium text-navy disabled:opacity-60"
          >
            Delete format
          </button>
          <button type="button" onClick={() => setDeleting(null)} className="text-xs text-white/60 hover:text-white">
            Cancel
          </button>
        </div>
      )}

      {editing && (
        <ImportProfileEditor
          key={editing.key}
          orgId={orgId}
          profile={editing}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function reads(profile: ImportProfile): string {
  if (profile.creates_assets && profile.creates_findings) return "Assets + findings";
  return profile.creates_assets ? "Assets" : "Findings";
}

function RowButton({ label, onClick, children }: { label: string; onClick(): void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} onClick={onClick} className="ml-3 text-xs text-cyan hover:underline">
      {children}
    </button>
  );
}
