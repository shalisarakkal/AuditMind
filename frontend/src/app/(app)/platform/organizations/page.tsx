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
import type { OrgStatus, Page, PlatformOrg, PlatformOrgCreated } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";

const PAGE_SIZE = 100;
const COLUMNS = 6;

const INPUT =
  "rounded-md border border-white/15 bg-navy px-3 py-1.5 text-sm text-white placeholder:text-white/40 focus:border-cyan focus:outline-none";
const BUTTON = "rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50";

const STATUS_LABELS: Record<OrgStatus, string> = { active: "Active", archived: "Archived", purging: "Being purged" };
const STATUS_BADGES: Record<OrgStatus, string> = {
  active: "bg-emerald-400/15 text-emerald-300",
  archived: "bg-amber-300/15 text-amber-200",
  purging: "bg-red-400/15 text-red-300",
};

type Pending = { kind: "archive" | "restore"; org: PlatformOrg };

export default function OrganizationsPage() {
  return (
    <SysadminOnly>
      <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
        <Organizations />
      </Suspense>
    </SysadminOnly>
  );
}

function Organizations() {
  const { reloadOrgs } = useApp();
  const list = useListState(PAGE_SIZE, "platform");
  const { data: page, error, loading, reload } = useApi<Page<PlatformOrg>>(`/platform/orgs?${list.apiQuery}`);
  const facets = useApi<{ status: string[] }>("/platform/orgs/facets");
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [purging, setPurging] = useState<PlatformOrg | null>(null);
  const [handover, setHandover] = useState<Handover | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = () => {
    reload();
    facets.reload();
    // The org picker lists every org for the Sysadmin.
    void reloadOrgs();
  };
  const start = () => {
    setActionError(null);
    setNotice(null);
    setHandover(null);
    setPending(null);
    setPurging(null);
  };

  async function confirm(change: Pending) {
    setBusy(true);
    setActionError(null);
    try {
      await api.post(`/platform/orgs/${change.org.id}/${change.kind}`);
      setNotice(
        change.kind === "archive"
          ? `${change.org.name} is archived: read-only for everyone until restored.`
          : `${change.org.name} is restored.`,
      );
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
        title="Organizations"
        total={page?.total}
        noun="organizations"
        orgName="AuditMind"
        filtered={list.hasFilters}
        note="Create an organization with its first admin, who then adds its people. Archive one to make it read-only for everyone; purge an archived one to delete it and everything in it for good."
        action={
          <button
            type="button"
            onClick={() => {
              start();
              setCreating(true);
            }}
            className={BUTTON}
          >
            Create organization
          </button>
        }
      />

      {creating && (
        <CreateOrg
          onCancel={() => setCreating(false)}
          onCreated={(org) => {
            setCreating(false);
            refresh();
            if (org.temporary_password) {
              setHandover({
                who: `${org.name} is created, and its admin ${org.admins[0]}`,
                password: org.temporary_password,
                expiresAt: org.temp_password_expires_at,
                added: true,
              });
            } else {
              setNotice(`${org.name} is created. Its admin ${org.admins[0]} already had an account and signs in with it.`);
            }
          }}
        />
      )}
      {pending && (
        <ConfirmPanel
          label="Confirm"
          message={
            pending.kind === "archive"
              ? `Archive ${pending.org.name}? It becomes read-only for everyone, and nothing in it is purged automatically, until you restore it.`
              : `Restore ${pending.org.name}? Its members can change it again.`
          }
          confirmLabel={pending.kind === "archive" ? "Archive" : "Restore"}
          busy={busy}
          onConfirm={() => void confirm(pending)}
          onCancel={() => setPending(null)}
        />
      )}
      {purging && (
        <PurgeOrg
          org={purging}
          onCancel={() => setPurging(null)}
          onPurged={() => {
            setPurging(null);
            setNotice(`${purging.name} is gone for everyone; the background worker is deleting its data.`);
            refresh();
          }}
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

      <ListToolbar list={list} label="organizations" />
      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable>
          <thead className={THEAD}>
            <tr>
              <SortHeader label="Name" column="name" list={list} defaultSort="name" />
              <SortHeader label="Status" column="status" list={list} />
              <SortHeader label="Members" column="members" list={list} />
              <th className={TH}>Admins</th>
              <SortHeader label="Created" column="created" list={list} />
              <th className={TH}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
            <tr>
              <th />
              <th className={FILTER_CELL}>
                <PickFilter name="status" label="status" list={list} options={facetOptions(facets.data?.status, STATUS_LABELS)} />
              </th>
              <th />
              <th />
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {page.items.length === 0 && <EmptyRow colSpan={COLUMNS} noun="organizations" filtered={list.hasFilters} />}
            {page.items.map((org) => (
              <tr key={org.id} className={`${ROW} align-top`}>
                <td className={`${TD} text-white`}>
                  {org.name}
                  {(org.industry || org.size) && (
                    <p className="text-xs text-white/50">{[org.industry, org.size].filter(Boolean).join(", ")}</p>
                  )}
                </td>
                <td className={TD}>
                  <span className={`rounded px-2 py-0.5 text-xs ${STATUS_BADGES[org.status]}`}>{STATUS_LABELS[org.status]}</span>
                  {org.archived_at && org.status === "archived" && (
                    <p className="mt-1 text-xs text-white/50">since {formatDateTime(org.archived_at)}</p>
                  )}
                </td>
                <td className={TD}>{org.members.toLocaleString("en-US")}</td>
                <td className={`${TD} text-xs`}>{org.admins.length ? org.admins.join(", ") : <span className="text-white/40">none</span>}</td>
                <td className={`${TD} whitespace-nowrap text-xs text-white/60`}>{formatDateTime(org.created_at)}</td>
                <td className={ACTIONS_CELL}>
                  {org.status === "active" && (
                    <button type="button" className={ROW_ACTION} onClick={() => (start(), setPending({ kind: "archive", org }))}>
                      Archive
                    </button>
                  )}
                  {org.status === "archived" && (
                    <>
                      <button type="button" className={ROW_ACTION} onClick={() => (start(), setPending({ kind: "restore", org }))}>
                        Restore
                      </button>
                      <button type="button" className={ROW_ACTION_DANGER} onClick={() => (start(), setPurging(org))}>
                        Purge
                      </button>
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

function CreateOrg({ onCreated, onCancel }: { onCreated(org: PlatformOrgCreated): void; onCancel(): void }) {
  const [values, setValues] = useState({ name: "", industry: "", size: "", admin_email: "", admin_name: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof values) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const optional = (value: string) => value.trim() || undefined;
    try {
      onCreated(
        await api.post<PlatformOrgCreated>("/platform/orgs", {
          name: values.name.trim(),
          industry: optional(values.industry),
          size: optional(values.size),
          admin_email: values.admin_email.trim(),
          admin_name: optional(values.admin_name),
        }),
      );
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const field = (key: keyof typeof values, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="text-sm text-white/70">
      {label}
      <input value={values[key]} onChange={set(key)} className={`${INPUT} mt-1 block w-56`} {...props} />
    </label>
  );

  return (
    <form onSubmit={submit} aria-label="Create organization" className="space-y-3 rounded-lg border border-cyan/30 bg-cyan/5 p-4">
      <div className="flex flex-wrap items-end gap-3">
        {field("name", "Name", { required: true, maxLength: 255 })}
        {field("industry", "Industry", { maxLength: 100, placeholder: "Optional" })}
        {field("size", "Size", { maxLength: 50, placeholder: "Optional" })}
      </div>
      <p className="text-sm text-white/70">
        Its first admin. Someone new gets a temporary password to give them; someone with an account keeps theirs.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        {field("admin_email", "Admin's email", { type: "email", required: true })}
        {field("admin_name", "Admin's name", { maxLength: 100, placeholder: "For a new account" })}
        <button type="submit" disabled={busy || !values.name.trim() || !values.admin_email.trim()} className={BUTTON}>
          {busy ? "Creating…" : "Create"}
        </button>
        <button type="button" onClick={onCancel} className="text-xs text-white/60 hover:text-white">
          Cancel
        </button>
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}
    </form>
  );
}

/** Purging can't be undone: the org's name, typed again, confirms it. */
function PurgeOrg({ org, onPurged, onCancel }: { org: PlatformOrg; onPurged(): void; onCancel(): void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/platform/orgs/${org.id}/purge`, { name });
      onPurged();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label={`Purge ${org.name}`} className="space-y-3 rounded-lg border border-red-400/30 bg-red-400/5 p-4 text-sm">
      <p className="text-white">
        Purge {org.name}? It and everything in it (uploads, assets, findings, reports, its Activity, its members&apos;
        access) is deleted for good. Accounts stay. This can&apos;t be undone.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="purge-name" className="text-white/70">
          Type <span className="font-medium text-white">{org.name}</span> to confirm
        </label>
        <input id="purge-name" value={name} onChange={(e) => setName(e.target.value)} className={INPUT} autoComplete="off" />
        <button
          type="submit"
          disabled={busy || name.trim() !== org.name}
          className="rounded-md bg-red-400/80 px-3 py-1.5 text-sm font-medium text-navy disabled:opacity-50"
        >
          {busy ? "Purging…" : "Purge"}
        </button>
        <button type="button" onClick={onCancel} className="text-xs text-white/60 hover:text-white">
          Cancel
        </button>
      </div>
      {error && <p className="text-red-300">{error}</p>}
    </form>
  );
}
