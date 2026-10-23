"use client";

import { useMeState } from "@/lib/useMe";

/** The Platform pages: the Sysadmin's only (the API refuses anyone else too). */
export function SysadminOnly({ children }: { children: React.ReactNode }) {
  const { data: me, error, loading, reload } = useMeState();
  if (loading && !me) return <p className="text-sm text-white/60">Loading…</p>;
  if (error || !me) return (
    <div role="alert" className="space-y-2 text-sm text-red-300">
      <p>{error ?? "Couldn't load your account."}</p>
      <button type="button" onClick={reload} className="text-cyan hover:underline">Retry</button>
    </div>
  );
  if (!me.is_sysadmin) return <p className="text-sm text-white/60">This page is for the Sysadmin.</p>;
  return <>{children}</>;
}
