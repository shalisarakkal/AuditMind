"use client";

import { useRouter } from "next/navigation";

import AuthGuard from "@/components/AuthGuard";
import ChangePasswordForm from "@/components/ChangePasswordForm";

/** Outside the app's layout (no sidebar, no polling), so it works while
 * every other page is refused until the password is changed. */
export default function ChangePasswordPage() {
  const router = useRouter();
  return (
    <AuthGuard>
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center text-2xl font-semibold tracking-wide text-white">
            Audit<span className="text-cyan">Mind</span>
          </div>
          <ChangePasswordForm onDone={() => router.replace("/")} />
        </div>
      </div>
    </AuthGuard>
  );
}
