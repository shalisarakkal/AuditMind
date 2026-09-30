"use client";

import { useState } from "react";

import PairRows, { type Choice, type Pair, inputClass, rowsToMap, selectClass } from "@/components/PairRows";
import { api } from "@/lib/apiClient";
import { ASSET_TYPE_LABELS, ASSET_TYPES, DOMAIN_LABELS, DOMAIN_ORDER, SEVERITY_ORDER } from "@/lib/domain";
import type { ImportProfile, ProfileParams, RiskyPort, Severity } from "@/lib/types";

const DOMAIN_CHOICES: Choice[] = DOMAIN_ORDER.map((d) => ({ value: d, label: DOMAIN_LABELS[d] }));
const TYPE_CHOICES: Choice[] = ASSET_TYPES.map((t) => ({ value: t, label: ASSET_TYPE_LABELS[t] }));
const SEVERITY_CHOICES: Choice[] = SEVERITY_ORDER.map((s) => ({ value: s, label: s.charAt(0).toUpperCase() + s.slice(1) }));

type Props = {
  orgId: string;
  profile: ImportProfile;
  onSaved(profile: ImportProfile): void;
  onCancel(): void;
};

type PortRow = { port: string; label: string; severity: Severity };

/** Edit one of the org's import profiles: name, the column for each field,
 * default values, the family's rule settings, and its own type names. */
