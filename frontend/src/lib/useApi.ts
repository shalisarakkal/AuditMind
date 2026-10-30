"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/apiClient";

type State<T> = { data: T | null; error: string | null; loading: boolean };

/** GET `path` (skipped while null); refetches when the path changes. */
export function useApi<T>(path: string | null, options?: { background?: boolean; keepPreviousData?: boolean }) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: path !== null });
  const [version, setVersion] = useState(0);
  const background = options?.background ?? false;
  const keepPreviousData = options?.keepPreviousData ?? false;

  useEffect(() => {
    if (path === null) return;
    let current = true; // ignore a response for a path we've since moved off
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .get<T>(path, { background })
      .then((data) => current && setState({ data, error: null, loading: false }))
      .catch((err: Error) => current && setState(previous => ({ data: keepPreviousData ? previous.data : null, error: err.message, loading: false })));
    return () => {
      current = false;
    };
  }, [path, version, background, keepPreviousData]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, reload };
}
