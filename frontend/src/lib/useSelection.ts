"use client";

import { useCallback, useMemo, useState } from "react";

import type { ListState } from "@/lib/useListState";

/** The most rows picked at once (the API's limit for one request). */
export const SELECTION_MAX = 500;

type Row = { id: string; name: string };
const NONE = new Map<string, string>();

/** Rows picked for an action on several at once, by id (with a name to
 * show), kept while paging through the list. Changing the filters or the
 * organization starts over, so nothing picked hides behind a filter. */
export function useSelection(list: ListState, orgId: string) {
  const scope = `${orgId}?${list.filterKey}`;
  const [state, setState] = useState({ scope, picked: NONE });
  const picked = state.scope === scope ? state.picked : NONE;

  const change = useCallback(
    (edit: (next: Map<string, string>) => void) =>
      setState((before) => {
        const next = new Map(before.scope === scope ? before.picked : NONE);
        edit(next);
        return { scope, picked: next };
      }),
    [scope],
  );

  return useMemo(
    () => ({
      count: picked.size,
      ids: [...picked.keys()],
      /** The names of these ids (as picked). */
      names: (ids: string[]) => ids.map((id) => picked.get(id) ?? id),
      has: (id: string) => picked.has(id),
      full: picked.size >= SELECTION_MAX,
      /** Pick (`on`) or drop these rows; past SELECTION_MAX, no more are picked. */
      set: (rows: Row[], on: boolean) =>
        change((next) => {
          for (const row of rows) {
            if (!on) next.delete(row.id);
            else if (next.size < SELECTION_MAX) next.set(row.id, row.name);
          }
        }),
      clear: () => change((next) => next.clear()),
    }),
    [picked, change],
  );
}

export type Selection = ReturnType<typeof useSelection>;
