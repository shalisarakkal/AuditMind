"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useApp } from "@/context/AppContext";
import { CHANGE_PASSWORD_PATH } from "@/lib/paths";
import LoadingIndicator from "@/components/LoadingIndicator";

/** Renders children only for a signed-in user; otherwise sends them to /login.
 * Only a generic loading indicator renders until the session is checked, so protected
 * pages never flash for signed-out visitors. A user who must change their
 * password (a temporary or expired one) is sent to Change password first. */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { hydrated, isAuthenticated, mustChangePassword } = useApp();
  const router = useRouter();
  const pathname = usePathname();
  const mustGo = isAuthenticated && mustChangePassword && pathname !== CHANGE_PASSWORD_PATH;

  useEffect(() => {
    if (hydrated && !isAuthenticated) router.replace("/login");
    else if (hydrated && mustGo) router.replace(CHANGE_PASSWORD_PATH);
  }, [hydrated, isAuthenticated, mustGo, router]);

  if (!hydrated) return <div className="flex min-h-screen items-center justify-center p-6"><LoadingIndicator label="Opening AuditMind…" detail="Checking your session and organizations." /></div>;
  if (!isAuthenticated || mustGo) return null;
  return <>{children}</>;
}
