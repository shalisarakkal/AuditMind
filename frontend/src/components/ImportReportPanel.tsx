import { importCounts } from "@/lib/importCounts";
import type { ImportReport, RowError, RowNote, ScanStatus } from "@/lib/types";

export type ImportResult = {
  status: ScanStatus;
  report: ImportReport | null;
  /** Set when the import crashed (no report), or the upload itself failed. */
  error?: string;
  filename: string;
  /** The scan's type: says what the counts count (assets, findings or both). */
  scanType?: string;
};

/** The report's counts, each saying what it counts ("Assets created"), and
 * always how many were created, even none. */
function counts(scanType: string | undefined, report: ImportReport) {
  const shown = importCounts(scanType, report);
  if (!shown.some((c) => c.key === "created")) {
    const [created] = importCounts(scanType, { created: 1 });
    shown.unshift({ ...created, count: 0 });
  }
  return shown.map((c) => ({ ...c, label: c.label[0].toUpperCase() + c.label.slice(1) }));
}

export default function ImportReportPanel({ result, onDismiss }: { result: ImportResult; onDismiss?: () => void }) {
  const { status, report, error, filename, scanType } = result;
  const failed = status === "failed";
  const warnings = report?.warnings ?? [];
  const warningsTotal = Math.max(report?.warnings_total ?? 0, warnings.length);

  return (
    <section
      aria-label="Upload result"
      className={`rounded-xl border p-4 ${failed ? "border-red-400/40 bg-red-400/5" : "border-emerald-400/30 bg-emerald-400/5"}`}
    >
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm text-white">
          <span className="font-medium">{filename}</span>{" "}
          {failed ? <span className="text-red-300">— processing failed</span> : <span className="text-emerald-300">— processed</span>}
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
            {counts(scanType, report).map(({ key, label, count }) => (
              <div key={key} className="rounded-md bg-white/5 px-3 py-1.5 text-sm">
                <dt className="inline text-white/60">{label} </dt>
                <dd className="inline font-semibold text-white">{count.toLocaleString("en-US")}</dd>
              </div>
            ))}
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
            <RowTable title="Warnings — recorded, but worth checking" rows={warnings} tone="warning">
              {warningsTotal > warnings.length && (
                <p className="mt-2 text-xs text-white/50">
                  Showing the first {warnings.length} of {warningsTotal} warnings.
                </p>
              )}
            </RowTable>
          )}
          <NoteList title="Skipped" rows={report.skipped_rows ?? []} total={report.skipped} />
          <NoteList title="Duplicates" rows={report.duplicate_rows ?? []} total={report.duplicates} />
        </>
      )}
    </section>
  );
}

/** Rows left out on purpose (skipped, duplicates): expected, so folded
 * away; each with what it was and why. */
function NoteList({ title, rows, total }: { title: string; rows: RowNote[]; total: number }) {
  if (rows.length === 0) return null;
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-xs font-medium text-white/70 hover:text-white">
        {title} — {total.toLocaleString("en-US")}
        {total > rows.length && ` (the first ${rows.length.toLocaleString("en-US")} listed)`}
      </summary>
      <div className="mt-1 max-h-64 overflow-auto" role="region" aria-label={title}>
        <table className="w-full table-fixed text-left">
          <thead className="text-xs uppercase tracking-wide text-white/50">
            <tr>
              <th className="w-16 py-1 pr-4">Row</th>
              <th className="py-1 pr-4">Item</th>
              <th className="py-1">Why</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((note, i) => (
              <tr key={i} className="border-t border-white/10 text-white/80">
                <td className="py-1 pr-4 align-top">{note.row}</td>
                <td className="break-words py-1 pr-4 align-top">{note.item}</td>
                <td className="py-1 align-top text-white/60">{note.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
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
