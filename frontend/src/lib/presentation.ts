/** For known application enums only, never user-authored text or acronyms. */
export function enumLabel(value: string): string {
  const text = value.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function capturedTime(value?: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Invalid recorded timestamp" : date.toLocaleString();
}

/** Rephrase only this known system value; preserve other saved provenance. */
export function reportScope(value?: string | null): string {
  return value === "currently active findings created within inclusive UTC dates; current inventory"
    ? "Scope: Current inventory and active findings created within the selected date range. Date boundaries were evaluated in UTC."
    : value ?? "Scope not recorded";
}
