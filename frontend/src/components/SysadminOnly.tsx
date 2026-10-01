"use client";

import { useMe } from "@/lib/useMe";

/** The Platform pages: the Sysadmin's only (the API refuses anyone else too). */
export function SysadminOnly({ children }: { children: React.ReactNode }) {
  const me = useMe();
  if (me === null) return <p className="text-sm text-white/60">Loading…</p>;
  if (!me.is_sysadmin) return <p className="text-sm text-white/60">This page is for the Sysadmin.</p>;
  return <>{children}</>;
}
