import type { ImportReport, ScanStatus } from "@/lib/types";

export type ImportResult = {
  status: ScanStatus;
  report: ImportReport | null;
  /** Set when the import crashed (no report), or the upload itself failed. */
  error?: string;
  filename: string;
};

const COUNTS: { key: keyof Omit<ImportReport, "errors">; label: string }[] = [
  { key: "created", label: "Created" },
  { key: "updated", label: "Updated" },
  { key: "skipped", label: "Skipped" },
  { key: "duplicates", label: "Duplicates" },
  { key: "failed", label: "Failed" },
];

export default function ImportReportPanel({ result, onDismiss }: { result: ImportResult; onDismiss?: () => void }) {
  const { status, report, error, filename } = result;
  const failed = status === "failed";

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
            {COUNTS.map(({ key, label }) =>
              report[key] > 0 || key === "created" ? (
                <div key={key} className="rounded-md bg-white/5 px-3 py-1.5 text-sm">
                  <dt className="inline text-white/60">{label} </dt>
                  <dd className="inline font-semibold text-white">{report[key]}</dd>
                </div>
              ) : null,
            )}
          </dl>
          {report.errors.length > 0 && (
            <div className="mt-3 max-h-64 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-white/50">
                  <tr>
                    <th className="py-1 pr-4">Row</th>
                    <th className="py-1">Problem</th>
                  </tr>
                </thead>
                <tbody>
                  {report.errors.map((e, i) => (
                    <tr key={i} className="border-t border-white/10 text-white/80">
                      <td className="py-1 pr-4 align-top">{e.row === 0 ? "File" : e.row}</td>
                      <td className="py-1">{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {report.failed > report.errors.length && (
                <p className="mt-2 text-xs text-white/50">
                  Showing the first {report.errors.length} of {report.failed} problems.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
