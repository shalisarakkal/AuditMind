"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { GenerateReportModal } from "@/components/GenerateReportModal";
import { PickFilter, SortHeader, TextFilter, facetOptions } from "@/components/ListControls";
import { FilterChips } from "@/components/FilterChips";
import ConfirmPanel from "@/components/ConfirmPanel";
import {
  ACTIONS_CELL,
  DateRangeFilter,
  EmptyRow,
  FILTER_CELL,
  ListTable,
  ListToolbar,
  PageHeader,
  ROW,
  ROW_ACTION_DANGER,
  ROW_ACTION_VIEW,
  SELECT_CELL,
  SelectBox,
  SelectPageBox,
  SelectionAction,
  SelectionBar,
  StatusBadge,
  TD,
  TH,
  THEAD,
} from "@/components/ListPage";
import Pager from "@/components/Pager";
import { ReportViewer } from "@/components/ReportViewer";
import StatusMessage from "@/components/StatusMessage";
import { useApp } from "@/context/AppContext";
import { apiClient } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/domain";
import { downloadReport, downloadReportsZip, reportErrorMessage } from "@/lib/report";
import type { AuditReport, Page, ReportFacets, UserRole } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useListState } from "@/lib/useListState";
import { useSelection } from "@/lib/useSelection";

const PAGE_SIZE = 100;

function canGenerate(role: UserRole): boolean {
  return role === "admin" || role === "auditor";
}

export default function ReportsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-white/60">Loading reports…</p>}>
      <Reports />
    </Suspense>
  );
}

