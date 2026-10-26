"use client";

import { Fragment, Suspense, useState } from "react";

import ImportButton from "@/components/ImportButton";
import ImportStatus from "@/components/ImportStatus";
import FindingWorkflowDialog from "@/components/FindingWorkflowDialog";
import FindingReference from "@/components/FindingReference";
import FindingActionDialog from "@/components/FindingActionDialog";
import AddFindingDialog from "@/components/AddFindingDialog";
import { formatDeadline, WORKFLOW_LABELS, WORKFLOW_OPTIONS } from "@/lib/findingWorkflow";
import BulkConfirm, { type BulkRequest, selectedText } from "@/components/BulkConfirm";
import { ArchiveButtons } from "@/components/JobButton";
import JobConfirm, { type JobRequest, undoRequest } from "@/components/JobConfirm";
import JobStatus from "@/components/JobStatus";
import {
  ACTIONS_CELL,
  DateRangeFilter,
  EmptyRow,
  FilterChips,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW_ACTION_VIEW,
  SELECT_CELL,
  SelectBox,
  SelectionAction,
  SelectionBar,
  SelectPageBox,
  StatusBadge,
  THEAD,
} from "@/components/ListPage";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import {
  DOMAIN_LABELS,
  DOMAIN_ORDER,
  SEVERITY_BADGES,
  SEVERITY_ORDER,
  canWrite,
  formatDateTime,
} from "@/lib/domain";
import type { EventDetails, FindingFacets, FindingListItem, FindingPage, ImportProfile } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const SEVERITY_OPTIONS = SEVERITY_ORDER.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }));
const DOMAIN_OPTIONS = DOMAIN_ORDER.map((d) => ({ value: d, label: DOMAIN_LABELS[d] }));

// The list reads its sort and filters from the page address.
export default function FindingsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Findings />
    </Suspense>
  );
}

