export type AssetContext = {
 available:boolean; version:number; owner_id:string|null; owner_label:string|null;
 owner_status:"unassigned"|"active"|"inactive"|"former"; environment:string|null;
 business_criticality:"critical"|"high"|"medium"|"low"|null; updated_at:string|null; asset_archived:boolean;
};
export const BUSINESS_CRITICALITY:Record<string,string>={critical:"Critical",high:"High",medium:"Medium",low:"Low"};
export function ownerText(value:AssetContext){return value.owner_id?`${value.owner_label||"Unavailable owner"}${value.owner_status==="former"?" (former member)":value.owner_status==="inactive"?" (inactive)":""}`:"Unassigned";}
export type ContextFacets={managed_owner:string[];managed_owner_labels:Record<string,string>;managed_environment:string[];business_criticality:string[]};
