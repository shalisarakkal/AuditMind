"use client";

// The building blocks every list page uses, so they all look and behave the
// same (docs/UI_CONVENTIONS.md): the header with its count, the toolbar with
// the search box, the table's frame, badges, row actions and the empty row.

import { useEffect, useRef } from "react";

import { TextFilter } from "@/components/ListControls";
import type { Criticality } from "@/lib/types";
import type { ListState } from "@/lib/useListState";
import type { Selection } from "@/lib/useSelection";

/** Title; "12,674 findings in Acme" (or "12 findings match" when filtered);
 * an optional one-line note; the page's main action on the right. */
export function PageHeader({
  title,
  total,
  noun,
  orgName,
  filtered = false,
  note,
  action,
}: {
  title: string;
  /** Undefined while loading. */
  total: number | undefined;
  /** Plural, e.g. "findings". */
  noun: string;
  orgName: string;
  filtered?: boolean;
  note?: React.ReactNode;
  action?: React.ReactNode;
}) {
  // "1 upload", "2 uploads" (every noun here is a plain plural).
  const count = total === undefined ? "" : `${total.toLocaleString("en-US")} ${total === 1 ? noun.replace(/s$/, "") : noun}`;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">{title}</h1>
          <p className="mt-1 text-sm text-white/60">
            {total === undefined ? orgName : filtered ? `${count} ${total === 1 ? "matches" : "match"}` : `${count} in ${orgName}`}
          </p>
        </div>
        {action}
      </div>
      {note && <p className="max-w-4xl text-xs text-white/50">{note}</p>}
    </div>
  );
}

const SEARCH =
  "w-full max-w-sm rounded-md border border-white/15 bg-navy px-3 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none";

/** "Search all columns", anything else the page filters by outside the
 * table (e.g. a date range), and Clear filters when any are set. */
export function ListToolbar({ list, label, children }: { list: ListState; label: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <TextFilter name="q" label="search" list={list} ariaLabel={`Search ${label}`} placeholder="Search all columns" className={SEARCH} />
      {children}
      {list.hasFilters && (
        <button type="button" onClick={list.clearFilters} className="text-sm text-cyan hover:underline">
          Clear filters
        </button>
      )}
    </div>
  );
}

/** The table's frame and header styles. */
export function ListTable({ children, fixed = false }: { children: React.ReactNode; fixed?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-white/10">
      <table className={`w-full text-left text-sm ${fixed ? "table-fixed" : ""}`}>{children}</table>
    </div>
  );
}

export const THEAD = "bg-white/5 text-xs uppercase tracking-wide text-white/50";
export const ROW = "border-t border-white/10 text-white/80";
/** A header cell with no sort (a column that isn't sortable, or actions). */
export const TH = "px-4 py-2";
/** A filter-row cell under the headers. */
export const FILTER_CELL = "px-4 pb-2";
export const TD = "px-4 py-2";

/** "No findings yet." or, filtered, "No findings match." across the table. */
export function EmptyRow({ colSpan, noun, filtered }: { colSpan: number; noun: string; filtered: boolean }) {
  return (
    <tr className="border-t border-white/10">
      <td colSpan={colSpan} className="px-4 py-6 text-center text-white/60">
        {filtered ? `No ${noun} match.` : `No ${noun} yet.`}
      </td>
    </tr>
  );
}

/** Statuses of imports, jobs and events, all in the same colours. */
const STATUS_BADGES: Record<string, string> = {
  completed: "bg-emerald-400/15 text-emerald-300",
  failed: "bg-red-400/15 text-red-300",
  stopped: "bg-red-400/15 text-red-300",
  running: "bg-cyan/15 text-cyan",
  pending: "bg-white/10 text-white/70",
};

export function StatusBadge({ status, label = status }: { status: string; label?: string }) {
  return <Badge className={STATUS_BADGES[status] ?? STATUS_BADGES.pending}>{label}</Badge>;
}

const CRITICALITY_BADGES: Record<Criticality, string> = {
  critical: "bg-red-400/15 text-red-300",
  warning: "bg-yellow-400/15 text-yellow-200",
  info: "bg-white/10 text-white/70",
};

export function CriticalityBadge({ criticality }: { criticality: Criticality }) {
  return <Badge className={CRITICALITY_BADGES[criticality]}>{criticality}</Badge>;
}

export function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return <span className={`rounded px-2 py-0.5 text-xs capitalize ${className}`}>{children}</span>;
}

/** Row actions: right-aligned text buttons; red for what can't be undone. */
export const ROW_ACTION = "text-xs text-cyan hover:underline";
/** Only shows something (Report, Details): white, always underlined, so it
 * reads as a link rather than cell text, and stays apart from the cyan of
 * what changes data. */
export const ROW_ACTION_VIEW =
  "text-xs text-white underline decoration-white/40 underline-offset-2 hover:decoration-white";
