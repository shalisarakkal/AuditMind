"use client";

import Link from "next/link";
import { Suspense, useState } from "react";

import ConfirmPanel from "@/components/ConfirmPanel";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import {
  ACTIONS_CELL,
  DateRangeFilter,
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
import { useApp } from "@/context/AppContext";
import { api } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
import { ACCOUNT_PATH } from "@/lib/paths";
import { displayName, ROLE_LABELS, ROLES, STATUS_LABELS } from "@/lib/people";
import type { Me, Member, MemberAdded, MemberFacets, MemberStatus, Page, PasswordReset, UserRole } from "@/lib/types";
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

/** An admin's change waiting for "are you sure?". */
type Pending =
  | { kind: "role"; member: Member; role: UserRole }
  | { kind: "remove" | "reset" | "unlock"; member: Member };

/** A temporary password to show the admin, once. */
type Handover = { who: string; password: string; expiresAt: string | null; added: boolean };

// The list reads its sort and filters from the page address.
export default function PeoplePage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <People />
    </Suspense>
  );
}

function People() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const isAdmin = org.role === "admin";
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<Member>>(`/orgs/${org.id}/members?${list.apiQuery}`);
  const facets = useApi<MemberFacets>(`/orgs/${org.id}/members/facets`);
  const me = useApi<Me>("/auth/me");
  const [adding, setAdding] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [renaming, setRenaming] = useState<Member | null>(null);
  const [handover, setHandover] = useState<Handover | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const url = `/orgs/${org.id}/members`;
  const refresh = () => {
    reload();
    facets.reload();
  };
  const start = () => {
    setActionError(null);
    setNotice(null);
    setHandover(null);
  };

  async function confirm(change: Pending) {
    setBusy(true);
    setActionError(null);
    const who = displayName(change.member);
    try {
      if (change.kind === "role") {
        await api.patch(`${url}/${change.member.id}`, { role: change.role });
        setNotice(`${who} is now ${ROLE_LABELS[change.role]}. They were signed out, to start again with their new role.`);
      } else if (change.kind === "remove") {
        await api.delete(`${url}/${change.member.id}`);
        setNotice(`${who} was removed from ${org.name}. Their account stays.`);
      } else if (change.kind === "unlock") {
        await api.post(`${url}/${change.member.id}/unlock`);
        setNotice(`${who} is unlocked and can sign in again.`);
      } else {
        const reset = await api.post<PasswordReset>(`${url}/${change.member.id}/reset-password`);
        setHandover({ who, password: reset.temporary_password, expiresAt: reset.expires_at, added: false });
      }
      setPending(null);
      refresh();
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const roleOptions = facetOptions(facets.data?.role, ROLE_LABELS);
  const statusOptions = facetOptions(facets.data?.status, STATUS_LABELS);

  return (
    <div className="space-y-6">
      <PageHeader
        title="People"
        total={page?.total}
        noun="members"
        orgName={org.name}
        filtered={list.hasFilters}
        note={
          isAdmin
            ? "Everyone here can see this list. As an admin you add people, change roles, reset passwords and unlock accounts."
            : "The people in this organization and their roles. Its admins add and change them."
        }
        action={
          isAdmin && (
            <button
              type="button"
              onClick={() => {
                start();
                setAdding(true);
              }}
              className={BUTTON}
            >
              Add person
            </button>
          )
        }
      />

      {adding && (
        <AddPerson
          url={url}
          onCancel={() => setAdding(false)}
          onAdded={(added) => {
            setAdding(false);
            refresh();
            if (added.temporary_password) {
              setHandover({
                who: displayName(added),
                password: added.temporary_password,
                expiresAt: added.temp_password_expires_at,
                added: true,
              });
            } else {
              setNotice(`${added.email} already had an account, so they sign in with their own password.`);
            }
          }}
        />
      )}
      {renaming && (
        <RenamePerson
          url={url}
          member={renaming}
          onCancel={() => setRenaming(null)}
          onRenamed={(name) => {
            setRenaming(null);
            setNotice(`Renamed to ${name}.`);
            refresh();
          }}
        />
      )}
      {pending && (
        <ConfirmPanel
          label="Confirm"
          message={confirmMessage(pending, org.name)}
          confirmLabel={CONFIRM_LABELS[pending.kind]}
          danger={pending.kind === "remove"}
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

      <ListToolbar list={list} label="people">
        <DateRangeFilter list={list} label="Added" />
      </ListToolbar>

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable>
          <thead className={THEAD}>
            <tr>
              <SortHeader label="Name" column="name" list={list} defaultSort="name" />
              <SortHeader label="Email" column="email" list={list} />
              <SortHeader label="Role" column="role" list={list} />
              <SortHeader label="Status" column="status" list={list} />
              <SortHeader label="Added" column="added" list={list} />
              <th className={TH}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
            <tr>
              <th className={FILTER_CELL}>
                <TextFilter name="name" label="name" list={list} />
              </th>
              <th className={FILTER_CELL}>
                <TextFilter name="email" label="email" list={list} />
              </th>
              <th className={FILTER_CELL}>
                <PickFilter name="role" label="role" list={list} options={roleOptions} />
              </th>
              <th className={FILTER_CELL}>
                <PickFilter name="status" label="status" list={list} options={statusOptions} />
              </th>
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {page.items.length === 0 && <EmptyRow colSpan={COLUMNS} noun="people" filtered={list.hasFilters} />}
            {page.items.map((member) => (
              <MemberRow
                key={member.id}
                member={member}
                isAdmin={isAdmin}
                isMe={member.id === me.data?.id}
                onRole={(role) => {
                  start();
                  setPending({ kind: "role", member, role });
                }}
                onAction={(kind) => {
                  start();
                  setRenaming(null);
                  setPending({ kind, member });
                }}
                onRename={() => {
                  start();
                  setPending(null);
                  setRenaming(member);
                }}
              />
            ))}
          </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}

const CONFIRM_LABELS: Record<Pending["kind"], string> = {
  role: "Change role",
  remove: "Remove",
  reset: "Reset password",
  unlock: "Unlock",
};

function confirmMessage(pending: Pending, orgName: string): string {
  const who = displayName(pending.member);
  switch (pending.kind) {
    case "role":
      return `Change ${who}'s role from ${ROLE_LABELS[pending.member.role]} to ${ROLE_LABELS[pending.role]}? They'll be signed out, to start again with the new role.`;
    case "remove":
      return `Remove ${who} from ${orgName}? They lose access to it at once; their account stays.`;
    case "reset":
      return `Reset ${who}'s password? You'll get a temporary password to give them; they're signed out until they use it.`;
    case "unlock":
      return `Unlock ${who}, so they can sign in again?`;
  }
}

function MemberRow({
  member,
  isAdmin,
  isMe,
  onRole,
  onAction,
  onRename,
}: {
  member: Member;
  isAdmin: boolean;
  isMe: boolean;
  onRole(role: UserRole): void;
  onAction(kind: "remove" | "reset" | "unlock"): void;
  onRename(): void;
}) {
  const manage = isAdmin && !isMe;
  return (
    <tr className={`${ROW} align-top`}>
      <td className={`${TD} text-white`}>
        {member.name || <span className="text-white/40">—</span>}
        {isMe && <span className="ml-2 text-xs text-white/50">(you)</span>}
      </td>
      <td className={TD}>
        {member.email}
        {member.in_other_orgs && <p className="text-xs text-white/50">Also in other organizations</p>}
      </td>
      <td className={TD}>
        {manage ? (
          <select
            aria-label={`Role of ${displayName(member)}`}
            value={member.role}
            onChange={(e) => onRole(e.target.value as UserRole)}
            className="rounded border border-white/15 bg-navy px-2 py-1 text-sm text-white focus:border-cyan focus:outline-none"
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role]}
              </option>
            ))}
          </select>
        ) : (
          ROLE_LABELS[member.role]
        )}
      </td>
      <td className={TD}>
        {/* Not Badge: its capitals would make "Must Change Password". */}
        <span className={`rounded px-2 py-0.5 text-xs ${STATUS_BADGES[member.status]}`}>{STATUS_LABELS[member.status]}</span>
        <StatusDetail member={member} />
      </td>
      <td className={`${TD} whitespace-nowrap text-xs text-white/60`}>{formatDateTime(member.added_at)}</td>
      <td className={ACTIONS_CELL}>
        {isMe && (
          <Link href={ACCOUNT_PATH} className={ROW_ACTION}>
            Your account
          </Link>
        )}
        {manage && (
          <>
            {member.status === "locked" && (
              <button type="button" className={ROW_ACTION} onClick={() => onAction("unlock")}>
                Unlock
              </button>
            )}
            {!member.in_other_orgs && (
              <>
                <button type="button" className={ROW_ACTION} onClick={onRename}>
                  Rename
                </button>
                <button type="button" className={ROW_ACTION} onClick={() => onAction("reset")}>
                  Reset password
                </button>
              </>
            )}
            <button type="button" className={ROW_ACTION_DANGER} onClick={() => onAction("remove")}>
              Remove
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

function StatusDetail({ member }: { member: Member }) {
  let text: string | null = null;
  if (member.status === "locked") {
    text = member.locked_until ? `until ${formatDateTime(member.locked_until)}` : "until an admin unlocks it";
  } else if (member.status === "must_change_password" && member.temp_password_expires_at) {
    text = `temporary password until ${formatDateTime(member.temp_password_expires_at)}`;
  }
  return text ? <p className="mt-1 text-xs text-white/50">{text}</p> : null;
}

function AddPerson({ url, onAdded, onCancel }: { url: string; onAdded(added: MemberAdded): void; onCancel(): void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAdded(await api.post<MemberAdded>(url, { email: email.trim(), name: name.trim() || undefined, role }));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Add person"
      className="space-y-3 rounded-lg border border-cyan/30 bg-cyan/5 p-4"
    >
      <p className="text-sm text-white/70">
        Someone new gets a temporary password to give them, and chooses their own at first sign-in. Someone who already
        has an account keeps their own password and name.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm text-white/70">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={`${INPUT} mt-1 block w-64`}
          />
        </label>
        <label className="text-sm text-white/70">
          Name
          <input
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="For a new account"
            className={`${INPUT} mt-1 block w-56`}
          />
        </label>
        <label className="text-sm text-white/70">
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as UserRole)} className={`${INPUT} mt-1 block`}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy || !email.trim()} className={BUTTON}>
          {busy ? "Adding…" : "Add"}
        </button>
        <button type="button" onClick={onCancel} className="text-xs text-white/60 hover:text-white">
          Cancel
        </button>
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}
    </form>
  );
}