function Findings() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canWrite(org.role);
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<FindingPage>(`/orgs/${org.id}/findings?${list.apiQuery}`);
  const facets = useApi<FindingFacets>(`/orgs/${org.id}/findings/facets`);
  const profiles = useApi<ImportProfile[]>(writer ? `/orgs/${org.id}/import-profiles` : null);
  useReloadOnImport(reload);
  useReloadOnImport(facets.reload);
  const [confirming, setConfirming] = useState<JobRequest | null>(null);
  const workflowScope = `${org.id}?${list.filterKey}`;
  const selection = useSelection(list, org.id, 500);
  useReloadOnImport(selection.clear);
  const [workflow, setWorkflow] = useState<{ scope: string; ids: string[]; names: string[] } | null>(null);
  const [bulk, setBulk] = useState<{ request: BulkRequest; ids: string[]; names: string[]; scope: string } | null>(null);
  const [addingOrg, setAddingOrg] = useState<string | null>(null);
  const hasManual = facets.data?.has_manual_findings ?? page?.items.some(f => f.scan_id === null) ?? false;
  // The event log finding whose details are open.
  const [opened, setOpened] = useState<string | null>(null);
  const nameOf = (f: FindingListItem) => f.description ?? f.category ?? "finding";
  const pickable = (f: FindingListItem) => !loading && !f.archiving;
  const allManual = selection.count > 0 && selection.ids.every(id => {
    const current = page?.items.find(f => f.id === id);
    return current ? current.scan_id === null && !current.archiving : selection.metadata(id)?.manual === true;
  });
  const archiveSelected = () => {
    if (loading || !allManual) return;
    setBulk({ ids: selection.ids, names: selection.names(selection.ids), scope: workflowScope, request: {
      action: "archive",
      itemType: "finding",
      label: "Archive selected findings",
      message: (
        <>
          Archive <strong>{selectedText(selection.count, "finding")}</strong>? They leave every list and score. Each can be
          restored from Archived until it&apos;s purged.
          <span role="list" className="mt-2 block">{selection.names(selection.ids).slice(0, 10).map((name, index) => <span role="listitem" className="block" key={selection.ids[index]}>{name}</span>)}</span>
          {selection.count > 10 && <span className="block">and {selection.count - 10} more selected findings.</span>}
        </>
      ),
      confirmLabel: `Archive ${selection.count} ${selection.count === 1 ? "finding" : "findings"}`,
    }});
  };
  // Only findings added by hand are archived one by one; imported ones go
  // with their upload or asset (a re-import would bring them back).
  const archive = (f: FindingListItem) => {
    const name = f.description ?? f.category ?? "this finding";
    setConfirming({
      path: `/orgs/${org.id}/findings/${f.id}/archive`,
      label: `Archive ${name}`,
      message: (
        <>
          Archive only this finding: <strong>{name}</strong>?
          <span className="my-2 block break-all">Finding ID: {f.id}</span>
          <span className="mb-2 block">This archives 1 finding only. Other checked findings are not included.</span>
          It leaves every list and score. You can restore it from Archived until it&apos;s
          purged.
        </>
      ),
      confirmLabel: "Archive 1 finding",
    });
  };

  return (
    <div className="min-w-0 space-y-6">
      <PageHeader
        title="Findings"
        total={page?.total}
        noun="findings"
        orgName={org.name}
        filtered={list.hasFilters}
        note={
          writer &&
          "A native Nessus export (.nessus); CSV/JSON generic findings (hostname and/or ip, domain, severity, category, description, source); or a tool export such as an endpoint agent or network scan, which records the hosts as assets too. Pick the file, then its source."
        }
        action={
          writer && (
            <div className="flex flex-wrap gap-3"><button type="button" className="rounded-md border border-cyan px-4 py-2 text-sm text-cyan" onClick={() => setAddingOrg(org.id)}>Add finding</button><ImportButton orgId={org.id} kind="findings" accept=".csv,.json,.nessus" label="Upload file" profiles={profiles.data} /></div>
          )
        }
      />
      <ImportStatus page="findings" />
      <JobStatus />
      {writer && addingOrg === org.id && <AddFindingDialog key={org.id} orgId={org.id} orgName={org.name} onClose={() => setAddingOrg(null)} onSaved={() => { reload(); facets.reload(); selection.clear(); }} />}
      {workflow?.scope === workflowScope && <FindingWorkflowDialog key={workflowScope} orgId={org.id} orgName={org.name} role={org.role}
        ids={workflow.ids} names={workflow.names} onClose={() => setWorkflow(null)} onSaved={() => { reload(); facets.reload(); selection.clear(); }} />}
      {writer && confirming && <FindingActionDialog title={confirming.path.endsWith('/archive') ? "Archive this finding" : "Confirm finding action"} orgName={org.name} onClose={() => setConfirming(null)}><JobConfirm request={confirming} onClose={() => setConfirming(null)} /></FindingActionDialog>}

      <div className="space-y-3">
        <ListToolbar list={list} label="findings">
          <DateRangeFilter list={list} label="Added" />
          <label className="min-w-0 max-w-full text-xs text-white/70">Overdue<select aria-label="Overdue" value={list.text("overdue")} onChange={e => list.setText("overdue", e.target.value)} className="max-w-full rounded border border-white/20 bg-navy p-1 text-white sm:ml-2">
            <option value="">All deadlines</option><option value="due">Remediation overdue</option><option value="risk_review">Risk review overdue</option>
          </select></label>
        </ListToolbar>
        {writer && !hasManual && <p className="text-xs text-white/70">No active manual findings are available to archive. Use Add finding for manual entry. Uploaded findings are archived with their upload or asset, not individually.</p>}
        <p className="text-xs text-white/70">Search an exact Finding ID to locate it in this organization. Archived or purged findings do not appear in this active list.</p>
        {list.text("finding_id") && <p className="text-sm">Finding ID: <span className="break-all">{list.text("finding_id")}</span></p>}
        {facets.error && <p role="alert" className="text-sm text-red-300">Could not load filter options: {facets.error} <button type="button" className="text-cyan underline" onClick={facets.reload}>Retry filter options</button></p>}
        {writer && (
          <SelectionBar selection={selection}>
            <span className="text-white/80">Actions for selected findings</span>
            <span className="text-xs text-white/60">Clear selection to use individual row actions.</span>
            <SelectionAction disabled={loading || selection.count > 100} onClick={() => { if (selection.count <= 100) { setBulk(null); setWorkflow({ scope: workflowScope, ids: selection.ids, names: selection.names(selection.ids) }); } }}>Update selected workflow</SelectionAction>
            <SelectionAction disabled={loading || !allManual} onClick={archiveSelected}>Archive selected</SelectionAction>
            {selection.count > 100 && <p className="text-xs text-white/70">Workflow updates support up to 100 findings. Reduce the selection to update workflow; archiving supports up to 500 eligible manual findings.</p>}
            {!allManual && <p className="text-xs text-white/70">Archive selected requires every selected finding to be manually added and available. Imported findings are archived with their upload or asset. No findings will be silently skipped.</p>}
          </SelectionBar>
        )}
        {writer && bulk?.scope === workflowScope && <FindingActionDialog title="Archive selected findings" orgName={org.name} onClose={() => setBulk(null)}><BulkConfirm request={bulk.request} selection={{ ...selection, ids: bulk.ids, count: bulk.ids.length, names: ids => ids.map(id => bulk.names[bulk.ids.indexOf(id)] ?? id) }} onClose={() => setBulk(null)} /></FindingActionDialog>}
        {page && (
          <FilterChips list={list} name="domain" label="Domain" options={DOMAIN_OPTIONS} counts={page.domain_counts} />
        )}
      </div>

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable fixed className="min-w-[1900px]">
            <thead className={THEAD}>
              <tr>
                {writer && (
                  <th className={SELECT_CELL}>
                    <SelectPageBox selection={selection} rows={page.items.filter(pickable).map((f) => ({ id: f.id, name: nameOf(f), metadata: { manual: f.scan_id === null } }))} />
                  </th>
                )}
                <SortHeader label="Severity" column="severity" list={list} defaultSort="severity" className="w-32" />
                <SortHeader label="Finding" column="finding" list={list} />
                <SortHeader label="Domain" column="domain" list={list} className="w-44" />
                <SortHeader label="Asset" column="asset" list={list} className="w-44" />
                <SortHeader label="Source" column="source" list={list} className="w-36" />
                <SortHeader label="Status" column="workflow_status" list={list} className="w-40" />
                <SortHeader label="Assignee" column="assignee" list={list} className="w-44" />
                <SortHeader label="Due" column="due_date" list={list} className="w-32" />
                <SortHeader label="Risk review" column="risk_review_date" list={list} className="w-44" />
                <SortHeader label="Added" column="created" list={list} className="w-40" />
                <th className="sticky right-0 z-20 w-28 bg-navy px-4 py-2 text-right sm:w-44">Actions</th>
              </tr>
              <tr>
                {writer && <th />}
                <th className="px-4 pb-2">
                  <PickFilter name="severity" label="severity" list={list} options={SEVERITY_OPTIONS} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="finding" label="finding" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="domain" label="domain" list={list} options={DOMAIN_OPTIONS} />
                </th>
                <th className="px-4 pb-2">
                  <TextFilter name="asset" label="asset" list={list} />
                </th>
                <th className="px-4 pb-2">
                  <PickFilter name="source" label="source" list={list} options={facetOptions(facets.data?.source)} />
                </th>
                <th className="px-4 pb-2"><PickFilter name="workflow_status" label="status" list={list} options={WORKFLOW_OPTIONS.filter(option => !facets.data?.workflow_status || facets.data.workflow_status.includes(option.value as keyof typeof WORKFLOW_LABELS))} /></th>
                <th className="px-4 pb-2"><PickFilter name="assignee" label="assignee" list={list} options={facets.data?.assignee ?? []} /></th>
                <th /><th />
                <th />
                <th className="sticky right-0 z-20 bg-navy" />
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 && (
                <EmptyRow colSpan={writer ? 12 : 11} noun="findings" filtered={list.hasFilters} />
              )}
              {page.items.map((f) => (
                <Fragment key={f.id}>
                <tr className="border-t border-white/10 text-white/80">
                  {writer && (
                    <td className={SELECT_CELL}>
                      <SelectBox selection={selection} id={f.id} name={nameOf(f)} metadata={{ manual: f.scan_id === null }} disabled={!pickable(f)} />
                    </td>
                  )}
                  <td className="px-4 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs capitalize ${SEVERITY_BADGES[f.severity]}`}>
                      {f.severity}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <p className="text-white">{f.description ?? f.category ?? "—"}</p>
                    {f.description && f.category && <p className="text-xs text-white/50">{f.category}</p>}
                    <details className="mt-1 text-xs"><summary>Finding ID</summary><FindingReference orgId={org.id} id={f.id} copy /></details>
                    {f.event_count != null && (
                      <p className="mt-1 text-xs text-white/60">
                        {f.event_count.toLocaleString("en-US")} {f.event_count === 1 ? "event" : "events"}
                        {f.first_seen && f.last_seen && `, ${formatDateTime(f.first_seen)} to ${formatDateTime(f.last_seen)}`}
                        {/* Under the text, not in the actions column: that's
                            shown only to writers, and everyone may look
                            (docs/UI_CONVENTIONS.md). */}
                        {f.details && (
                          <button
                            type="button"
                            aria-expanded={opened === f.id}
                            onClick={() => setOpened(opened === f.id ? null : f.id)}
                            className={`ml-3 ${ROW_ACTION_VIEW}`}
                          >
                            {opened === f.id ? "Hide details" : "Details"}
                          </button>
                        )}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-2">{DOMAIN_LABELS[f.domain]}</td>
                  <td className="truncate px-4 py-2" title={f.asset_cloud_id ?? undefined}>
                    {f.asset_hostname ?? f.asset_ip ?? f.asset_cloud_id ?? "—"}
                  </td>
                  <td className="truncate px-4 py-2">{f.source ?? "—"}</td>
                  <td className="px-4 py-2"><StatusBadge status={f.workflow_status ?? "open"} label={WORKFLOW_LABELS[f.workflow_status ?? "open"]} /></td>
                  <td className="break-words px-4 py-2 text-xs">{f.assignee_id ? f.assignee_label || "Assignee unavailable" : "Unassigned"}</td>
                  <td className="px-4 py-2 text-xs">{formatDeadline(f.due_date, f.due_expires_at)}</td>
                  <td className="px-4 py-2 text-xs">{formatDeadline(f.risk_review_date, f.risk_review_expires_at)}</td>
                  <td className="px-4 py-2 text-xs text-white/60">{formatDateTime(f.created_at)}</td>
                    <td className={`${ACTIONS_CELL} sticky right-0 z-10 bg-navy`}>
                      <div className="flex flex-wrap justify-end gap-3">
                      <button type="button" disabled={loading || !!f.archiving || selection.count > 0} title={selection.count ? "Clear selection to use individual row actions." : undefined} className={`${ROW_ACTION_VIEW} disabled:opacity-50`} onClick={() => { setBulk(null); setWorkflow({ scope: workflowScope, ids: [f.id], names: [nameOf(f)] }); }}>Workflow</button>
                      {writer && f.scan_id === null && (
                        <ArchiveButtons
                          itemId={f.id}
                          disabled={loading || selection.count > 0}
                          disabledTitle="Clear selection to use individual row actions."
                          name={f.description ?? f.category ?? "finding"}
                          archiving={f.archiving}
                          batchId={f.archiving_batch_id}
                          onArchive={() => archive(f)}
                          onUndo={(batchId) => setConfirming(undoRequest(org.id, batchId, f.description ?? f.category ?? "finding"))}
                        />
                      )}
                      </div>
                    </td>
                </tr>
                {opened === f.id && f.details && (
                  <tr className="text-white/80">
                    <td colSpan={writer ? 12 : 11} className="px-4 pb-4">
                      <EventDetailsPanel details={f.details} />
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}

/** What an event log finding keeps about its events: who and where most
 * often, and a few of the events themselves. */
function EventDetailsPanel({ details }: { details: EventDetails }) {
  const top = (title: string, part?: { distinct: string; top: { value: string; events: number }[] }) =>
    part && part.top.length > 0 ? (
      <div>
        <p className="text-xs uppercase tracking-wide text-white/50">
          {title} ({part.distinct} in all)
        </p>
        <ul className="mt-1 space-y-0.5 text-xs">
          {part.top.map((entry) => (
            <li key={entry.value} className="flex justify-between gap-4">
              <span className="truncate">{entry.value}</span>
              <span className="text-white/50">{entry.events.toLocaleString("en-US")}</span>
            </li>
          ))}
        </ul>
      </div>
    ) : null;
  return (
    <div role="region" aria-label="Event details" className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-3">
      <div className="grid gap-4 sm:grid-cols-2">
        {top("Most frequent actors", details.actors)}
        {top(`Most frequent ${details.scopes?.name ?? "scopes"}`, details.scopes)}
      </div>
      {details.examples && details.examples.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wide text-white/50">Example events</p>
          <pre className="mt-1 max-h-64 overflow-auto rounded bg-navy p-2 text-xs text-white/70">
            {details.examples.map((example) => JSON.stringify(example)).join("\n")}
          </pre>
        </div>
      )}
    </div>
  );
}