export default function ImportProfileEditor({ orgId, profile, onSaved, onCancel }: Props) {
  const p = profile.params;
  const [name, setName] = useState(profile.name);
  const [columns, setColumns] = useState<Record<string, string>>(profile.column_map);
  const [defaults, setDefaults] = useState<Pair[]>(Object.entries(p.default_values));
  const [aliases, setAliases] = useState<Pair[]>(Object.entries(p.type_aliases));
  // Number settings are edited as text: blanks are caught on save, and the
  // server validates the numbers themselves.
  const [numbers, setNumbers] = useState<Record<string, string>>(
    Object.fromEntries(NUMBER_SETTINGS.filter(([key]) => key in p).map(([key]) => [key, String(p[key])])),
  );
  const [dayFirst, setDayFirst] = useState(Boolean(p.day_first_dates));
  const [keepOther, setKeepOther] = useState(Boolean(p.keep_other_columns));
  const [compliance, setCompliance] = useState<Pair[]>(Object.entries(p.compliance_severity ?? {}));
  // Lists of values are edited as comma-separated text.
  const [lists, setLists] = useState<Record<string, string>>(
    Object.fromEntries(LIST_SETTINGS.filter(([key]) => key in p).map(([key]) => [key, (p[key] as string[]).join(", ")])),
  );
  const [severities, setSeverities] = useState<Record<string, Severity>>(
    Object.fromEntries(SEVERITY_SETTINGS.filter(([key]) => key in p).map(([key]) => [key, p[key] as Severity])),
  );
  const [vulnDomains, setVulnDomains] = useState<Pair[]>(Object.entries(p.vulnerability_domains ?? {}));
  const [ports, setPorts] = useState<PortRow[]>(
    Object.entries(p.risky_ports ?? {}).map(([port, spec]) => ({ port, ...spec })),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const endpoint = profile.family === "endpoint_agent";
  const network = profile.family === "network_scan";
  const directory = profile.family === "directory";
  const fieldChoices: Choice[] = profile.fields.map((f) => ({ value: f.name, label: f.label }));

  function params(): ProfileParams {
    const result: ProfileParams = {
      default_values: rowsToMap(defaults),
      type_aliases: rowsToMap(aliases) as ProfileParams["type_aliases"],
      keep_other_columns: keepOther,
    };
    for (const [key] of NUMBER_SETTINGS) {
      if (key in numbers) Object.assign(result, { [key]: Number(numbers[key]) });
    }
    for (const [key] of LIST_SETTINGS) {
      if (key in lists) Object.assign(result, { [key]: lists[key].split(",").map((v) => v.trim()).filter(Boolean) });
    }
    Object.assign(result, severities);
    if (endpoint || directory) result.day_first_dates = dayFirst;
    if (endpoint) {
      result.compliance_severity = rowsToMap(compliance) as Record<string, Severity>;
    }
    if (network) {
      result.vulnerability_domains = rowsToMap(vulnDomains) as ProfileParams["vulnerability_domains"];
      result.risky_ports = Object.fromEntries(
        ports.filter((r) => r.port.trim()).map((r): [string, RiskyPort] => [r.port.trim(), { label: r.label.trim(), severity: r.severity }]),
      );
    }
    return result;
  }

  async function save() {
    const blank = NUMBER_SETTINGS.find(([key]) => key in numbers && numbers[key].trim() === "");
    if (blank) {
      setError(`${blank[1]} needs a number.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const columnMap = Object.fromEntries(
        Object.entries(columns).filter(([, header]) => header.trim()).map(([field, header]) => [field, header.trim()]),
      );
      onSaved(
        await api.patch<ImportProfile>(`/orgs/${orgId}/import-profiles/${profile.key}`, {
          name: name.trim(),
          column_map: columnMap,
          params: params(),
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label={`Edit ${profile.name}`} className="space-y-5 rounded-xl border border-cyan/30 bg-white/5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="profile-name" className="text-sm text-white/70">
          Name
        </label>
        <input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} className={`w-72 ${inputClass}`} />
        <span className="text-xs text-white/50">{profile.family_label}</span>
      </div>

      <Block
        title="Columns"
        help="The column header in your file for each field; list other names it may have with |, e.g. ResourceType|Type. Leave blank if the file doesn't have it."
      >
        <div className="grid gap-2 sm:grid-cols-2">
          {profile.fields.map((f) => (
            <label key={f.name} className="flex items-center justify-between gap-2 text-sm text-white/80">
              <span>
                {f.label}
                {f.detail && <span className="ml-1 text-xs text-white/40">(details)</span>}
              </span>
              <input
                aria-label={`Column for ${f.label}`}
                value={columns[f.name] ?? ""}
                onChange={(e) => setColumns({ ...columns, [f.name]: e.target.value })}
                className={`w-44 ${inputClass}`}
              />
            </label>
          ))}
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm text-white/80">
          <input type="checkbox" checked={keepOther} onChange={(e) => setKeepOther(e.target.checked)} />
          Keep the file&apos;s other columns in each asset&apos;s details
        </label>
      </Block>

      <Block title="Default values" help="Used when the file has no value for a field, e.g. Environment → production.">
        <PairRows
          rows={defaults}
          onChange={setDefaults}
          keyLabel="Default field"
          valueLabel="Default value"
          keyChoices={fieldChoices}
          newValue=""
          addLabel="+ Add default value"
        />
      </Block>

      {endpoint && (
        <Block title="Endpoint rules">
          <NumberInputs keys={["threats_high_at", "threats_critical_at", "stale_after_days"]} numbers={numbers} onChange={setNumbers} />
          <label className="mt-3 flex items-center gap-2 text-sm text-white/80">
            <input type="checkbox" checked={dayFirst} onChange={(e) => setDayFirst(e.target.checked)} />
            Dates are day first (03/04/2026 is 3 April)
          </label>
          <p className="mt-3 text-xs text-white/50">Compliance status → severity of a Compliance finding</p>
          <PairRows
            rows={compliance}
            onChange={setCompliance}
            keyLabel="Compliance status"
            valueLabel="Severity for compliance status"
            keyPlaceholder="e.g. non-compliant"
            valueChoices={SEVERITY_CHOICES}
            newValue="medium"
            addLabel="+ Add status"
          />
          <ListInput setting="compliant_values" lists={lists} onChange={setLists} />
        </Block>
      )}

      {directory && (
        <Block title="Directory rules" help="Account status and last login raise Identity & Access findings.">
          <NumberInputs keys={["stale_login_days"]} numbers={numbers} onChange={setNumbers} />
          <div className="mt-3 flex flex-wrap gap-4">
            {SEVERITY_SETTINGS.map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm text-white/80">
                {label}
                <select
                  aria-label={label}
                  value={severities[key] ?? "medium"}
                  onChange={(e) => setSeverities({ ...severities, [key]: e.target.value as Severity })}
                  className={selectClass}
                >
                  {SEVERITY_CHOICES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <ListInput setting="disabled_values" lists={lists} onChange={setLists} />
          <ListInput setting="ok_values" lists={lists} onChange={setLists} />
          <label className="mt-3 flex items-center gap-2 text-sm text-white/80">
            <input type="checkbox" checked={dayFirst} onChange={(e) => setDayFirst(e.target.checked)} />
            Dates are day first (03/04/2026 is 3 April)
          </label>
        </Block>
      )}

      {network && (
        <Block title="Network scan rules" help="Risk score (0–10) at or above each value sets the severity; below medium is low.">
          <NumberInputs keys={["risk_critical_at", "risk_high_at", "risk_medium_at"]} numbers={numbers} onChange={setNumbers} />
          <p className="mt-3 text-xs text-white/50">Vulnerabilities that belong to another domain (others: Vulnerability Mgmt)</p>
          <PairRows
            rows={vulnDomains}
            onChange={setVulnDomains}
            keyLabel="Vulnerability"
            valueLabel="Domain for vulnerability"
            keyPlaceholder="e.g. TLS1.0"
            valueChoices={DOMAIN_CHOICES}
            newValue="network_config"
            addLabel="+ Add vulnerability"
          />
          <ListInput setting="no_vulnerability_values" lists={lists} onChange={setLists} />
          <p className="mt-3 text-xs text-white/50">Risky open ports: each raises a Network &amp; Config finding</p>
          <div className="space-y-2">
            {ports.map((row, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <input
                  aria-label={`Port ${i + 1}`}
                  value={row.port}
                  onChange={(e) => setPorts(ports.map((r, j) => (j === i ? { ...r, port: e.target.value } : r)))}
                  className={`w-20 ${inputClass}`}
                />
                <input
                  aria-label={`Label for port ${i + 1}`}
                  value={row.label}
                  onChange={(e) => setPorts(ports.map((r, j) => (j === i ? { ...r, label: e.target.value } : r)))}
                  className={`w-32 ${inputClass}`}
                />
                <select
                  aria-label={`Severity for port ${i + 1}`}
                  value={row.severity}
                  onChange={(e) => setPorts(ports.map((r, j) => (j === i ? { ...r, severity: e.target.value as Severity } : r)))}
                  className={selectClass}
                >
                  {SEVERITY_CHOICES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  aria-label={`Remove port ${i + 1}`}
                  onClick={() => setPorts(ports.filter((_, j) => j !== i))}
                  className="px-2 text-xs text-white/60 hover:text-white"
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setPorts([...ports, { port: "", label: "", severity: "medium" }])}
              className="text-sm text-cyan hover:underline"
            >
              + Add port
            </button>
          </div>
        </Block>
      )}

      <Block title="Type names" help="This format's own names for asset types, on top of the organization's list.">
        <PairRows
          rows={aliases}
          onChange={setAliases}
          keyLabel="Format type name"
          valueLabel="Category for format type name"
          keyPlaceholder="e.g. Hypervisor"
          valueChoices={TYPE_CHOICES}
          newValue="server"
          addLabel="+ Add type name"
        />
      </Block>

      {error && <p className="text-sm text-red-300">{error}</p>}
      <div className="flex gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="rounded-md bg-cyan px-4 py-1.5 text-sm font-medium text-navy disabled:opacity-60"
        >
          Save profile
        </button>
        <button type="button" onClick={onCancel} className="text-sm text-white/60 hover:text-white">
          Cancel
        </button>
      </div>
    </section>
  );
}

const NUMBER_SETTINGS: [keyof ProfileParams, string][] = [
  ["threats_high_at", "Threats for a high finding"],
  ["threats_critical_at", "Threats for a critical finding"],
  ["stale_after_days", "Agent not reporting after (days)"],
  ["risk_critical_at", "Critical at risk score"],
  ["risk_high_at", "High at risk score"],
  ["risk_medium_at", "Medium at risk score"],
  ["stale_login_days", "Stale after no login for (days)"],
];

const LIST_SETTINGS: [keyof ProfileParams, string][] = [
  ["compliant_values", "Statuses that mean compliant"],
  ["no_vulnerability_values", "Values that mean no vulnerability"],
  ["disabled_values", "Statuses that mean disabled (a finding)"],
  ["ok_values", "Statuses that need no finding"],
];

const SEVERITY_SETTINGS: [keyof ProfileParams, string][] = [
  ["disabled_severity", "Disabled account severity"],
  ["stale_severity", "Stale account severity"],
];

/** A comma-separated list setting. */
function ListInput({
  setting,
  lists,
  onChange,
}: {
  setting: keyof ProfileParams;
  lists: Record<string, string>;
  onChange(lists: Record<string, string>): void;
}) {
  const label = LIST_SETTINGS.find(([key]) => key === setting)![1];
  return (
    <label className="mt-3 flex flex-wrap items-center gap-2 text-sm text-white/80">
      {label}
      <input
        aria-label={label}
        value={lists[setting] ?? ""}
        onChange={(e) => onChange({ ...lists, [setting]: e.target.value })}
        className={`w-72 ${inputClass}`}
      />
    </label>
  );
}

function NumberInputs({
  keys,
  numbers,
  onChange,
}: {
  keys: (keyof ProfileParams)[];
  numbers: Record<string, string>;
  onChange(numbers: Record<string, string>): void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {NUMBER_SETTINGS.filter(([key]) => keys.includes(key)).map(([key, label]) => (
        <label key={key} className="flex flex-col gap-1 text-xs text-white/60">
          {label}
          <input
            type="number"
            step="any"
            aria-label={label}
            value={numbers[key] ?? ""}
            onChange={(e) => onChange({ ...numbers, [key]: e.target.value })}
            className={inputClass}
          />
        </label>
      ))}
    </div>
  );
}

function Block({ title, help, children }: { title: string; help?: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-sm font-medium text-white">{title}</h4>
      {help && <p className="mb-2 text-xs text-white/50">{help}</p>}
      <div className={help ? "" : "mt-2"}>{children}</div>
    </div>
  );
}
