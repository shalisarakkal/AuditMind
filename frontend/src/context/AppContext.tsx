"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, clearToken, getToken, setToken } from "@/lib/apiClient";
import type { MyOrganization, Token } from "@/lib/types";

const ORG_KEY = "auditmind_org_id";

type AppContextValue = {
  /** False until localStorage has been read (it isn't available during prerender). */
  hydrated: boolean;
  isAuthenticated: boolean;
  orgs: MyOrganization[];
  orgsLoading: boolean;
  orgsError: string | null;
  selectedOrg: MyOrganization | null;
  login(email: string, password: string): Promise<void>;
  register(details: { orgName: string; email: string; password: string; name?: string }): Promise<void>;
  logout(): void;
  selectOrg(orgId: string): void;
  createOrg(name: string): Promise<void>;
};

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const [token, setTokenState] = useState<string | null>(null);
  const [orgs, setOrgs] = useState<MyOrganization[]>([]);
  const [orgsLoading, setOrgsLoading] = useState(false);
  const [orgsError, setOrgsError] = useState<string | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);

  const selectOrg = useCallback((orgId: string) => {
    window.localStorage.setItem(ORG_KEY, orgId);
    setSelectedOrgId(orgId);
  }, []);

  // Load the user's orgs; keep the remembered selection only if it's still one
  // of them (the user may have lost access, or another user signed in).
  const loadOrgs = useCallback(
    async (preferOrgId?: string) => {
      setOrgsLoading(true);
      setOrgsError(null);
      try {
        const list = await api.get<MyOrganization[]>("/orgs");
        setOrgs(list);
        const wanted = preferOrgId ?? window.localStorage.getItem(ORG_KEY);
        const next = list.find((o) => o.id === wanted) ?? list[0];
        if (next) selectOrg(next.id);
        else setSelectedOrgId(null);
      } catch (err) {
        setOrgsError((err as Error).message);
      } finally {
        setOrgsLoading(false);
      }
    },
    [selectOrg],
  );

  useEffect(() => {
    const stored = getToken();
    setTokenState(stored);
    setHydrated(true);
    if (stored) void loadOrgs();
  }, [loadOrgs]);

  const signIn = useCallback(
    async (accessToken: string) => {
      setToken(accessToken);
      setTokenState(accessToken);
      await loadOrgs();
    },
    [loadOrgs],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await api.post<Token>("/auth/login", { email, password });
      await signIn(access_token);
    },
    [signIn],
  );

  const register = useCallback(
    async (details: { orgName: string; email: string; password: string; name?: string }) => {
      const { access_token } = await api.post<Token>("/auth/register", {
        org_name: details.orgName,
        email: details.email,
        password: details.password,
        name: details.name || undefined,
      });
      // A new account's only org is the one just created, so select it.
      window.localStorage.removeItem(ORG_KEY);
      await signIn(access_token);
    },
    [signIn],
  );

  const logout = useCallback(() => {
    clearToken();
    window.localStorage.removeItem(ORG_KEY);
    setTokenState(null);
    setOrgs([]);
    setSelectedOrgId(null);
  }, []);

  const createOrg = useCallback(
    async (name: string) => {
      const org = await api.post<MyOrganization>("/orgs", { name });
      await loadOrgs(org.id);
    },
    [loadOrgs],
  );

  const value = useMemo<AppContextValue>(
    () => ({
      hydrated,
      isAuthenticated: token !== null,
      orgs,
      orgsLoading,
      orgsError,
      selectedOrg: orgs.find((o) => o.id === selectedOrgId) ?? null,
      login,
      register,
      logout,
      selectOrg,
      createOrg,
    }),
    [hydrated, token, orgs, orgsLoading, orgsError, selectedOrgId, login, register, logout, selectOrg, createOrg],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
