import type { ImportProfile } from "@/lib/types";

// The generic profiles post to the original endpoints (which also take
// .nessus files); every other profile posts to /imports.
export const GENERIC_ASSETS = "generic_assets";
export const GENERIC_FINDINGS = "generic_findings";

// How much of a file is read to find its columns; a whole JSON file is
// parsed only if the first record isn't complete by then and the file is small.
const HEAD_BYTES = 256 * 1024;
const JSON_SNIFF_MAX_BYTES = 5 * 1024 * 1024;

export function fileExtension(name: string): string {
  const match = /\.[^.]+$/.exec(name.toLowerCase());
  return match ? match[0] : "";
}

/** The file's column names: a CSV header row, or the keys of the first JSON
 * record ([...] or {"<anything>": [...]}). [] if they can't be read. Only
 * the start of the file is read, so this is quick at any size. */
export async function readColumns(file: File): Promise<string[]> {
  const ext = fileExtension(file.name);
  try {
    if (ext === ".csv") {
      const head = await file.slice(0, HEAD_BYTES).text();
      const firstLine = head.replace(/^\uFEFF/, "").split(/\r?\n/, 1)[0] ?? "";
      return splitCsvLine(firstLine).filter(Boolean);
    }
    if (ext === ".json") {
      const first = firstJsonRecord(await file.slice(0, HEAD_BYTES).text());
      if (first) return Object.keys(first);
      // The first record is huge, or the layout unusual: parse the whole
      // file if that's affordable.
      if (file.size <= JSON_SNIFF_MAX_BYTES) return recordKeys(JSON.parse(await file.text()));
    }
  } catch {
    // Unreadable here; the server reports the real problem on upload.
  }
  return [];
}

/** The keys of a parsed JSON file's first record (the records list chosen as
 * in firstJsonRecord). */
function recordKeys(data: unknown): string[] {
  const object = (data ?? {}) as Record<string, unknown>;
  const records = Array.isArray(data)
    ? data
    : (LIST_KEYS.map((key) => object[key]).find(Array.isArray) ?? Object.values(object).find(Array.isArray));
  const first = (records as unknown[] | undefined)?.[0];
  return first && typeof first === "object" && !Array.isArray(first) ? Object.keys(first) : [];
}

// The keys the server looks for records under when a JSON file is an object
// ({"records": [...]}; ingestion_service.parse_json and each source's
// json_list_key). Otherwise the object's first list is taken.
const LIST_KEYS = ["records", "assets", "findings"];

/** The first record of a JSON file's records list in `head` (the start of the
 * file). The list is the file itself if it is one, else the object's list
 * under one of LIST_KEYS, else its first list. Null if the record isn't
 * complete within `head`, or the list doesn't start with an object. */
export function firstJsonRecord(head: string): Record<string, unknown> | null {
  const list = recordsListStart(head);
  if (list < 0) return null;
  const start = list + 1 + (head.slice(list + 1).length - head.slice(list + 1).trimStart().length);
  if (head[start] !== "{") return null;
  const end = matchingClose(head, start);
  if (end < 0) return null;
  const record: unknown = JSON.parse(head.slice(start, end + 1));
  return record && typeof record === "object" && !Array.isArray(record) ? (record as Record<string, unknown>) : null;
}

/** Where the records list's "[" is in `head`, or -1. Scans the top-level
 * object's keys outside strings, so lists nested in other values (or brackets
 * inside strings) are never taken for it. */
function recordsListStart(head: string): number {
  const first = head.length - head.replace(/^[\s﻿]+/, "").length;
  if (head[first] === "[") return first;
  if (head[first] !== "{") return -1;
  let depth = 0;
  let key: string | null = null; // the top-level key whose value comes next
  let lastString = "";
  let firstList = -1;
  for (let i = first; i < head.length; i++) {
    const ch = head[i];
    if (ch === '"') {
      const close = stringEnd(head, i);
      if (close < 0) break;
      lastString = head.slice(i + 1, close);
      i = close;
    } else if (ch === ":" && depth === 1) key = lastString;
    else if (ch === "," && depth === 1) key = null;
    else if (ch === "{" || ch === "[") {
      if (ch === "[" && depth === 1) {
        if (key !== null && LIST_KEYS.includes(key)) return i;
        if (firstList < 0) firstList = i;
      }
      depth++;
    } else if (ch === "}" || ch === "]") depth--;
  }
  return firstList;
}

/** The index of the quote closing the string opened at `open`, or -1. */
function stringEnd(text: string, open: number): number {
  for (let i = open + 1; i < text.length; i++) {
    if (text[i] === "\\") i++;
    else if (text[i] === '"') return i;
  }
  return -1;
}

/** The index of the "}" closing the object opened at `open`, or -1. */
function matchingClose(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      i = stringEnd(text, i);
      if (i < 0) return -1;
    } else if (ch === "{") depth++;
    else if (ch === "}" && --depth === 0) return i;
  }
  return -1;
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

// The fields every source identifies a row's host by (at least one needed).
const IDENTITY_FIELDS = ["hostname", "ip", "cloud_id"];

/** Whether `profile` can identify the rows of a file with these `columns`:
 * the file has at least one of the source's host columns (under any of its
 * names), or the source fills one in by default. Files whose columns are
 * unknown ([]) are given the benefit of the doubt: the server reports. */
export function canRead(profile: ImportProfile, columns: string[]): boolean {
  // An event log's findings sum its events up: no host needed.
  if (columns.length === 0 || profile.events) return true;
  const present = new Set(columns.map((c) => c.trim().toLowerCase()));
  return IDENTITY_FIELDS.some(
    (field) =>
      Boolean(profile.params?.default_values?.[field]) ||
      (profile.column_map[field] ?? "").split("|").some((name) => present.has(name.trim().toLowerCase())),
  );
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
