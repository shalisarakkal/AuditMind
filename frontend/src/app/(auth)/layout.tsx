"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useApp } from "@/context/AppContext";
import ProductBrand from "@/components/ProductBrand";

/** Sign-in pages; already signed-in users go straight to the dashboard. */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { hydrated, isAuthenticated } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && isAuthenticated) router.replace("/");
  }, [hydrated, isAuthenticated, router]);

  return (
    <main className="flex min-h-svh items-center justify-center px-4 py-10 sm:px-6">
      <div className="w-full max-w-[25rem]">
        <div className="mb-6 flex justify-center">
          <ProductBrand variant="auth" />
        </div>
        {children}
      </div>
    </main>
  );
}
