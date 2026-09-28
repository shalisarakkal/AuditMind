import type { ImportProfile } from "@/lib/types";

// The generic profiles post to the original endpoints (which also take
// .nessus files); every other profile posts to /imports.
export const GENERIC_ASSETS = "generic_assets";
export const GENERIC_FINDINGS = "generic_findings";

const JSON_SNIFF_MAX_BYTES = 5 * 1024 * 1024;

export function fileExtension(name: string): string {
  const match = /\.[^.]+$/.exec(name.toLowerCase());
  return match ? match[0] : "";
}

/** The file's column names: a CSV header row, or the keys of the first JSON
 * record ([...] or {"<anything>": [...]}). [] if they can't be read. */
export async function readColumns(file: File): Promise<string[]> {
  const ext = fileExtension(file.name);
  try {
    if (ext === ".csv") {
      const head = await file.slice(0, 64 * 1024).text();
      const firstLine = head.replace(/^\uFEFF/, "").split(/\r?\n/, 1)[0] ?? "";
      return splitCsvLine(firstLine).filter(Boolean);
    }
    if (ext === ".json" && file.size <= JSON_SNIFF_MAX_BYTES) {
      const data: unknown = JSON.parse(await file.text());
      const records = Array.isArray(data)
        ? data
        : Object.values((data ?? {}) as Record<string, unknown>).find(Array.isArray);
      const first = (records as unknown[] | undefined)?.[0];
      return first && typeof first === "object" && !Array.isArray(first) ? Object.keys(first) : [];
    }
  } catch {
    // Unreadable here; the server reports the real problem on upload.
  }
  return [];
}

function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += ch;
    }
  }
  cells.push(cell.trim());
  return cells;
}

/** The profile that finds the most of its fields in the file. A field is
 * found when any of its column names ("ResourceType|Type") is a column. A
 * profile qualifies when it finds at least half its fields, and at least 3
 * (or all, if it maps fewer); the org's own profiles win ties over built-ins. */
export function suggestProfile(columns: string[], profiles: ImportProfile[]): ImportProfile | null {
  const present = new Set(columns.map((c) => c.trim().toLowerCase()));
  let best: ImportProfile | null = null;
  let bestFound = 0;
  for (const profile of profiles) {
    const fields = Object.values(profile.column_map).map((header) =>
      header.split("|").map((name) => name.trim().toLowerCase()),
    );
    const found = fields.filter((names) => names.some((name) => present.has(name))).length;
    if (found === 0 || found < Math.min(3, fields.length) || found * 2 < fields.length) continue;
    if (found > bestFound || (found === bestFound && best?.builtin && !profile.builtin)) {
      best = profile;
      bestFound = found;
    }
  }
  return best;
}

/** Where to upload a file read with `profileKey`, and the extra form fields. */
export function importTarget(orgId: string, profileKey: string): { path: string; fields: Record<string, string> } {
  if (profileKey === GENERIC_ASSETS) return { path: `/orgs/${orgId}/assets/import`, fields: {} };
  if (profileKey === GENERIC_FINDINGS) return { path: `/orgs/${orgId}/findings/import`, fields: {} };
  return { path: `/orgs/${orgId}/imports`, fields: { profile: profileKey } };
}

/** "open_ports" -> "Open ports", "endpoint_id" -> "Endpoint ID". */
export function humanize(name: string): string {
  const text = name.replace(/_/g, " ").replace(/\b(id|ip|os)\b/gi, (word) => word.toUpperCase());
  return text.charAt(0).toUpperCase() + text.slice(1);
}