export const ROW_ACTION_DANGER = "text-xs text-red-300 hover:underline";
export const ACTIONS_CELL = "whitespace-nowrap px-4 py-2 text-right space-x-3";

const DATE_INPUT =
  "rounded-md border border-white/15 bg-navy px-2 py-1.5 text-sm text-white focus:border-cyan focus:outline-none [color-scheme:dark]";

/** From/To on the list's date column (the API's since/until), for the
 * toolbar. `label` names the column, e.g. "Uploaded". */
export function DateRangeFilter({ list, label }: { list: ListState; label: string }) {
  return (
    <div role="group" aria-label={`${label} between`} className="flex items-center gap-2 text-sm text-white/60">
      <span>{label}</span>
      <input
        type="date"
        aria-label={`${label} from`}
        value={list.text("since")}
        onChange={(e) => list.setText("since", e.target.value)}
        className={DATE_INPUT}
      />
      <span>to</span>
      <input
        type="date"
        aria-label={`${label} to`}
        value={list.text("until")}
        onChange={(e) => list.setText("until", e.target.value)}
        className={DATE_INPUT}
      />
    </div>
  );
}

/** Chips over the list that pre-filter one pick-list column (`name`): "All"
 * first, then each value with how many match the other filters. */
export function FilterChips<V extends string>({
  list,
  name,
  label,
  options,
  counts,
}: {
  list: ListState;
  name: string;
  label: string;
  options: { value: V; label: string }[];
  counts?: Partial<Record<V, number>>;
}) {
  const chosen = list.values(name);
  const all = counts && Object.values<number | undefined>(counts).reduce<number>((sum, n) => sum + (n ?? 0), 0);
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      <Chip label="All" count={all} active={chosen.length === 0} onClick={() => list.setValues(name, [])} />
      {options
        .filter((o) => !counts || counts[o.value] || chosen.includes(o.value))
        .map((o) => (
          <Chip
            key={o.value}
            label={o.label}
            count={counts ? counts[o.value] ?? 0 : undefined}
            active={chosen.includes(o.value)}
            onClick={() => list.setValues(name, [o.value])}
          />
        ))}
    </div>
  );
}

function Chip({ label, count, active, onClick }: { label: string; count?: number; active: boolean; onClick(): void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
        active ? "border-cyan bg-cyan/10 text-cyan" : "border-white/15 text-white/70 hover:border-cyan hover:text-cyan"
      }`}
    >
      {label}{count !== undefined && ` (${count.toLocaleString("en-US")})`}
    </button>
  );
}

const CHECKBOX = "h-4 w-4 accent-cyan disabled:opacity-30";
/** The checkbox column, first in the table. */
export const SELECT_CELL = "w-10 px-4 py-2";

/** The header checkbox: pick, or drop, every row on this page that can be
 * picked (`rows`); shown half-ticked when some are. */
export function SelectPageBox({ selection, rows }: { selection: Selection; rows: { id: string; name: string }[] }) {
  const picked = rows.filter((row) => selection.has(row.id)).length;
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (box.current) box.current.indeterminate = picked > 0 && picked < rows.length;
  });
  return (
    <input
      ref={box}
      type="checkbox"
      aria-label="Select all on this page"
      disabled={rows.length === 0}
      checked={rows.length > 0 && picked === rows.length}
      onChange={(e) => selection.set(rows, e.target.checked)}
      className={CHECKBOX}
    />
  );
}

/** A row's checkbox; `disabled` when the row can't take the action now
 * (e.g. a job is already running on it). */
export function SelectBox({ selection, id, name, disabled = false }: { selection: Selection; id: string; name: string; disabled?: boolean }) {
  return (
    <input
      type="checkbox"
      aria-label={`Select ${name}`}
      checked={selection.has(id)}
      disabled={disabled || (selection.full && !selection.has(id))}
      onChange={(e) => selection.set([{ id, name }], e.target.checked)}
      className={CHECKBOX}
    />
  );
}

/** "12 selected", the actions on them, and Clear selection: shown while
 * anything is picked, on any page of the list. */
export function SelectionBar({ selection, children }: { selection: Selection; children: React.ReactNode }) {
  if (selection.count === 0) return null;
  return (
    <div role="group" aria-label="Selected" className="flex flex-wrap items-center gap-3 rounded-lg border border-cyan/30 bg-cyan/5 px-3 py-2 text-sm">
      <span className="text-white">
        {selection.count.toLocaleString("en-US")} selected
        {selection.full && <span className="text-white/60"> (the most at once)</span>}
      </span>
      {children}
      <button type="button" onClick={selection.clear} className="text-xs text-white/60 hover:text-white">
        Clear selection
      </button>
    </div>
  );
}

/** A button in the SelectionBar; red for what can't be undone. */
export function SelectionAction({ onClick, danger = false, disabled = false, children }: { onClick(): void; danger?: boolean; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-1 text-sm font-medium text-navy hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 ${danger ? "bg-red-400/80" : "bg-cyan"}`}
    >
      {children}
    </button>
  );
}
