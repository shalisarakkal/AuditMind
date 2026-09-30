"use client";

import { useEffect, useState } from "react";

import PairRows, { type Choice, type Pair, rowsToMap, selectClass } from "@/components/PairRows";
import { api } from "@/lib/apiClient";
import { ASSET_TYPE_LABELS, ASSET_TYPES, DOMAIN_LABELS, DOMAIN_ORDER } from "@/lib/domain";
import type { IngestionSettings } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Props = { orgId: string; isAdmin: boolean };

const DOMAIN_CHOICES: Choice[] = DOMAIN_ORDER.map((d) => ({ value: d, label: DOMAIN_LABELS[d] }));
const TYPE_CHOICES: Choice[] = ASSET_TYPES.map((t) => ({ value: t, label: ASSET_TYPE_LABELS[t] }));

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
    choices: DOMAIN_CHOICES,
  },
];

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
        <RetentionField
          days={settings.archive_retention_days}
          overridden={settings.overridden.includes("archive_retention_days")}
          isAdmin={isAdmin}
          saving={saving}
          onSave={(days) => save({ archive_retention_days: days })}
        />
      </div>

      <MapEditor
        title="Nessus plugin family → domain"
        help="Families not listed go to the default domain above. This organization's own mappings take precedence."
        own={settings.nessus_domain_map_override}
        effective={settings.nessus_domain_map}
        choices={DOMAIN_CHOICES}
        newValue={settings.nessus_default_domain}
        keyLabel="Plugin family"
        valueLabel="Domain for plugin family"
        keyPlaceholder="e.g. Web Servers"
        emptyText="No custom mappings."
        addLabel="+ Add mapping"
        saveLabel="Save mappings"
        onSave={(map) => save({ nessus_domain_map: map })}
        isAdmin={isAdmin}
        saving={saving}
      />
      <MapEditor
        title="Asset type names"
        help="Names that imports and new assets may use for a type, e.g. laptop → Workstation. The name is kept as the asset's subtype."
        own={settings.asset_type_aliases_override}
        effective={settings.asset_type_aliases}
        choices={TYPE_CHOICES}
        newValue="server"
        keyLabel="Type name"
        valueLabel="Category for type name"
        keyPlaceholder="e.g. hypervisor"
        emptyText="No names of its own."
        addLabel="+ Add type name"
        saveLabel="Save type names"
        onSave={(map) => save({ asset_type_aliases: map })}
        isAdmin={isAdmin}
        saving={saving}
      />
    </div>
  );
}

/** How long archived items are kept: a number of days, saved on demand. */
function RetentionField({
  days,
  overridden,
  isAdmin,
  saving,
  onSave,
}: {
  days: number;
  overridden: boolean;
  isAdmin: boolean;
  saving: boolean;
  /** null: back to the server default. */
  onSave(days: number | null): void;
}) {
  const [value, setValue] = useState(String(days));
  useEffect(() => setValue(String(days)), [days]);
  const parsed = Number(value);
  const valid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 3650;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-4">
      <div>
        <label htmlFor="archive_retention_days" className="text-sm font-medium text-white">
          Keep archived items for
        </label>
        <p className="text-xs text-white/50">Days before an archived upload, asset or finding is purged for good.</p>
      </div>
      <div className="flex items-center gap-3">
        <span className={`rounded px-2 py-0.5 text-xs ${overridden ? "bg-cyan/15 text-cyan" : "bg-white/10 text-white/60"}`}>
          {overridden ? "Override" : "Default"}
        </span>
        <input
          id="archive_retention_days"
          type="number"
          min={1}
          max={3650}
          value={value}
          disabled={!isAdmin || saving}
          onChange={(e) => setValue(e.target.value)}
          className={`w-24 ${selectClass}`}
        />
        <span className="text-sm text-white/60">days</span>
        {isAdmin && value !== String(days) && (
          <button
            type="button"
            disabled={saving || !valid}
            onClick={() => onSave(parsed)}
            className="rounded-md bg-cyan px-3 py-1 text-sm font-medium text-navy disabled:opacity-60"
          >
            Save
          </button>
        )}
        {isAdmin && overridden && (
          <button type="button" disabled={saving} onClick={() => onSave(null)} className="text-xs text-white/60 hover:text-white">
            Reset to default
          </button>
        )}
      </div>
    </div>
  );
}

type MapEditorProps = {
  title: string;
  help: string;
  /** The org's own entries (what an admin edits). */
  own: Record<string, string>;
  /** Everything in effect; entries not in `own` are shown as inherited. */
  effective: Record<string, string>;
  choices: Choice[];
  newValue: string;
  keyLabel: string;
  valueLabel: string;
  keyPlaceholder: string;
  emptyText: string;
  addLabel: string;
  saveLabel: string;
  /** Saves the org's entries; null when there are none (clears the override). */
  onSave(map: Record<string, string> | null): Promise<void>;
  isAdmin: boolean;
  saving: boolean;
};

/** A map setting layered built-in -> server -> org: the org's own entries
 * are editable, the rest are listed as inherited. */
function MapEditor(props: MapEditorProps) {
  const { own, effective, choices, isAdmin, saving } = props;
  const [rows, setRows] = useState<Pair[]>([]);
  useEffect(() => setRows(Object.entries(own)), [own]);

  const label = (value: string) => choices.find((c) => c.value === value)?.label ?? value;
  const inherited = Object.entries(effective).filter(([key]) => !(key in own));
  const cleaned = rowsToMap(rows);

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h3 className="text-sm font-medium text-white">{props.title}</h3>
      <p className="mt-1 text-xs text-white/50">{props.help}</p>

      <div className="mt-4 space-y-2">
        <p className="text-xs uppercase tracking-wide text-white/50">This organization</p>
        <PairRows
          rows={rows}
          onChange={setRows}
          keyLabel={props.keyLabel}
          valueLabel={props.valueLabel}
          keyPlaceholder={props.keyPlaceholder}
          valueChoices={choices}
          newValue={props.newValue}
          addLabel={props.addLabel}
          disabled={!isAdmin}
          emptyText={props.emptyText}
        />
        {isAdmin && (
          <button
            type="button"
            disabled={saving}
            onClick={() => props.onSave(Object.keys(cleaned).length ? cleaned : null)}
            className="rounded-md bg-cyan px-3 py-1 text-sm font-medium text-navy disabled:opacity-60"
          >
            {props.saveLabel}
          </button>
        )}
      </div>

      <div className="mt-5">
        <p className="text-xs uppercase tracking-wide text-white/50">Inherited (built-in and server defaults)</p>
        <ul className="mt-2 grid max-h-48 gap-1 overflow-auto text-sm text-white/70 sm:grid-cols-2">
          {inherited.map(([key, value]) => (
            <li key={key}>
              {key} → {label(value)}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
