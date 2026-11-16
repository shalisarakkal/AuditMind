import type { Domain } from "./types";

export type Catalog = { id: string; framework: string; edition: string; title: string; source: string; rights: string; content_hash: string; installed_at: string };
export type Control = { control_id: string; reference: string; title: string; description: string };
export type Catalogs = { available: boolean; items: Catalog[] };
export type CatalogControls = { catalog: Catalog; controls: Control[] };
export type MappingDecision = { id: string; version: number; state: "proposed" | "approved" | "withdrawn"; proposal_version: number | null; catalog: Catalog; controls: Control[]; rationale: string; actor_label: string; created_at: string };
export type ControlMapping = { available: boolean; context_kind?: "finding" | "rule"; finding_id: string | null; source: string | null; domain: Domain; category: string | null; archived: boolean; inactive: boolean; version: number; rule_id: string | null; status: "mapped" | "unmapped"; effective: MappingDecision | null; proposal: MappingDecision | null };

export type ControlMappingSummary = { available: boolean; status: "mapped" | "unmapped"; proposal_pending: boolean; version: number; catalog_id: string | null };
