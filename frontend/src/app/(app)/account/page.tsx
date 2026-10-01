"use client";

import Link from "next/link";
import { useState } from "react";

import { ListTable, ROW, TD, TH, THEAD } from "@/components/ListPage";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { api } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
import { CHANGE_PASSWORD_PATH } from "@/lib/paths";
import { ROLE_LABELS } from "@/lib/people";
import type { Me } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const INPUT =
  "w-full max-w-sm rounded-md border border-white/15 bg-navy px-3 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none";
const BUTTON = "rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50";

/** The signed-in user's own details: their name (which they can change),
 * their email, their orgs and roles, and their password. */
export default function AccountPage() {
  const { orgs, accountChanged } = useApp();
  const { data: me, error, loading } = useApi<Me>("/auth/me");

  return (
    <div className="max-w-3xl space-y-8">
      <h1 className="text-2xl font-semibold text-white">Your account</h1>
      <StatusMessage loading={loading && !me} error={error} />
      {me && (
        <>
          <NameForm me={me} onSaved={accountChanged} />

          <section className="space-y-1">
            <h2 className="text-lg font-medium text-white">Email</h2>
            <p className="text-sm text-white">{me.email}</p>
            <p className="text-xs text-white/50">You sign in with it, so it can&apos;t be changed here.</p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">Organizations</h2>
            {orgs.length === 0 ? (
              <p className="text-sm text-white/60">You don&apos;t belong to any organization.</p>
            ) : (
              <ListTable>
                <thead className={THEAD}>
                  <tr>
                    <th className={TH}>Organization</th>
                    <th className={TH}>Your role</th>
                  </tr>
                </thead>
                <tbody>
                  {orgs.map((org) => (
                    <tr key={org.id} className={ROW}>
                      <td className={`${TD} text-white`}>{org.name}</td>
                      <td className={TD}>{ROLE_LABELS[org.role]}</td>
                    </tr>
                  ))}
                </tbody>
              </ListTable>
            )}
          </section>

          <section className="space-y-1">
            <h2 className="text-lg font-medium text-white">Password</h2>
            {me.password_expires_at && (
              <p className="text-sm text-white/60">It must be changed by {formatDateTime(me.password_expires_at)}.</p>
            )}
            <Link href={CHANGE_PASSWORD_PATH} className="text-sm text-cyan hover:underline">
              Change password
            </Link>
          </section>
        </>
      )}
    </div>
  );
}

function NameForm({ me, onSaved }: { me: Me; onSaved(): void }) {
  const [name, setName] = useState(me.name ?? "");
  const [saved, setSaved] = useState(me.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const trimmed = name.trim();
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patch<Me>("/auth/me", { name: trimmed });
      setName(updated.name ?? "");
      setSaved(updated.name ?? "");
      setDone(true);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-2">
      <label htmlFor="account-name" className="block text-lg font-medium text-white">
        Name
      </label>
      <p className="text-xs text-white/50">How you&apos;re shown to others: in People, Activity and the account menu.</p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          id="account-name"
          value={name}
          maxLength={100}
          onChange={(e) => {
            setName(e.target.value);
            setDone(false);
          }}
          placeholder="Your name"
          className={INPUT}
        />
        <button type="submit" disabled={busy || !trimmed || trimmed === saved} className={BUTTON}>
          {busy ? "Saving…" : "Save"}
        </button>
        {done && <span className="text-sm text-emerald-300">Saved</span>}
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}
    </form>
  );
}
