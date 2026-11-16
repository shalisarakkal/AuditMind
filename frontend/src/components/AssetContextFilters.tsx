"use client";
import { useApi } from "@/lib/useApi";
import type { ListState } from "@/lib/useListState";
import { BUSINESS_CRITICALITY, type ContextFacets } from "@/lib/assetContext";
import { PickFilter } from "./ListControls";
export default function AssetContextFilters({orgId,list,revision}:{orgId:string;list:ListState;revision:number}){
 const facets=useApi<ContextFacets>(`/orgs/${orgId}/assets/context-facets?revision=${revision}`);
 return <section aria-label="Organization-managed context filters" className="flex flex-wrap items-center gap-3 text-sm">
  <span className="text-white/70">Organization context</span>
  <PickFilter name="managed_owner" label="managed owner" list={list} options={[{value:"",label:"Unassigned"},...(facets.data?.managed_owner||[]).map(value=>({value,label:facets.data?.managed_owner_labels[value]||"Former owner"}))]}/>
  <PickFilter name="managed_environment" label="managed environment" list={list} options={[{value:"",label:"Unknown"},...(facets.data?.managed_environment||[]).map(value=>({value,label:value}))]}/>
  <PickFilter name="business_criticality" label="business criticality" list={list} options={[{value:"",label:"Unknown"},...Object.entries(BUSINESS_CRITICALITY).map(([value,label])=>({value,label}))]}/>
  {facets.error&&<p role="alert">Context filters could not load. <button type="button" className="text-cyan underline" onClick={facets.reload}>Retry context filters</button></p>}
 </section>;
}
