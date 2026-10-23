"use client";

import { useEffect, useRef, useState } from "react";

import type { ListState, SortOrder } from "@/lib/useListState";
import { useDebounced } from "@/lib/useDebounced";

/** A column header that sorts: ascending, then descending, then back to the
 * list's default order. `defaultSort` is the column the default order sorts
 * by, if it's a shown column, and `defaultOrder` its direction (a list of
 * newest first: "desc"). */
export function SortHeader({
  label,
  column,
  list,
  defaultSort,
  defaultOrder = "asc",
  className = "",
}: {
  label: string;
  column: string;
  list: ListState;
  defaultSort?: string;
  defaultOrder?: SortOrder;
  className?: string;
}) {
  const sort = list.sort ?? defaultSort;
  const order = list.sort ? list.order : defaultOrder;
  const active = sort === column;
  const next = () => {
    if (!active) list.setSort(column, "asc");
    // The default order's column: the other way round.
    else if (!list.sort) list.setSort(column, order === "asc" ? "desc" : "asc");
    else if (order === "asc") list.setSort(column, "desc");
    else list.setSort(null);
  };
  return (
    <th aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"} className={`px-4 py-2 ${className}`}>
      <button
        type="button"
        onClick={next}
        className={`inline-flex items-center gap-1 uppercase tracking-wide hover:text-cyan ${active ? "text-cyan" : ""}`}
      >
        {label}
        <span aria-hidden className="text-[10px]">
          {active ? (order === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}

const input =
  "w-full rounded border border-white/15 bg-navy px-2 py-1 text-xs font-normal normal-case tracking-normal text-white placeholder:text-white/30 focus:border-cyan focus:outline-none";

/** A "contains" filter, applied once typing pauses. Also the page's search
 * box (with its own label, placeholder and look). */
export function TextFilter({
  name,
  label,
  list,
  ariaLabel = `Filter ${label}`,
  placeholder = "contains…",
  className = input,
}: {
  name: string;
  label: string;
  list: ListState;
  ariaLabel?: string;
  placeholder?: string;
  className?: string;
}) {
  const [value, setValue] = useState(list.text(name));
  const settled = useDebounced(value);
  const applied = useRef(list.text(name));
  useEffect(() => {
    if (settled.trim() === applied.current) return;
    applied.current = settled.trim();
    list.setText(name, settled);
  }, [settled, name, list]);
  // "Clear filters": empty the box, including typing not applied yet (its
  // pending debounce is dropped with it).
  const clears = useRef(list.clearCount);
  useEffect(() => {
    if (list.clearCount === clears.current) return;
    clears.current = list.clearCount;
    applied.current = "";
    setValue("");
  }, [list.clearCount]);

  return (
    <input
      type="search"
      aria-label={ariaLabel}
      placeholder={placeholder}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      className={className}
    />
  );
}

export type PickOption = { value: string; label: string };

/** A pick-list filter: any number of values; none chosen means no filter. */
export function PickFilter({
  name,
  label,
  options,
  list,
}: {
  name: string;
  label: string;
  options: PickOption[];
  list: Pick<ListState, "values" | "setValues">;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const clickOutside = (event: MouseEvent) => {
      if (menu.current?.open && event.target instanceof Node && !menu.current.contains(event.target)) {
        menu.current.open = false;
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !menu.current?.open) return;
      const restoreFocus = menu.current.contains(document.activeElement);
      menu.current.open = false;
      if (restoreFocus) menu.current.querySelector("summary")?.focus();
    };
    document.addEventListener("click", clickOutside, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("click", clickOutside, true);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  const chosen = list.values(name);
  const labelOf = (value: string) => options.find((o) => o.value === value)?.label ?? value;
  const summary = chosen.length === 0 ? "All" : chosen.length === 1 ? labelOf(chosen[0]) : `${labelOf(chosen[0])} +${chosen.length - 1}`;
  const toggle = (value: string) =>
    list.setValues(name, chosen.includes(value) ? chosen.filter((v) => v !== value) : [...chosen, value]);

  return (
    <details ref={menu} className="relative font-normal normal-case tracking-normal">
      <summary
        aria-label={`Filter ${label}: ${summary}`}
        className={`${input} cursor-pointer list-none truncate ${chosen.length ? "border-cyan text-cyan" : "text-white/60"}`}
      >
        {summary} ▾
      </summary>
      <div
        role="group"
        aria-label={`${label} values`}
        className="absolute z-10 mt-1 max-h-64 w-56 overflow-y-auto rounded-md border border-white/15 bg-navy p-2 shadow-lg"
      >
        {options.length === 0 && <p className="text-xs text-white/50">No values yet</p>}
        {options.map((option) => (
          <label key={option.value} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs text-white/80 hover:bg-white/5">
            <input type="checkbox" checked={chosen.includes(option.value)} onChange={() => toggle(option.value)} />
            {option.label}
          </label>
        ))}
        {chosen.length > 0 && (
          <button type="button" onClick={() => list.setValues(name, [])} className="mt-1 text-xs text-cyan hover:underline">
            Clear
          </button>
        )}
      </div>
    </details>
  );
}

/** Pick-list options from a facet's values: "" becomes "(blank)". */
export function facetOptions(values: string[] | undefined, labels: Record<string, string> = {}): PickOption[] {
  return (values ?? []).map((value) => ({ value, label: value === "" ? "(blank)" : (labels[value] ?? value) }));
}
