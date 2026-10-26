"use client";

export type Pair = [string, string];
export type Choice = { value: string; label: string };

export const inputClass =
  "rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none disabled:opacity-60";
export const selectClass =
  "rounded-md border border-white/15 bg-navy px-2 py-1.5 text-sm text-white focus:border-cyan focus:outline-none disabled:opacity-60";

type PairRowsProps = {
  rows: Pair[];
  onChange(rows: Pair[]): void;
  /** Accessible names: "<keyLabel> 1", "<valueLabel> 1". */
  keyLabel: string;
  valueLabel: string;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  /** A select instead of a text box, for either side. */
  keyChoices?: Choice[];
  valueChoices?: Choice[];
  /** Value for a new row. */
  newValue: string;
  addLabel: string;
  disabled?: boolean;
  emptyText?: string;
};

/** Editable key -> value rows (a map as the user edits it: blank and
 * repeated keys are allowed while typing; the caller cleans up on save). */
export default function PairRows({
  rows,
  onChange,
  keyLabel,
  valueLabel,
  keyPlaceholder,
  valuePlaceholder,
  keyChoices,
  valueChoices,
  newValue,
  addLabel,
  disabled = false,
  emptyText,
}: PairRowsProps) {
  const set = (i: number, side: 0 | 1, value: string) =>
    onChange(rows.map((row, j) => (j === i ? ((side === 0 ? [value, row[1]] : [row[0], value]) as Pair) : row)));

  function field(i: number, side: 0 | 1) {
    const choices = side === 0 ? keyChoices : valueChoices;
    const label = `${side === 0 ? keyLabel : valueLabel} ${i + 1}`;
    const value = rows[i][side];
    if (choices) {
      return (
        <select aria-label={label} value={value} disabled={disabled} onChange={(e) => set(i, side, e.target.value)} className={`${selectClass} max-w-full`}>
          {choices.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        aria-label={label}
        value={value}
        disabled={disabled}
        placeholder={side === 0 ? keyPlaceholder : valuePlaceholder}
        onChange={(e) => set(i, side, e.target.value)}
        className={`min-w-0 flex-1 ${inputClass}`}
      />
    );
  }

  return (
    <div className="space-y-2">
      {rows.length === 0 && emptyText && <p className="text-sm text-white/50">{emptyText}</p>}
      {rows.map((_, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          {field(i, 0)}
          <span className="text-white/40">→</span>
          {field(i, 1)}
          {!disabled && (
            <button
              type="button"
              aria-label={`Remove ${keyLabel.toLowerCase()} ${i + 1}`}
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
              className="px-2 text-xs text-white/60 hover:text-white"
            >
              Remove
            </button>
          )}
        </div>
      ))}
      {!disabled && (
        <button
          type="button"
          onClick={() => onChange([...rows, [keyChoices?.[0]?.value ?? "", newValue]])}
          className="text-sm text-cyan hover:underline"
        >
          {addLabel}
        </button>
      )}
    </div>
  );
}

/** Rows -> map: trimmed keys, blank keys dropped, later rows win. */
export function rowsToMap(rows: Pair[]): Record<string, string> {
  return Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), v]));
}
