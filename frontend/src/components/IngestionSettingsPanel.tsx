"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/apiClient";
import { DOMAIN_LABELS, DOMAIN_ORDER } from "@/lib/domain";
import type { Domain, IngestionSettings } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Props = { orgId: string; isAdmin: boolean };

type Choice = { value: string; label: string };

const FIELDS: {
  key: "import_partial_success" | "asset_existing_strategy" | "nessus_info_severity" | "nessus_default_domain";
  label: string;
  help: string;
  choices: Choice[];
}[] = [
  {
    key: "import_partial_success",
    label: "Files with bad rows",
    help: "Whether one bad row rejects the whole file.",
    choices: [
      { value: "true", label: "Import the valid rows, report the rest" },
      { value: "false", label: "Reject the whole file" },
    ],
  },
  {
    key: "asset_existing_strategy",
    label: "Asset already in inventory",
    help: "Matched by hostname, else IP.",
    choices: [
      { value: "update", label: "Update it" },
      { value: "skip", label: "Leave it unchanged" },
      { value: "duplicate", label: "Add a duplicate" },
    ],
  },
  {
    key: "nessus_info_severity",
    label: "Nessus Info items",
    help: "Severity 0 findings in .nessus files.",
    choices: [
      { value: "skip", label: "Skip them" },
      { value: "low", label: "Record as low" },
    ],
  },
  {
    key: "nessus_default_domain",
    label: "Nessus default domain",
    help: "For plugin families with no mapping.",
    choices: DOMAIN_ORDER.map((d) => ({ value: d, label: DOMAIN_LABELS[d] })),
  },
];

const selectClass =
  "rounded-md border border-white/15 bg-navy px-2 py-1.5 text-sm text-white focus:border-cyan focus:outline-none disabled:opacity-60";

export default function IngestionSettingsPanel({ orgId, isAdmin }: Props) {
  const { data, error, loading } = useApi<IngestionSettings>(`/orgs/${orgId}/settings`);
  const [settings, setSettings] = useState<IngestionSettings | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => setSettings(data), [data]);

  async function save(changes: Partial<Record<string, unknown>>) {
    setSaving(true);
    setSaveError(null);
    try {
      setSettings(await api.patch<IngestionSettings>(`/orgs/${orgId}/settings`, changes));
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (loading && !settings) return <p className="text-sm text-white/60">Loading settings…</p>;
  if (error) return <p className="text-sm text-red-300">{error}</p>;
  if (!settings) return null;

  return (
    <div className="space-y-6">
      {!isAdmin && (
        <p className="text-sm text-white/60">Only organization admins can change these settings.</p>
      )}
      {saveError && <p className="text-sm text-red-300">{saveError}</p>}

      <div className="divide-y divide-white/10 rounded-xl border border-white/10 bg-white/5">
        {FIELDS.map((field) => {
          const overridden = settings.overridden.includes(field.key);
          return (
            <div key={field.key} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <label htmlFor={field.key} className="text-sm font-medium text-white">
                  {field.label}
                </label>
                <p className="text-xs text-white/50">{field.help}</p>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`rounded px-2 py-0.5 text-xs ${overridden ? "bg-cyan/15 text-cyan" : "bg-white/10 text-white/60"}`}
                >
                  {overridden ? "Override" : "Default"}
                </span>
                <select
                  id={field.key}
                  value={String(settings[field.key])}
                  disabled={!isAdmin || saving}
                  onChange={(e) =>
                    save({
                      [field.key]: field.key === "import_partial_success" ? e.target.value === "true" : e.target.value,
                    })
                  }
                  className={selectClass}
                >
                  {field.choices.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                {isAdmin && overridden && (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => save({ [field.key]: null })}
                    className="text-xs text-white/60 hover:text-white"
                  >
                    Reset to default
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <DomainMapEditor settings={settings} isAdmin={isAdmin} saving={saving} onSave={save} />
    </div>
  );
}

function DomainMapEditor({
  settings,
  isAdmin,
  saving,
  onSave,
}: {
  settings: IngestionSettings;
  isAdmin: boolean;
  saving: boolean;
  onSave(changes: Record<string, unknown>): Promise<void>;
}) {
  const [rows, setRows] = useState<[string, Domain][]>([]);
  useEffect(() => setRows(Object.entries(settings.nessus_domain_map_override)), [settings.nessus_domain_map_override]);

  const inherited = Object.entries(settings.nessus_domain_map).filter(
    ([family]) => !(family in settings.nessus_domain_map_override),
  );
  const cleaned = rows.filter(([family]) => family.trim());

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h3 className="text-sm font-medium text-white">Nessus plugin family → domain</h3>
      <p className="mt-1 text-xs text-white/50">
        Families not listed go to the default domain above. This organization&apos;s own mappings take precedence.
      </p>

      <div className="mt-4 space-y-2">
        <p className="text-xs uppercase tracking-wide text-white/50">This organization</p>
        {rows.length === 0 && <p className="text-sm text-white/50">No custom mappings.</p>}
        {rows.map(([family, domain], i) => (
          <div key={i} className="flex flex-wrap gap-2">
            <input
              aria-label={`Plugin family ${i + 1}`}
              value={family}
              disabled={!isAdmin}
              onChange={(e) => setRows(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))}
              placeholder="e.g. Web Servers"
              className="flex-1 rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none"
            />
            <select
              aria-label={`Domain for plugin family ${i + 1}`}
              value={domain}
              disabled={!isAdmin}
              onChange={(e) => setRows(rows.map((r, j) => (j === i ? [r[0], e.target.value as Domain] : r)))}
              className={selectClass}
            >
              {DOMAIN_ORDER.map((d) => (
                <option key={d} value={d}>
                  {DOMAIN_LABELS[d]}
                </option>
              ))}
            </select>
            {isAdmin && (
              <button
                type="button"
                onClick={() => setRows(rows.filter((_, j) => j !== i))}
                className="px-2 text-xs text-white/60 hover:text-white"
              >
                Remove
              </button>
            )}
          </div>
        ))}
        {isAdmin && (
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={() => setRows([...rows, ["", settings.nessus_default_domain]])}
              className="text-sm text-cyan hover:underline"
            >
              + Add mapping
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() =>
                onSave({ nessus_domain_map: cleaned.length ? Object.fromEntries(cleaned.map(([f, d]) => [f.trim(), d])) : null })
              }
              className="rounded-md bg-cyan px-3 py-1 text-sm font-medium text-navy disabled:opacity-60"
            >
              Save mappings
            </button>
          </div>
        )}
      </div>

      <div className="mt-5">
        <p className="text-xs uppercase tracking-wide text-white/50">Inherited (built-in and server defaults)</p>
        <ul className="mt-2 grid gap-1 text-sm text-white/70 sm:grid-cols-2">
          {inherited.map(([family, domain]) => (
            <li key={family}>
              {family} → {DOMAIN_LABELS[domain]}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
