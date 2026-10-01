"use client";

import { Suspense, useState } from "react";

import ConfirmPanel from "@/components/ConfirmPanel";
import { PickFilter, SortHeader, facetOptions } from "@/components/ListControls";
import {
  ACTIONS_CELL,
  EmptyRow,
  FILTER_CELL,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW,
  ROW_ACTION,
  ROW_ACTION_DANGER,
  TD,
  TH,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { SysadminOnly } from "@/components/SysadminOnly";
import TemporaryPassword, { type Handover } from "@/components/TemporaryPassword";
import { useApp } from "@/context/AppContext";
import { api } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
import { displayName, ROLE_LABELS, ROLES, STATUS_LABELS } from "@/lib/people";
import type { MemberStatus, Page, PasswordReset, PlatformUser, UserRole } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";

const PAGE_SIZE = 100;
const COLUMNS = 6;

const INPUT =
  "rounded-md border border-white/15 bg-navy px-3 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none";
const BUTTON = "rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50";
const STATUS_BADGES: Record<MemberStatus, string> = {
  active: "bg-emerald-400/15 text-emerald-300",
  locked: "bg-red-400/15 text-red-300",
  must_change_password: "bg-white/10 text-white/70",
  deactivated: "bg-red-400/15 text-red-300",
};

type Pending =
  | { kind: "reset" | "unlock" | "deactivate" | "reactivate"; user: PlatformUser }
  | { kind: "role"; user: PlatformUser; orgId: string; orgName: string; from: UserRole; role: UserRole };

export default function AccountsPage() {
  return (
    <SysadminOnly>
      <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
        <Accounts />
      </Suspense>
    </SysadminOnly>
  );
}

function Accounts() {
  const { accountChanged } = useApp();
  const list = useListState(PAGE_SIZE, "platform");
  const { data: page, error, loading, reload } = useApi<Page<PlatformUser>>(`/platform/users?${list.apiQuery}`);
  const facets = useApi<{ status: string[] }>("/platform/users/facets");
  const [pending, setPending] = useState<Pending | null>(null);
  const [editing, setEditing] = useState<PlatformUser | null>(null);
  const [handover, setHandover] = useState<Handover | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = () => {
    reload();
    facets.reload();
  };
  const start = () => {
    setActionError(null);
    setNotice(null);
    setHandover(null);
    setPending(null);
    setEditing(null);
  };

  async function confirm(change: Pending) {
    setBusy(true);
    setActionError(null);
    const url = `/platform/users/${change.user.id}`;
    const who = displayName(change.user);
    try {
      if (change.kind === "reset") {
        const reset = await api.post<PasswordReset>(`${url}/reset-password`);
        setHandover({ who, password: reset.temporary_password, expiresAt: reset.expires_at, added: false });
      } else if (change.kind === "unlock") {
        await api.post(`${url}/unlock`);
        setNotice(`${who} is unlocked.`);
      } else if (change.kind === "role") {
        await api.patch(`${url}/orgs/${change.orgId}`, { role: change.role });
        setNotice(`${who} is now ${ROLE_LABELS[change.role]} in ${change.orgName}, and was signed out.`);
      } else {
        const active = change.kind === "reactivate";
        await api.patch(url, { active });
        setNotice(active ? `${who} can sign in again.` : `${who} is deactivated and was signed out.`);
      }
      setPending(null);
      refresh();
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Accounts"
        total={page?.total}
        noun="accounts"
        orgName="AuditMind"
        filtered={list.hasFilters}
        note="Everyone's account, whatever their organizations. For emergencies: their own admins add people and change roles. Only you reset the password or change the name of someone in several organizations, change an email (the sign-in), or deactivate an account."
      />

      {editing && (
        <EditAccount
          user={editing}
          onCancel={() => setEditing(null)}
          onSaved={(updated) => {
            setEditing(null);
            setNotice(`Saved ${updated.email}.`);
            refresh();
            accountChanged(); // in case it's the Sysadmin's own
          }}
        />
      )}
      {pending && (
        <ConfirmPanel
          label="Confirm"
          message={confirmMessage(pending)}
          confirmLabel={CONFIRM_LABELS[pending.kind]}
          danger={pending.kind === "deactivate"}
          busy={busy}
          onConfirm={() => void confirm(pending)}
          onCancel={() => setPending(null)}
        />
      )}
      {handover && <TemporaryPassword handover={handover} onDone={() => setHandover(null)} />}
      {notice && (
        <p role="status" className="text-sm text-emerald-300">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="text-sm text-red-300">
          {actionError}
        </p>
      )}

      <ListToolbar list={list} label="accounts" />
      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable>
          <thead className={THEAD}>
            <tr>
              <SortHeader label="Name" column="name" list={list} defaultSort="name" />
              <SortHeader label="Email" column="email" list={list} />
              <th className={TH}>Organizations and roles</th>
              <SortHeader label="Status" column="status" list={list} />
              <SortHeader label="Created" column="created" list={list} />
              <th className={TH}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
            <tr>
              <th />
              <th />
              <th />
              <th className={FILTER_CELL}>
                <PickFilter name="status" label="status" list={list} options={facetOptions(facets.data?.status, STATUS_LABELS)} />
              </th>
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {page.items.length === 0 && <EmptyRow colSpan={COLUMNS} noun="accounts" filtered={list.hasFilters} />}
            {page.items.map((user) => (
              <tr key={user.id} className={`${ROW} align-top`}>
                <td className={`${TD} text-white`}>
                  {user.name || <span className="text-white/40">—</span>}
                  {user.is_sysadmin && <p className="text-xs text-cyan">Sysadmin</p>}
                </td>
                <td className={TD}>{user.email}</td>
                <td className={`${TD} space-y-1`}>
                  {user.orgs.length === 0 && <span className="text-xs text-white/40">none</span>}
                  {user.orgs.map((org) => (
                    <div key={org.org_id} className="flex items-center gap-2 text-xs">
                      <span className="text-white/80">{org.name}</span>
                      <select
                        aria-label={`Role of ${displayName(user)} in ${org.name}`}
                        value={org.role}
                        onChange={(e) => {
                          start();
                          setPending({
                            kind: "role",
                            user,
                            orgId: org.org_id,
                            orgName: org.name,
                            from: org.role,
                            role: e.target.value as UserRole,
                          });
                        }}
                        className="rounded border border-white/15 bg-navy px-1 py-0.5 text-xs text-white focus:border-cyan focus:outline-none"
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {ROLE_LABELS[role]}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </td>
                <td className={TD}>
                  <span className={`rounded px-2 py-0.5 text-xs ${STATUS_BADGES[user.status]}`}>{STATUS_LABELS[user.status]}</span>
                  {user.status === "locked" && (
                    <p className="mt-1 text-xs text-white/50">
                      {user.locked_until ? `until ${formatDateTime(user.locked_until)}` : "until unlocked"}
                    </p>
                  )}
                </td>
                <td className={`${TD} whitespace-nowrap text-xs text-white/60`}>{formatDateTime(user.created_at)}</td>
                <td className={ACTIONS_CELL}>
                  <button type="button" className={ROW_ACTION} onClick={() => (start(), setEditing(user))}>
                    Edit
                  </button>
                  {!user.is_sysadmin && (
                    <>
                      {user.status === "locked" && (
                        <button type="button" className={ROW_ACTION} onClick={() => (start(), setPending({ kind: "unlock", user }))}>
                          Unlock
                        </button>
                      )}
                      <button type="button" className={ROW_ACTION} onClick={() => (start(), setPending({ kind: "reset", user }))}>
                        Reset password
                      </button>
                      {user.status === "deactivated" ? (
                        <button type="button" className={ROW_ACTION} onClick={() => (start(), setPending({ kind: "reactivate", user }))}>
                          Reactivate
                        </button>
                      ) : (
                        <button type="button" className={ROW_ACTION_DANGER} onClick={() => (start(), setPending({ kind: "deactivate", user }))}>
                          Deactivate
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}

const CONFIRM_LABELS: Record<Pending["kind"], string> = {
  reset: "Reset password",
  unlock: "Unlock",
  deactivate: "Deactivate",
  reactivate: "Reactivate",
  role: "Change role",
};

function confirmMessage(pending: Pending): string {
  const who = displayName(pending.user);
  switch (pending.kind) {
    case "reset":
      return `Reset ${who}'s password? You'll get a temporary password to give them; they're signed out until they use it.`;
    case "unlock":
      return `Unlock ${who}, so they can sign in again?`;
    case "deactivate":
      return `Deactivate ${who}? They're signed out at once and can't sign in, in any organization, until reactivated.`;
    case "reactivate":
      return `Reactivate ${who}, so they can sign in again?`;
    case "role":
      return `Change ${who}'s role in ${pending.orgName} from ${ROLE_LABELS[pending.from]} to ${ROLE_LABELS[pending.role]}? They'll be signed out. Normally the organization's admins do this.`;
  }
}

/** Rename, or change the email (the sign-in). */
function EditAccount({ user, onSaved, onCancel }: { user: PlatformUser; onSaved(user: PlatformUser): void; onCancel(): void }) {
  const [name, setName] = useState(user.name ?? "");
  const [email, setEmail] = useState(user.email);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changes: Record<string, string> = {};
  if (name.trim() && name.trim() !== (user.name ?? "")) changes.name = name.trim();
  if (email.trim().toLowerCase() !== user.email) changes.email = email.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.patch<PlatformUser>(`/platform/users/${user.id}`, changes));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label={`Edit ${user.email}`} className="space-y-3 rounded-lg border border-cyan/30 bg-cyan/5 p-4 text-sm">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-white/70">
          Name
          <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} className={`${INPUT} mt-1 block w-56`} />
        </label>
        <label className="text-white/70">
          Email (the sign-in)
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={`${INPUT} mt-1 block w-64`} />
        </label>
        <button type="submit" disabled={busy || Object.keys(changes).length === 0} className={BUTTON}>
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onCancel} className="text-xs text-white/60 hover:text-white">
          Cancel
        </button>
      </div>
      {"email" in changes && (
        <p className="text-xs text-amber-200">They&apos;ll sign in with the new email from now on: tell them.</p>
      )}
      {error && <p className="text-red-300">{error}</p>}
    </form>
  );
}
