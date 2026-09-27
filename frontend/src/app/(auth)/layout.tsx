"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useApp } from "@/context/AppContext";

/** Sign-in pages; already signed-in users go straight to the dashboard. */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { hydrated, isAuthenticated } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && isAuthenticated) router.replace("/");
  }, [hydrated, isAuthenticated, router]);

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center text-2xl font-semibold tracking-wide text-white">
          Audit<span className="text-cyan">Mind</span>
        </div>
        {children}
      </div>
    </div>
  );
}
