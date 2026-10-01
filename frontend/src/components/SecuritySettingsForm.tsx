"use client";

import { useState } from "react";

import { api } from "@/lib/apiClient";
import type { SecuritySettings, SecuritySettingsLayer } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Key = keyof SecuritySettings;
type Field = {
  key: Key;
  label: string;
  /** The range, as the help text says it. */
  range?: string;
  kind: "number" | "rule" | "flag";
  min?: number;
  max?: number;
  /** 0 is allowed too, below `min` (never locks, until unlocked, never expires). */
  zero?: boolean;
  /** Only the Complex rule uses it. */
  complex?: boolean;
};

// The ranges are the backend's (services/security_policy.py), which checks
// them again.
const FIELDS: Field[] = [
  { key: "idle_minutes", label: "Signed out after idle (minutes)", range: "10 to 600", kind: "number", min: 10, max: 600 },
  { key: "max_session_days", label: "Longest sign-in (days)", range: "2 to 10", kind: "number", min: 2, max: 10 },
  { key: "lockout_threshold", label: "Failed sign-ins before locking", range: "3 to 6, or 0: never locks", kind: "number", min: 3, max: 6, zero: true },
  { key: "lockout_window_minutes", label: "Counted over (minutes)", range: "10 to 20", kind: "number", min: 10, max: 20 },
  { key: "lock_minutes", label: "Lock lasts (minutes)", range: "10 to 20, or 0: until an admin unlocks", kind: "number", min: 10, max: 20, zero: true },
  { key: "password_rule", label: "Password rule", kind: "rule" },
  { key: "min_length", label: "Minimum length", range: "12 to 64", kind: "number", min: 12, max: 64, complex: true },
  { key: "require_upper", label: "An upper-case letter", kind: "flag", complex: true },
  { key: "require_lower", label: "A lower-case letter", kind: "flag", complex: true },
  { key: "require_digit", label: "A digit", kind: "flag", complex: true },
  { key: "require_symbol", label: "A symbol", kind: "flag", complex: true },
  { key: "history_count", label: "Not one of the last … passwords", range: "0 to 24", kind: "number", min: 0, max: 24, complex: true },
  { key: "expiry_days", label: "Must be changed every (days)", range: "30 to 365, or 0: never", kind: "number", min: 30, max: 365, zero: true, complex: true },
];

const INPUT =
  "w-24 rounded-md border border-white/15 bg-navy px-2 py-1 text-sm text-white focus:border-cyan focus:outline-none disabled:opacity-60";

/** Why a value is out of range, or null if it's fine (the backend checks again). */
function problem(field: Field, value: SecuritySettings[Key]): string | null {
  if (field.kind !== "number") return null;
  const n = value as number;
  if (!Number.isInteger(n)) return "Enter a whole number";
  if (field.zero && n === 0) return null;
  if (n < field.min! || n > field.max!) return `Must be ${field.range}`;
  return null;
}

function show(field: Field, value: SecuritySettings[Key]): string {
  if (field.kind === "flag") return value ? "required" : "not required";
  if (field.kind === "rule") return value === "complex" ? "Complex" : "Simple";
  return String(value);
}

/** One layer of the security settings: the platform defaults (the
 * Sysadmin's) or an org's (its admins'). Each setting follows the layer
 * below ("Default") until changed; "Use default" goes back. */
export default function SecuritySettingsForm({
  path,
  editable,
  belowName,
}: {
  /** GET and PATCH here. */
  path: string;
  editable: boolean;
  /** What the layer below is called: "built-in", "platform default". */
  belowName: string;
}) {
  const { data, error, loading, reload } = useApi<SecuritySettingsLayer>(path);
  if (loading && !data) return <p className="text-sm text-white/60">Loading…</p>;
  if (error || !data) return <p className="text-sm text-red-300">{error ?? "Couldn't load the settings."}</p>;
  return <Form key={JSON.stringify(data)} layer={data} path={path} editable={editable} belowName={belowName} onSaved={reload} />;
}

