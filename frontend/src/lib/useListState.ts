"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { browserTimezone } from "./findingWorkflow";

export type SortOrder = "asc" | "desc";

// Not the endpoint's: which org the address's sort and filters belong to.
const ORG_KEY = "org";

/** A paged list's sort, filters and offset, kept in the page address (so a
 * refresh or the Back button brings them back, and a view can be shared as a
 * link). Keys are the list endpoint's own query parameters: `apiQuery` is
 * what to send it. Any change other than paging goes back to the first page.
 *
 * The address also names the org (`org=`): a list opened for another org
 * (after switching org, or from a link to another org's view) starts clean
 * rather than applying that org's filters to this one. */
export function useListState(pageSize: number, orgId: string) {
  const router = useRouter();
  const pathname = usePathname();
  const initial = useSearchParams();
  const [params, setParams] = useState(() => {
    const fromAddress = new URLSearchParams(initial?.toString() ?? "");
    const owner = fromAddress.get(ORG_KEY);
    return owner && owner !== orgId ? new URLSearchParams() : fromAddress;
  });
  const latest = useRef(params); // several changes in one event build on each other
  // Goes up on "Clear filters", so filter boxes drop typing not applied yet.
  const [clearCount, setClearCount] = useState(0);

  const write = useCallback(
    (next: URLSearchParams) => {
      latest.current = next;
      setParams(next);
      const query = new URLSearchParams(next);
      if ([...query.keys()].length) query.set(ORG_KEY, orgId);
      else query.delete(ORG_KEY);
      const text = query.toString();
      router.replace(text ? `${pathname}?${text}` : pathname, { scroll: false });
    },
    [router, pathname, orgId],
  );

  // On opening the list, settle the address: another org's view is dropped,
  // and a view with no org named yet (an older link) is stamped with this
  // one, so switching org straight away doesn't carry it over.
  useEffect(() => {
    const owner = initial?.get(ORG_KEY);
    if (owner && owner !== orgId) write(new URLSearchParams());
    else if (!owner && [...latest.current.keys()].length) write(latest.current);
    // Only on opening the list: later changes write the address themselves.
  }, []);

  const update = useCallback(
    (change: (next: URLSearchParams) => void, keepOffset = false) => {
      const next = new URLSearchParams(latest.current);
      next.delete(ORG_KEY);
      change(next);
      if (!keepOffset) next.delete("offset");
      write(next);
    },
    [write],
  );

  return useMemo(() => {
    const own = new URLSearchParams(params);
    own.delete(ORG_KEY);
    const offset = Math.max(0, Number(own.get("offset")) || 0);
    const apiQuery = new URLSearchParams(own);
    // Date-only controls cover whole browser-local days; no time controls needed.
    apiQuery.delete("filter_timezone");
    if (own.get("since") || own.get("until")) apiQuery.set("filter_timezone", browserTimezone() || "");
    // A sort without an order (an old link) is shown ascending: ask for it
    // (some lists' own default is newest first).
    if (own.get("sort") && !own.get("order")) apiQuery.set("order", "asc");
    apiQuery.set("limit", String(pageSize));
    apiQuery.set("offset", String(offset));
    const filterKeys = [...new Set(own.keys())].filter((k) => !["sort", "order", "offset"].includes(k));
    return {
      apiQuery: apiQuery.toString(),
      offset,
      sort: own.get("sort"),
      order: (own.get("order") === "desc" ? "desc" : "asc") as SortOrder,
      /** A text filter's value ("" when unset). */
      text: (key: string) => own.get(key) ?? "",
      /** A pick-list filter's chosen values. */
      values: (key: string) => own.getAll(key),
      hasFilters: filterKeys.length > 0,
      /** The filters as one string: changes whenever any filter does. */
      filterKey: [...filterKeys]
        .sort()
        .flatMap((k) => own.getAll(k).map((v) => `${k}=${v}`))
        .join("&"),
      clearCount,
      setText: (key: string, value: string) =>
        update((next) => (value.trim() ? next.set(key, value.trim()) : next.delete(key))),
      setValues: (key: string, values: string[]) =>
        update((next) => {
          next.delete(key);
          values.forEach((value) => next.append(key, value));
        }),
      /** Sort by `column` (the order always written: some lists default to
       * newest first), or back to the list's default order (null). */
      setSort: (column: string | null, order: SortOrder = "asc") =>
        update((next) => {
          next.delete("sort");
          next.delete("order");
          if (column) {
            next.set("sort", column);
            next.set("order", order);
          }
        }),
      setOffset: (value: number) =>
        update((next) => (value > 0 ? next.set("offset", String(value)) : next.delete("offset")), true),
      clearFilters: () => {
        setClearCount((count) => count + 1);
        update((next) => {
          for (const key of filterKeys) next.delete(key);
        });
      },
    };
  }, [params, pageSize, update, clearCount]);
}

export type ListState = ReturnType<typeof useListState>;
