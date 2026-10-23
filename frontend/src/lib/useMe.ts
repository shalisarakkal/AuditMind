"use client";

import { useApp } from "@/context/AppContext";
import type { Me } from "@/lib/types";
import { useApi } from "@/lib/useApi";

/** The signed-in user (GET /auth/me), loaded again when their own details
 * change (accountChanged). Null while loading, or if it can't be had. */
export function useMeState() {
  const { accountVersion } = useApp();
  return useApi<Me>(`/auth/me?v=${accountVersion}`);
}

export function useMe(): Me | null {
  return useMeState().data;
}