function Form({
  layer,
  path,
  editable,
  belowName,
  onSaved,
}: {
  layer: SecuritySettingsLayer;
  path: string;
  editable: boolean;
  belowName: string;
  onSaved(): void;
}) {
  // This layer's own values; a setting left out follows the layer below.
  const [own, setOwn] = useState<Partial<SecuritySettings>>(() =>
    Object.fromEntries(layer.changed.map((key) => [key, layer.values[key]])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const value = <K extends Key>(key: K): SecuritySettings[K] => (key in own ? own[key] : layer.below[key]) as SecuritySettings[K];
  const set = (key: Key, next: SecuritySettings[Key] | undefined) => {
    setSaved(false);
    setError(null); // a refusal was about the values before this change
    setOwn((current) => {
      const copy = { ...current } as Record<string, unknown>;
      if (next === undefined) delete copy[key];
      else copy[key] = next;
      return copy as Partial<SecuritySettings>;
    });
  };

  // What to send: new or changed values, and null for each one dropped.
  const changes: Record<string, unknown> = {};
  for (const key of new Set<Key>([...layer.changed, ...(Object.keys(own) as Key[])])) {
    if (!(key in own)) changes[key] = null;
    else if (!layer.changed.includes(key) || own[key] !== layer.values[key]) changes[key] = own[key];
  }
  const dirty = Object.keys(changes).length > 0;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch(path, changes);
      setSaved(true);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const complex = value("password_rule") === "complex";
  const shown = FIELDS.filter((field) => !field.complex || complex);
  const problems = Object.fromEntries(shown.map((field) => [field.key, problem(field, value(field.key))]));
  const invalid = Object.values(problems).some(Boolean);
  return (
    <form onSubmit={save} aria-label="Security settings" className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-left text-sm">
          <tbody>
            {shown.map((field) => {
              const isOwn = field.key in own;
              const id = `security-${field.key}`;
              const fieldProblem = problems[field.key];
              return (
                <tr key={field.key} className="border-t border-white/10 first:border-t-0">
                  <td className={`px-4 py-2 ${field.complex ? "pl-8" : ""}`}>
                    <label htmlFor={id} className="text-white/80">
                      {field.label}
                    </label>
                    {field.range && <p className="text-xs text-white/40">{field.range}</p>}
                  </td>
                  <td className="px-4 py-2">
                    <Control
                      field={field}
                      id={id}
                      value={value(field.key)}
                      invalid={Boolean(fieldProblem)}
                      disabled={!editable}
                      onChange={(v) => set(field.key, v)}
                    />
                    {fieldProblem && (
                      <p id={`${id}-problem`} className="mt-1 text-xs text-red-300">
                        {fieldProblem}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {isOwn ? (
                      <span className="text-cyan">Changed</span>
                    ) : (
                      <span className="text-white/50">Default</span>
                    )}
                    {isOwn && (
                      <span className="text-white/40">
                        {" "}
                        ({belowName}: {show(field, layer.below[field.key])})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {editable && isOwn && (
                      <button type="button" onClick={() => set(field.key, undefined)} className="text-xs text-cyan hover:underline">
                        Use default
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editable && (
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={busy || !dirty || invalid}
            className="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save"}
          </button>
          {saved && !dirty && <span className="text-sm text-emerald-300">Saved</span>}
          {invalid && <span className="text-sm text-red-300">Fix the values marked in red to save.</span>}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
    </form>
  );
}

function Control({
  field,
  id,
  value,
  invalid,
  disabled,
  onChange,
}: {
  field: Field;
  id: string;
  value: SecuritySettings[Key];
  invalid: boolean;
  disabled: boolean;
  onChange(value: SecuritySettings[Key]): void;
}) {
  if (field.kind === "flag") {
    return (
      <input
        id={id}
        type="checkbox"
        checked={Boolean(value)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-cyan"
      />
    );
  }
  if (field.kind === "rule") {
    return (
      <select id={id} value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value as "simple" | "complex")} className={`${INPUT} w-auto`}>
        <option value="simple">Simple (length only)</option>
        <option value="complex">Complex</option>
      </select>
    );
  }
  return (
    <input
      id={id}
      type="number"
      min={field.zero ? 0 : field.min}
      max={field.max}
      // Emptied: NaN, shown empty and marked "Enter a whole number".
      value={Number.isNaN(value) ? "" : String(value)}
      disabled={disabled}
      aria-invalid={invalid}
      aria-describedby={invalid ? `${id}-problem` : undefined}
      onChange={(e) => onChange(e.target.value === "" ? Number.NaN : Number(e.target.value))}
      className={`${INPUT} ${invalid ? "border-red-400 focus:border-red-400" : ""}`}
    />
  );
}
