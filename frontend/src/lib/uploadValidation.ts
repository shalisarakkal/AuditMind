/** Fixed document/logo ceilings match the API contract. Import size is
 * configurable: obtain it from the API before selection can become ready. */
export const DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
export const LOGO_MAX_BYTES = 2 * 1024 * 1024;

export type UploadLimits = {
  import_max_bytes: number;
  document_max_bytes: number;
  logo_max_bytes: number;
};

export function formatFileLimit(bytes: number): string {
  if (bytes >= 1024**3 && bytes % 1024**3 === 0) return `${bytes / 1024**3} GiB`;
  if (bytes >= 1024**2) return `${Number((bytes / 1024**2).toFixed(2))} MiB`;
  if (bytes >= 1024) return `${Number((bytes / 1024).toFixed(2))} KiB`;
  return `${bytes} bytes`;
}

function exceedsLimit(file: File, maxBytes: number): string | null {
  return file.size > maxBytes
    ? `${file.name} exceeds the ${formatFileLimit(maxBytes)} file limit (${file.size.toLocaleString()} bytes selected).`
    : null;
}

export function importFileError(file: File, maxBytes: number): string | null {
  if (!/\.(csv|json|nessus)$/i.test(file.name)) return `${file.name}: Unsupported file type; expected .csv, .json, .nessus.`;
  return exceedsLimit(file, maxBytes);
}

export function documentFileError(file: File): string | null {
  if (!/\.(txt|md|markdown)$/i.test(file.name)) return `${file.name}: Choose UTF-8 text or Markdown (.txt, .md, .markdown). CSV/JSON inventories belong in Assets or Findings.`;
  return exceedsLimit(file, DOCUMENT_MAX_BYTES);
}
