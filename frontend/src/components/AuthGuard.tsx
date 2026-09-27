"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useApp } from "@/context/AppContext";

/** Renders children only for a signed-in user; otherwise sends them to /login.
 * Nothing is rendered until the stored session has been read, so protected
 * pages never flash for signed-out visitors. */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { hydrated, isAuthenticated } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && !isAuthenticated) router.replace("/login");
  }, [hydrated, isAuthenticated, router]);

  if (!hydrated || !isAuthenticated) return null;
  return <>{children}</>;
}
