"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, clearToken, getToken, refreshAccessToken, setSessionHandlers, setToken } from "@/lib/apiClient";
import type { MyOrganization, Token } from "@/lib/types";

const ORG_KEY = "auditmind_org_id";

type AppContextValue = {
  /** False until the session has been looked for (the cookie, on load). */
  hydrated: boolean;
  isAuthenticated: boolean;
  /** Every page but Change password is refused until it's changed. */
  mustChangePassword: boolean;
  /** Why the user was signed out (idle too long, say), for the sign-in page. */
  signedOutReason: string | null;
  orgs: MyOrganization[];
  orgsLoading: boolean;
  orgsError: string | null;
  selectedOrg: MyOrganization | null;
  login(email: string, password: string): Promise<void>;
  register(details: { orgName: string; email: string; password: string; name?: string }): Promise<void>;
  logout(): Promise<void>;
  changePassword(current: string, next: string): Promise<void>;
  selectOrg(orgId: string): void;
  createOrg(name: string): Promise<void>;
};

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const [token, setTokenState] = useState<string | null>(null);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [signedOutReason, setSignedOutReason] = useState<string | null>(null);
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

  // Signed in (or the session renewed on load): the orgs, unless the
  // password must be changed first (they'd be refused).
  const signIn = useCallback(
    async (accessToken: string, mustChange: boolean) => {
      setToken(accessToken);
      setTokenState(accessToken);
      setSignedOutReason(null);
      setMustChangePassword(mustChange);
      if (!mustChange) await loadOrgs();
    },
    [loadOrgs],
  );

  const signedOut = useCallback((reason: string | null) => {
    clearToken();
    window.localStorage.removeItem(ORG_KEY);
    setTokenState(null);
    setMustChangePassword(false);
    setSignedOutReason(reason);
    setOrgs([]);
    setSelectedOrgId(null);
  }, []);

  useEffect(() => {
    setSessionHandlers({
      onSessionEnded: (message) => signedOut(message),
      onPasswordChangeRequired: () => setMustChangePassword(true),
    });
    return () => setSessionHandlers(null);
  }, [signedOut]);

  // On load: the token is only in memory, so a new page (or a reload) asks
  // for one with the session cookie. (One already there: set by a test, or
  // kept across a hot reload in development.)
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const existing = getToken();
      const session = existing ? null : await refreshAccessToken().catch(() => null);
      if (cancelled) return;
      if (existing) await signIn(existing, false);
      else if (session) await signIn(session.access_token, session.must_change_password);
      setHydrated(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [signIn]);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api.post<Token>("/auth/login", { email, password });
      await signIn(session.access_token, session.must_change_password);
    },
    [signIn],
  );

  const register = useCallback(
    async (details: { orgName: string; email: string; password: string; name?: string }) => {
      const session = await api.post<Token>("/auth/register", {
        org_name: details.orgName,
        email: details.email,
        password: details.password,
        name: details.name || undefined,
      });
      // A new account's only org is the one just created, so select it.
      window.localStorage.removeItem(ORG_KEY);
      await signIn(session.access_token, session.must_change_password);
    },
    [signIn],
  );

  const logout = useCallback(async () => {
    // Ends the session on the server (the cookie too); signed out here
    // whatever happens.
    await api.post("/auth/logout").catch(() => undefined);
    signedOut(null);
  }, [signedOut]);

  const changePassword = useCallback(
    async (current: string, next: string) => {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      setMustChangePassword(false);
      if (mustChangePassword) await loadOrgs();
    },
    [mustChangePassword, loadOrgs],
  );

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
      mustChangePassword,
      signedOutReason,
      orgs,
      orgsLoading,
      orgsError,
      selectedOrg: orgs.find((o) => o.id === selectedOrgId) ?? null,
      login,
      register,
      logout,
      changePassword,
      selectOrg,
      createOrg,
    }),
    [
      hydrated,
      token,
      mustChangePassword,
      signedOutReason,
      orgs,
      orgsLoading,
      orgsError,
      selectedOrgId,
      login,
      register,
      logout,
      changePassword,
      selectOrg,
      createOrg,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
