"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "./apiClient";

export type DashboardState = { scoring_mode: "findings_based" | "evidence_qualified"; settings_version: number; evidence_revision: number; evaluation_id: string | null };

/** Cheap revision/mode polling, not an inventory scan. Never keeps a login alive. */
export function useDashboardState(orgId: string) {
  const [snapshot, setSnapshot] = useState<{ orgId: string; data: DashboardState | null; error: string | null } | null>(null);
  const serial = useRef(0);
  useEffect(() => {
    let current = true;
    async function refresh() {
      const request = ++serial.current;
      try {
        const value = await api.get<DashboardState>(`/orgs/${orgId}/scoring/dashboard-state`, { background: true });
        if (current && request === serial.current) setSnapshot({ orgId, data: value, error: null });
      } catch (cause) {
        if (current && request === serial.current) setSnapshot({ orgId, data: null, error: cause instanceof Error ? cause.message : "Could not verify Dashboard state" });
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    window.addEventListener("focus", refresh);
    return () => { current = false; serial.current++; clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [orgId]);
  return snapshot?.orgId === orgId ? { state: snapshot.data, error: snapshot.error } : { state: null, error: null };
}
