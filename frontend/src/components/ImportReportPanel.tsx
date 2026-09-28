import type { ImportReport, RowError, ScanStatus } from "@/lib/types";

export type ImportResult = {
  status: ScanStatus;
  report: ImportReport | null;
  /** Set when the import crashed (no report), or the upload itself failed. */
  error?: string;
  filename: string;
};

type CountKey = "created" | "updated" | "skipped" | "findings_created" | "duplicates" | "failed";

// When a file created findings alongside assets (a profile import), the first
// three counts are assets.
function counts(report: ImportReport): { key: CountKey; label: string }[] {
  const both = (report.findings_created ?? 0) > 0;
  return [
    { key: "created", label: both ? "Assets created" : "Created" },
    { key: "updated", label: both ? "Assets updated" : "Updated" },
    { key: "skipped", label: both ? "Assets skipped" : "Skipped" },
    { key: "findings_created", label: "Findings created" },
    { key: "duplicates", label: both ? "Duplicate findings" : "Duplicates" },
    { key: "failed", label: "Failed" },
  ];
}

export default function ImportReportPanel({ result, onDismiss }: { result: ImportResult; onDismiss?: () => void }) {
  const { status, report, error, filename } = result;
  const failed = status === "failed";
  const warnings = report?.warnings ?? [];
  const warningsTotal = Math.max(report?.warnings_total ?? 0, warnings.length);

  return (
    <section
      aria-label="Import result"
      className={`rounded-xl border p-4 ${failed ? "border-red-400/40 bg-red-400/5" : "border-emerald-400/30 bg-emerald-400/5"}`}
    >
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm text-white">
          <span className="font-medium">{filename}</span>{" "}
          {failed ? <span className="text-red-300">— import failed</span> : <span className="text-emerald-300">— imported</span>}
        </p>
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="text-xs text-white/60 hover:text-white">
            Dismiss
          </button>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-300">{error}</p>}

      {report && (
        <>
          <dl className="mt-3 flex flex-wrap gap-2">
            {counts(report).map(({ key, label }) =>
              (report[key] ?? 0) > 0 || key === "created" ? (
                <div key={key} className="rounded-md bg-white/5 px-3 py-1.5 text-sm">
                  <dt className="inline text-white/60">{label} </dt>
                  <dd className="inline font-semibold text-white">{report[key]}</dd>
                </div>
              ) : null,
            )}
            {warnings.length > 0 && (
              <div className="rounded-md bg-amber-400/10 px-3 py-1.5 text-sm">
                <dt className="inline text-amber-200/80">Warnings </dt>
                <dd className="inline font-semibold text-amber-100">{warningsTotal}</dd>
              </div>
            )}
          </dl>
          {report.errors.length > 0 && (
            <RowTable title="Problems" rows={report.errors} tone="error">
              {report.failed > report.errors.length && (
                <p className="mt-2 text-xs text-white/50">
                  Showing the first {report.errors.length} of {report.failed} problems.
                </p>
              )}
            </RowTable>
          )}
          {warnings.length > 0 && (
            <RowTable title="Warnings — imported, but worth checking" rows={warnings} tone="warning">
              {warningsTotal > warnings.length && (
                <p className="mt-2 text-xs text-white/50">
                  Showing the first {warnings.length} of {warningsTotal} warnings.
                </p>
              )}
            </RowTable>
          )}
        </>
      )}
    </section>
  );
}

function RowTable({
  title,
  rows,
  tone,
  children,
}: {
  title: string;
  rows: RowError[];
  tone: "error" | "warning";
  children?: React.ReactNode;
}) {
  return (
    <div className="mt-3 max-h-64 overflow-auto" aria-label={title} role="region">
      <p className={`mb-1 text-xs font-medium ${tone === "error" ? "text-red-300" : "text-amber-200"}`}>{title}</p>
      <table className="w-full table-fixed text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-white/50">
          <tr>
            <th className="w-16 py-1 pr-4">Row</th>
            <th className="py-1">{tone === "error" ? "Problem" : "Warning"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e, i) => (
            <tr key={i} className="border-t border-white/10 text-white/80">
              <td className="py-1 pr-4 align-top">{e.row === 0 ? "File" : e.row}</td>
              <td className="py-1">{e.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {children}
    </div>
  );
}
