import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PublicationAction from "./PublicationAction";
import { mockApi, json } from "@/test/helpers";
const base="/orgs/o/observation-publication";
const target=base+"/findings/f/observations/a";
const plan={finding_id:"f",observation_id:"a",operation:"publish",expected_version:2,review_token:"a".repeat(64),apply_available:true,no_op:false,changes:[],provenance:{original_filename:"before.nessus",observation_filename:"after.nessus",recorded_at:"2026-11-15T12:00:00Z",observed_at:null}};
const setting={available:true,enabled:true,version:1};
async function open(){await userEvent.click(await screen.findByRole("button",{name:"Review publication"}));await screen.findByText("Original owner import: before.nessus");}
async function confirm(){await userEvent.type(screen.getByLabelText("Publication review rationale"),"Reviewed");await userEvent.click(screen.getByRole("checkbox"));}
describe("Guarded publication",()=>{
 it("blocks publication when policy is off or a workflow draft exists",async()=>{
  mockApi({["GET "+base+"/settings"]:()=>({...setting,enabled:false})});render(<PublicationAction orgId="o" findingId="f" observationId="a" hasWorkflowDraft onChanged={vi.fn()}/>);
  expect(await screen.findByRole("button",{name:"Review publication"})).toBeDisabled();expect(screen.getByRole("status")).toHaveTextContent("unsaved workflow draft");
 });
 it("requires explicit confirmation and sends only the fixed reviewed request",async()=>{
  let body:unknown;const changed=vi.fn();mockApi({["GET "+base+"/settings"]:()=>setting,["POST "+target+"/preview"]:()=>plan,["POST "+target+"/publish"]:(init)=>{body=JSON.parse(String(init?.body));return {};}});
  render(<PublicationAction orgId="o" findingId="f" observationId="a" onChanged={changed}/>);await open();expect(screen.getByRole("button",{name:"Publish scanner fields"})).toBeDisabled();await confirm();await userEvent.click(screen.getByRole("button",{name:"Publish scanner fields"}));expect(changed).toHaveBeenCalledOnce();expect(body).toMatchObject({expected_version:2,review_token:plan.review_token,rationale:"Reviewed",confirm:true});
 });
 it("keeps an uncertain request frozen even when its retry is denied",async()=>{
  const bodies:string[]=[];mockApi({["GET "+base+"/settings"]:()=>setting,["POST "+target+"/preview"]:()=>plan,["POST "+target+"/publish"]:(init)=>{bodies.push(String(init?.body));return json({detail:bodies.length===1?"Unavailable":"Role revoked"},bodies.length===1?503:403);}});
  render(<PublicationAction orgId="o" findingId="f" observationId="a" onChanged={vi.fn()}/>);await open();await confirm();await userEvent.click(screen.getByRole("button",{name:"Publish scanner fields"}));await screen.findByRole("button",{name:"Retry same request"});await userEvent.click(screen.getByRole("button",{name:"Retry same request"}));expect(await screen.findByRole("alert")).toHaveTextContent("Role revoked");expect(bodies[0]).toBe(bodies[1]);expect(screen.getByLabelText("Publication review rationale")).toBeDisabled();expect(screen.getByRole("button",{name:"Close and refresh"})).toBeEnabled();
 });
 it("requires a fresh preview after a definite stale conflict",async()=>{
  mockApi({["GET "+base+"/settings"]:()=>setting,["POST "+target+"/preview"]:()=>plan,["POST "+target+"/publish"]:()=>json({detail:"Stale preview"},409)});render(<PublicationAction orgId="o" findingId="f" observationId="a" onChanged={vi.fn()}/>);await open();await confirm();await userEvent.click(screen.getByRole("button",{name:"Publish scanner fields"}));expect(await screen.findByRole("button",{name:"Reload and review current source"})).toBeEnabled();expect(screen.getByRole("button",{name:"Publish scanner fields"})).toBeDisabled();
 });
});