function Reports() {
  const { selectedOrg } = useApp();
  const org = selectedOrg!;
  const writer = canGenerate(org.role);
  const admin = org.role === "admin";
  const list = useListState(PAGE_SIZE, org.id);
  const { data: page, error, loading, reload } = useApi<Page<AuditReport>>(`/orgs/${org.id}/reports?${list.apiQuery}`);
  const facets = useApi<ReportFacets>(`/orgs/${org.id}/reports/facets`);
  const capabilities = useApi<{ rule_based_test_enabled: boolean }>(`/orgs/${org.id}/reports/capabilities`);
  const selection = useSelection(list, org.id);
  const [modalMode, setModalMode] = useState<"ai" | "rule_based_test" | null>(null);
  const [selectedReport, setSelectedReport] = useState<AuditReport | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: "cancel" | "delete"; report: AuditReport } | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleteBusy, setBulkDeleteBusy] = useState(false);
  const [bulkDeleteError, setBulkDeleteError] = useState<string | null>(null);
  const [bulkDownloadBusy, setBulkDownloadBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const selectedId = selectedReport?.id;
  const selectedStatus = selectedReport?.status;

  useEffect(() => {
    if (!selectedId || (selectedStatus !== "pending" && selectedStatus !== "running")) return;
    let active = true;
    let fetching = false;
    const interval = setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try {
        const full = await apiClient.get<AuditReport>(`/orgs/${org.id}/reports/${selectedId}`);
        if (active) setSelectedReport((previous) => previous?.id === selectedId ? full : previous);
      } catch (err) {
        console.error("Failed to refresh report:", err);
      } finally {
        fetching = false;
      }
    }, 3000);
    return () => { active = false; clearInterval(interval); };
  }, [org.id, selectedId, selectedStatus]);

  // Periodic poll if any report is running or pending
  useEffect(() => {
    if (!page?.items) return;
    const hasRunning = page.items.some((r) => r.status === "pending" || r.status === "running");
    if (!hasRunning) return;

    const interval = setInterval(reload, 4000);
    return () => clearInterval(interval);
  }, [page, reload]);

  const generationAttempt = useRef<{ fingerprint: string; key: string } | null>(null);

  async function handleGenerate(payload: { title: string; frameworks: string[] }, mode: "ai" | "rule_based_test") {
    const endpoint = mode === "ai" ? "generate" : "rule-based-test";
    const fingerprint = JSON.stringify([org.id, mode, payload]);
    if (generationAttempt.current?.fingerprint !== fingerprint) {
      generationAttempt.current = { fingerprint, key: crypto.randomUUID() };
    }
    await apiClient.post(`/orgs/${org.id}/reports/${endpoint}`, payload,
      mode === "ai" ? { headers: { "Idempotency-Key": generationAttempt.current.key } } : undefined);
    generationAttempt.current = null;
    reload();
  }

  async function handleDownload(reportId: string, title: string, format: "html" | "pdf") {
    setDownloadError(null);
    try {
      await downloadReport(org.id, reportId, title, format);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Failed to download report");
    }
  }

  async function handleBulkDownload() {
    if (bulkDownloadBusy) return;
    setBulkDownloadBusy(true);
    setDownloadError(null);
    try {
      await downloadReportsZip(org.id, selection.ids);
      selection.clear();
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Failed to download selected reports");
    } finally {
      setBulkDownloadBusy(false);
    }
  }

  async function handleConfirmedAction() {
    if (!confirmAction) return;
    const { type, report } = confirmAction;
    setActionId(report.id);
    setActionError(null);
    try {
      if (type === "cancel") {
        await apiClient.post(`/orgs/${org.id}/reports/${report.id}/cancel`);
      } else {
        await apiClient.delete(`/orgs/${org.id}/reports/${report.id}`);
      }
      if (selectedReport?.id === report.id) {
        setSelectedReport(null);
      }
      setConfirmAction(null);
      reload();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : `Failed to ${type} report`);
    } finally {
      setActionId(null);
    }
  }

  async function handleBulkDelete() {
    setBulkDeleteBusy(true);
    setBulkDeleteError(null);
    try {
      await apiClient.post(`/orgs/${org.id}/reports/bulk-delete`, { ids: selection.ids });
      selection.clear();
      setBulkDeleteOpen(false);
      reload();
    } catch (err) {
      setBulkDeleteError(err instanceof Error ? err.message : "Failed to delete selected reports");
    } finally {
      setBulkDeleteBusy(false);
    }
  }

  async function viewReportDetails(reportId: string) {
    try {
      const full = await apiClient.get<AuditReport>(`/orgs/${org.id}/reports/${reportId}`);
      setSelectedReport(full);
    } catch (err) {
      console.error("Failed to fetch report details:", err);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Reports"
        total={page?.total}
        noun="reports"
        orgName={org.name}
        filtered={list.hasFilters}
        note="AI-generated assessments evaluate active findings against selected CIS/NIST/ISO standards."
        action={
          writer && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setModalMode("ai")}
                className="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50"
              >
                + Generate report
              </button>
              {capabilities.data?.rule_based_test_enabled && (
                <button
                  type="button"
                  onClick={() => setModalMode("rule_based_test")}
                  className="rounded-md border border-amber-400/40 px-3 py-1.5 text-sm font-medium text-amber-200 hover:bg-amber-400/10"
                >
                  + Rule-based test report
                </button>
              )}
            </div>
          )
        }
      />

      {downloadError && <p role="alert" className="text-sm text-red-300">{downloadError}</p>}

      {selectedReport && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <button
              onClick={() => setSelectedReport(null)}
              className="flex items-center gap-1 text-xs text-cyan-400 hover:underline"
            >
              ← Back to reports list
            </button>
          </div>
          <ReportViewer
            report={selectedReport}
            onDownloadHtml={() => void handleDownload(selectedReport.id, selectedReport.title, "html")}
            onDownloadPdf={() => void handleDownload(selectedReport.id, selectedReport.title, "pdf")}
          />
        </div>
      )}

      {!selectedReport && (
        <div className="space-y-4">
          <FilterChips
            name="frameworks"
            label="Frameworks"
            options={facetOptions(facets.data?.frameworks)}
            list={list}
          />
          <ListToolbar list={list} label="reports">
            <label className="text-xs text-white/70">Assessment completeness
              <select aria-label="Assessment completeness" className="ml-2 rounded border border-white/20 bg-[#0e1626] p-2"
                value={list.values("assessment_status")[0] ?? ""}
                onChange={event => list.setValues("assessment_status", event.target.value ? [event.target.value] : [])}>
                <option value="">All assessments (including legacy)</option>
                <option value="complete">Complete AI assessment</option>
                <option value="partial">Partial AI assessment</option>
              </select>
            </label>
            <DateRangeFilter list={list} label="Created" />
          </ListToolbar>

          <SelectionBar selection={selection}>
            <SelectionAction onClick={() => void handleBulkDownload()} disabled={bulkDownloadBusy}>
              {bulkDownloadBusy ? "Preparing ZIP…" : "Download selected PDFs"}
            </SelectionAction>
            {admin && (
              <SelectionAction onClick={() => { setBulkDeleteOpen(true); setBulkDeleteError(null); }} danger>
                Delete selected
              </SelectionAction>
            )}
          </SelectionBar>
          {bulkDeleteOpen && (
            <div className="space-y-2">
              <ConfirmPanel
                label="Delete selected reports"
                message={<>Permanently delete <strong>{selection.count} selected {selection.count === 1 ? "report" : "reports"}</strong>? This can&apos;t be undone.</>}
                confirmLabel={bulkDeleteBusy ? "Deleting…" : "Delete reports"}
                onConfirm={() => void handleBulkDelete()}
                onCancel={() => { setBulkDeleteOpen(false); setBulkDeleteError(null); }}
                busy={bulkDeleteBusy}
                danger
              />
              {bulkDeleteError && <p role="alert" className="text-sm text-red-300">{bulkDeleteError}</p>}
            </div>
          )}
          {confirmAction && (
            <div className="space-y-2">
              <ConfirmPanel
                label={confirmAction.type === "cancel" ? "Cancel report generation" : "Delete report"}
                message={
                  confirmAction.type === "cancel" ? (
                    <>Cancel generation of <strong>{confirmAction.report.title}</strong>? This stops the report job.</>
                  ) : (
                    <>Permanently delete <strong>{confirmAction.report.title}</strong>? This can&apos;t be undone.</>
                  )
                }
                confirmLabel={
                  actionId === confirmAction.report.id
                    ? confirmAction.type === "cancel" ? "Cancelling…" : "Deleting…"
                    : confirmAction.type === "cancel" ? "Cancel generation" : "Delete for good"
                }
                onConfirm={() => void handleConfirmedAction()}
                onCancel={() => { setConfirmAction(null); setActionError(null); }}
                busy={actionId === confirmAction.report.id}
                danger={confirmAction.type === "delete"}
              />
              {actionError && <p role="alert" className="text-sm text-red-300">{actionError}</p>}
            </div>
          )}
          <StatusMessage loading={loading && !page} error={error} />

          <ListTable>
            <thead className={THEAD}>
              <tr className={THEAD}>
                <th className={SELECT_CELL}>
                  <SelectPageBox
                    selection={selection}
                    rows={(page?.items ?? [])
                      .filter((report) =>
                        report.status === "completed" || report.status === "generated" || (admin && report.status === "failed"))
                      .map((report) => ({ id: report.id, name: report.title }))}
                  />
                </th>
                <SortHeader label="Title" column="title" list={list} />
                <SortHeader label="Frameworks" column="frameworks" list={list} />
                <SortHeader label="Status" column="status" list={list} />
                <SortHeader label="Score" column="score" list={list} />
                <SortHeader label="Created" column="created" list={list} defaultSort="created" defaultOrder="desc" />
                <th className={`${TH} text-right`}>Actions</th>
              </tr>
              <tr>
                <th />
                <th className={FILTER_CELL}><TextFilter name="title" label="title" list={list} /></th>
                <th className={FILTER_CELL}><TextFilter name="frameworks" label="frameworks" list={list} /></th>
                <th className={FILTER_CELL}>
                  <PickFilter
                    name="status"
                    label="status"
                    list={list}
                    options={facetOptions(facets.data?.status, {
                      pending: "Pending",
                      running: "Running",
                      completed: "Completed",
                      generated: "Generated",
                      failed: "Failed",
                    })}
                  />
                </th>
                <th className={FILTER_CELL}><TextFilter name="score" label="score" list={list} /></th>
                <th />
                <th />
              </tr>
            </thead>
            <tbody>
              {loading && !page ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-white/50">
                    Loading reports...
                  </td>
                </tr>
              ) : error ? null : !page?.items || page.items.length === 0 ? (
                <EmptyRow colSpan={7} noun="reports" filtered={list.hasFilters} />
              ) : (
                page.items.map((r) => {
                  const isCompleted = r.status === "completed" || r.status === "generated";
                  const isRunning = r.status === "pending" || r.status === "running";
                  const score = r.overall_score;
                  const errorMessage = reportErrorMessage(r.error_message);

                  return (
                    <tr key={r.id} className={ROW}>
                      <td className={SELECT_CELL}>
                        <SelectBox
                          selection={selection}
                          id={r.id}
                          name={r.title}
                          disabled={!isCompleted && !(admin && r.status === "failed")}
                        />
                      </td>
                      <td className={TD}>
                        <button
                          onClick={() => viewReportDetails(r.id)}
                          className="font-medium text-white hover:text-cyan-400 text-left transition-colors"
                        >
                          {r.title}
                        </button>
                        {errorMessage && <div className="text-xs text-red-400 mt-0.5">{errorMessage}</div>}
                      </td>
                      <td className={TD}>
                        <span className="font-mono text-xs text-white/70">
                          {r.assessment_type === "rule_based_test" ? "Rule-based test · no framework assessment" : r.frameworks || "CIS, NIST, ISO"}
                        </span>
                      </td>
                      <td className={TD}>
                        <StatusBadge status={r.status} />
                      </td>
                      <td className={TD}>
                        {score != null ? (
                          <span className="font-semibold text-cyan-400">{score}/100 <span className="block text-xs font-normal">{r.assessment_type === "rule_based_test" ? "Deterministic test" : "AI advisory"}</span></span>
                        ) : r.assessment_status === "partial" ? (
                          <span className="text-xs text-white/70">Partial AI assessment — overall score unavailable</span>
                        ) : isRunning ? (
                          <span className="text-xs text-white/40">Evaluating...</span>
                        ) : (
                          <span className="text-xs text-white/40">—</span>
                        )}
                      </td>
                      <td className={TD}>
                        <span className="whitespace-nowrap text-xs text-white/60">{formatDateTime(r.created_at)}</span>
                      </td>
                      <td className={ACTIONS_CELL}>
                        {isCompleted && (
                          <>
                            <button
                              type="button"
                              onClick={() => viewReportDetails(r.id)}
                              className={ROW_ACTION_VIEW}
                            >
                              View
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDownload(r.id, r.title, "html")}
                              className="text-xs text-white/70 hover:text-white transition-colors"
                            >
                              Download HTML
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDownload(r.id, r.title, "pdf")}
                              className="text-xs text-white/70 hover:text-white transition-colors"
                            >
                              Download PDF
                            </button>
                          </>
                        )}
                        {writer && isRunning && (
                          <button
                            type="button"
                            disabled={actionId === r.id}
                            onClick={() => { setConfirmAction({ type: "cancel", report: r }); setActionError(null); }}
                            className="text-xs text-cyan hover:underline"
                          >
                            Cancel
                          </button>
                        )}
                        {org.role === "admin" && !isRunning && (
                          <button
                            type="button"
                            disabled={actionId === r.id}
                            onClick={() => { setConfirmAction({ type: "delete", report: r }); setActionError(null); }}
                            className={ROW_ACTION_DANGER}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </ListTable>

          {page && <Pager total={page.total} limit={PAGE_SIZE} offset={list.offset} onChange={list.setOffset} />}
        </div>
      )}

      <GenerateReportModal
        key={org.id}
        orgId={org.id}
        orgName={org.name}
        canApprove={admin}
        isOpen={modalMode !== null}
        mode={modalMode ?? "ai"}
        onClose={() => setModalMode(null)}
        onGenerate={handleGenerate}
      />
    </div>
  );
}
