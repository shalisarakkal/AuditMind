"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ReportViewer } from "@/components/ReportViewer";
import { useApp } from "@/context/AppContext";
import { apiClient } from "@/lib/apiClient";
import { downloadReport } from "@/lib/report";
import type { AuditReport } from "@/lib/types";

export default function ReportDetailPage() {
  const params = useParams();
  const reportId = params?.id as string;
  const { selectedOrg: currentOrg } = useApp();
  const [report, setReport] = useState<AuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const reportRef = useRef<AuditReport | null>(null);

  useEffect(() => {
    reportRef.current = report;
  }, [report]);

  useEffect(() => {
    if (!currentOrg || !reportId) {
      setReport(null);
      setError(null);
      setLoading(false);
      return;
    }

    const orgId = currentOrg.id;
    let isMounted = true;
    async function fetchReport() {
      try {
        const data = await apiClient.get<AuditReport>(`/orgs/${orgId}/reports/${reportId}`);
        if (isMounted) {
          setReport(data);
          setError(null);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to load report");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchReport();

    // Poll while the report is still being generated.
    const interval = setInterval(() => {
      const status = reportRef.current?.status;
      if (status === "pending" || status === "running") {
        fetchReport();
      }
    }, 3000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [currentOrg, reportId]);

  async function handleDownload(format: "html" | "pdf") {
    if (!currentOrg || !report) return;
    try {
      setDownloadError(null);
      await downloadReport(currentOrg.id, report.id, report.title, format);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Failed to download report");
    }
  }

  if (loading) {
    return (
      <div className="py-12 text-center text-white/50">
        <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent mr-3 align-middle" />
        Loading audit report...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center">
        <h2 className="text-lg font-semibold text-red-400">Report not found</h2>
        <p className="mt-2 text-sm text-white/60">{error || "The requested report could not be found."}</p>
        <Link
          href="/reports"
          className="mt-4 inline-block rounded-lg bg-white/10 px-4 py-2 text-xs font-medium text-white hover:bg-white/20"
        >
          ← Back to reports
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/reports" className="text-xs text-cyan-400 hover:underline">
          ← Back to reports list
        </Link>
      </div>
      {downloadError && <p role="alert" className="text-sm text-red-300">{downloadError}</p>}
      <ReportViewer
        report={report}
        onDownloadHtml={() => void handleDownload("html")}
        onDownloadPdf={() => void handleDownload("pdf")}
      />
    </div>
  );
}
