"use client";

import { Suspense } from "react";

import { PickFilter, SortHeader, TextFilter } from "@/components/ListControls";
import {
  CriticalityBadge,
  DateRangeFilter,
  EmptyRow,
  FILTER_CELL,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW,
  StatusBadge,
  TD,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { CRITICALITY_ORDER, EVENT_LABELS, timing, eventLabel, eventSummary } from "@/lib/activity";
import { formatDateTime } from "@/lib/domain";
import type { ActivityEvent, EventFacets, Page } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useReloadOnImport } from "@/lib/useReloadOnImport";

const PAGE_SIZE = 100;
const COLUMNS = 6;
const capitalized = (value: string) => ({ value, label: value[0].toUpperCase() + value.slice(1) });
const CRITICALITY_OPTIONS = CRITICALITY_ORDER.map(capitalized);

// The list reads its sort and filters from the page address.
export default function ActivityPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading…</p>}>
      <Activity />
    </Suspense>
  );
}

function Activity() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<ActivityEvent>>(`/orgs/${org.id}/events?${list.apiQuery}`);
  const facets = useApi<EventFacets>(`/orgs/${org.id}/events/facets`);
  useReloadOnImport(reload);
  useReloadOnImport(facets.reload);

  const typeOptions = (facets.data?.type ?? []).map((t) => ({ value: t, label: EVENT_LABELS[t] ?? t }));
  const resultOptions = (facets.data?.result ?? []).map(capitalized);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity"
        total={page?.total}
        noun="events"
        orgName={org.name}
        filtered={list.hasFilters}
        note="Uploads, archives, restores and purges, sign-ins, and changes to settings and people. Nothing here can be changed or deleted; old events are removed after the retention period set in Settings."
      />
      <ListToolbar list={list} label="activity">
        <DateRangeFilter list={list} label="When" />
      </ListToolbar>

      <StatusMessage loading={loading && !page} error={error} />
      {page && (
        <ListTable>
          <thead className={THEAD}>
            <tr>
              <SortHeader label="When" column="when" list={list} defaultSort="when" defaultOrder="desc" />
              <SortHeader label="Event" column="event" list={list} />
              <SortHeader label="Item" column="item" list={list} />
              <SortHeader label="Who" column="who" list={list} />
              <SortHeader label="Result" column="result" list={list} />
              <SortHeader label="Criticality" column="criticality" list={list} />
            </tr>
            <tr>
              <th />
              <th className={FILTER_CELL}>
                <PickFilter name="type" label="event" list={list} options={typeOptions} />
              </th>
              <th className={FILTER_CELL}>
                <TextFilter name="item" label="item" list={list} />
              </th>
              <th className={FILTER_CELL}>
                <TextFilter name="who" label="who" list={list} />
              </th>
              <th className={FILTER_CELL}>
                <PickFilter name="result" label="result" list={list} options={resultOptions} />
              </th>
              <th className={FILTER_CELL}>
                <PickFilter name="criticality" label="criticality" list={list} options={CRITICALITY_OPTIONS} />
              </th>
            </tr>
          </thead>
          <tbody>
            {page.items.length === 0 && <EmptyRow colSpan={COLUMNS} noun="events" filtered={list.hasFilters} />}
            {page.items.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </tbody>
        </ListTable>
      )}
      {page && <Pager offset={list.offset} limit={PAGE_SIZE} total={page.total} onChange={list.setOffset} />}
    </div>
  );
}

function EventRow({ event }: { event: ActivityEvent }) {
  const took = timing(event);
  const summary = eventSummary(event);
  return (
    <tr className={`${ROW} align-top`}>
      <td className={`${TD} whitespace-nowrap text-xs text-white/60`}>
        {formatDateTime(event.started_at)}
        {took && <p>{took}</p>}
      </td>
      <td className={`${TD} text-white`}>
        {eventLabel(event)}
        {summary && <p className="text-xs text-white/50">{summary}</p>}
      </td>
      <td className={TD}>{event.item ?? "—"}</td>
      <td className={TD}>{event.actor_label}</td>
      <td className={TD}>
        <StatusBadge status={event.outcome} />
      </td>
      <td className={TD}>
        <CriticalityBadge criticality={event.criticality} />
      </td>
    </tr>
  );
}
