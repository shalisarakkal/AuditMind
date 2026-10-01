"use client";

import { useApi } from "@/lib/useApi";

type AuthOptions = { public_signup: boolean };

/** What the sign-in pages offer (GET /auth/options): null until known, or
 * if the server can't say. */
export function useAuthOptions(): AuthOptions | null {
  return useApi<AuthOptions>("/auth/options").data;
}