function RenamePerson({
  url,
  member,
  onRenamed,
  onCancel,
}: {
  url: string;
  member: Member;
  onRenamed(name: string): void;
  onCancel(): void;
}) {
  const [name, setName] = useState(member.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trimmed = name.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patch<Member>(`${url}/${member.id}`, { name: trimmed });
      onRenamed(updated.name ?? trimmed);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-label={`Rename ${member.email}`}
      className="flex flex-wrap items-center gap-3 rounded-lg border border-cyan/30 bg-cyan/5 p-3 text-sm"
    >
      <label htmlFor="rename" className="text-white">
        Name of {member.email}
      </label>
      <input id="rename" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} className={INPUT} />
      <button type="submit" disabled={busy || !trimmed || trimmed === member.name} className={BUTTON}>
        {busy ? "Saving…" : "Save"}
      </button>
      <button type="button" onClick={onCancel} className="text-xs text-white/60 hover:text-white">
        Cancel
      </button>
      {error && <p className="w-full text-sm text-red-300">{error}</p>}
    </form>
  );
}

/** The temporary password, shown once: the admin passes it on. */
function TemporaryPassword({ handover, onDone }: { handover: Handover; onDone(): void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div role="group" aria-label="Temporary password" className="space-y-2 rounded-lg border border-cyan/30 bg-cyan/5 p-4 text-sm">
      <p className="text-white">
        {handover.added ? `${handover.who} is added.` : `${handover.who}'s password is reset.`} Give them this temporary
        password: it&apos;s shown only once{handover.expiresAt ? `, and works until ${formatDateTime(handover.expiresAt)}` : ""}.
        They choose their own when they sign in.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <code className="rounded bg-navy px-3 py-1.5 font-mono text-base text-cyan select-all">{handover.password}</code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(handover.password).then(() => setCopied(true));
          }}
          className="text-xs text-cyan hover:underline"
        >
          {copied ? "Copied" : "Copy"}
        </button>
        <button type="button" onClick={onDone} className={BUTTON}>
          Done
        </button>
      </div>
    </div>
  );
}
