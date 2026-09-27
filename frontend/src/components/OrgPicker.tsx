"use client";

import { useState } from "react";

import { useApp } from "@/context/AppContext";

const NEW_ORG = "__new__";

export default function OrgPicker() {
  const { orgs, selectedOrg, selectOrg, createOrg } = useApp();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createOrg(name.trim());
      setCreating(false);
      setName("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <label htmlFor="org-picker" className="block text-xs uppercase tracking-wide text-white/50">
        Organization
      </label>
      <select
        id="org-picker"
        value={creating ? NEW_ORG : (selectedOrg?.id ?? "")}
        onChange={(e) => {
          if (e.target.value === NEW_ORG) setCreating(true);
          else {
            setCreating(false);
            selectOrg(e.target.value);
          }
        }}
        className="w-full rounded-md border border-white/15 bg-navy px-2 py-1.5 text-sm text-white focus:border-cyan focus:outline-none"
      >
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.name}
          </option>
        ))}
        <option value={NEW_ORG}>+ New organization…</option>
      </select>
      {selectedOrg && !creating && (
        <p className="text-xs text-white/50">
          Your role: <span className="capitalize text-white/80">{selectedOrg.role}</span>
        </p>
      )}
      {creating && (
        <form onSubmit={handleCreate} className="space-y-2">
          <input
            aria-label="New organization name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Organization name"
            className="w-full rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none"
          />
          {error && <p className="text-xs text-red-300">{error}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="rounded-md bg-cyan px-2.5 py-1 text-xs font-medium text-navy disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create"}
            </button>
            <button
              type="button"
              onClick={() => {
                setCreating(false);
                setError(null);
              }}
              className="rounded-md px-2.5 py-1 text-xs text-white/70 hover:text-white"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
