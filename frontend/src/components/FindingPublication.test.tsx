import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import FindingPublication, { ObservationPublicationPreview } from "./FindingPublication";
import { mockApi, json } from "@/test/helpers";
const props={orgId:"o1",findingId:"f1"};
const path="/orgs/o1/findings/f1/publication-status";
const previewPath="/orgs/o1/findings/f1/observations/a1/publication-preview";
const source={id:"s1",filename:"source.nessus",retained:true,archived:false,status:"completed"};
const entry={id:"d1",version:1,operation:"publish",created_at:"2026-11-14T15:00:00Z",actor_label:"Reviewer",rationale:"Reviewed source",source,
  observation_id:"a1",observation_retained:true,recorded_at:"2026-11-13T15:00:00Z",observed_at:null,admission_contract:"observation-publication-consumers-v1",snapshots:{before:"s0",after:"s1"}};
const history={availability:"installed",status:"published",current:entry,original_source:{...source,id:"s0",filename:"baseline.nessus"},items:[entry],has_more:false,next_before_version:null,recovery:[],message:"Read-only retention metadata; eligibility requires a fresh review."};
const summary=(value:unknown,truncated=false)=>({value,truncated,bytes:100,sha256:"a".repeat(64)});
const preview={no_op:false,message:"Read-only preview",provenance:{original_filename:"baseline.nessus",observation_filename:"source.nessus",original_scan_id:"s0",observation_scan_id:"s1",observation_id:"a1",recorded_at:"2026-11-13T15:00:00Z",observed_at:null},changes:[{field:"severity",before:summary("medium"),after:summary("critical"),removal:false}]};
async function openPreview(){await userEvent.click(screen.getByRole("button",{name:"Preview scanner-field differences"}));}

describe("Read-only publication UI",()=>{
 it("loads history only on demand and exposes no write action",async()=>{
  const calls=mockApi({[`GET ${path}`]:()=>history});render(<FindingPublication {...props}/>);expect(calls).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Show publication history"}));expect(await screen.findByText("Publication recorded")).toBeVisible();
  expect(screen.getByText("Original owner import: baseline.nessus")).toBeVisible();expect(screen.getByText(/eligibility requires/)).toBeVisible();
  expect(screen.queryByRole("button",{name:/^(Publish|Undo|Apply)$/})).not.toBeInTheDocument();
  expect(calls.mock.calls.every(([,init])=>!init?.method||init.method==="GET")).toBe(true);
 });
 it("shows recovery messages and renders rationale as plain text",async()=>{
  mockApi({[`GET ${path}`]:()=>({...history,status:"recovery_required",recovery:["Purged data cannot be restored."],items:[{...entry,rationale:"<img src=x>"}]})});
  render(<FindingPublication {...props}/>);await userEvent.click(screen.getByRole("button",{name:"Show publication history"}));
  expect(await screen.findByText("Recovery review required")).toBeVisible();expect(screen.getByRole("status")).toHaveTextContent("Purged data");
  expect(screen.getByText(/<img src=x>/)).toBeVisible();expect(screen.queryByRole("img")).not.toBeInTheDocument();
 });
 it("retries a failed history read and uses version cursor pagination",async()=>{
  let attempts=0;mockApi({[`GET ${path}?limit=20`]:()=>++attempts===1?json({detail:"History unavailable"},503):({...history,has_more:true,next_before_version:2}),[`GET ${path}?limit=20&before_version=2`]:()=>({...history,items:[{...entry,rationale:"Older decision"}]})});
  render(<FindingPublication {...props}/>);await userEvent.click(screen.getByRole("button",{name:"Show publication history"}));await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button",{name:"Retry publication history"}));await screen.findByText("Publication recorded");
  await userEvent.click(screen.getByRole("button",{name:"Older publication decisions"}));expect(await screen.findByText("Reason: Older decision")).toBeVisible();
 });
 it("uses only the read-only preview endpoint and labels shortened values/removals",async()=>{
  const calls=mockApi({[`POST ${previewPath}`]:()=>({...preview,changes:[...preview.changes,{field:"description",before:summary("<script>sample</script>",true),after:summary(null),removal:true}]})});
  render(<ObservationPublicationPreview {...props} observationId="a1"/>);expect(calls).not.toHaveBeenCalled();await openPreview();
  expect(await screen.findByText("Medium")).toBeVisible();expect(screen.getByText("Critical")).toBeVisible();expect(screen.getByText("Description (would be cleared)")).toBeVisible();
  expect(screen.getByText("<script>sample</script>")).toBeVisible();expect(screen.getByText("Not set")).toBeVisible();expect(screen.getByText(/Display shortened/)).toBeVisible();
  expect(calls).toHaveBeenCalledTimes(1);expect(calls.mock.calls[0][0]).toContain("publication-preview");expect(screen.queryByRole("button",{name:/^(Publish|Undo|Apply)$/})).not.toBeInTheDocument();
 });
 it("labels identical fields and missing scanner time honestly",async()=>{
  mockApi({[`POST ${previewPath}`]:()=>({...preview,no_op:true,changes:[]})});render(<ObservationPublicationPreview {...props} observationId="a1"/>);await openPreview();
  expect(await screen.findByText("No scanner-field differences.")).toBeVisible();expect(screen.getByText("Source observed time: Not provided")).toBeVisible();
 });
 it("can close during a read and ignores the late response",async()=>{
  let finish!:(value:unknown)=>void;mockApi({[`POST ${previewPath}`]:()=>new Promise(resolve=>{finish=resolve;})});
  render(<ObservationPublicationPreview {...props} observationId="a1"/>);await openPreview();await screen.findByRole("status");
  await userEvent.click(screen.getByRole("button",{name:"Close preview"}));await act(async()=>finish(preview));expect(screen.queryByText("Critical")).not.toBeInTheDocument();
 });
 it("shows a prerequisite failure and permits only a fresh read",async()=>{
  let attempts=0;mockApi({[`POST ${previewPath}`]:()=>++attempts===1?json({detail:"Select the latest observation"},409):preview});render(<ObservationPublicationPreview {...props} observationId="a1"/>);await openPreview();
  expect(await screen.findByRole("alert")).toHaveTextContent("Select the latest observation");await userEvent.click(screen.getByRole("button",{name:"Reload scanner-field preview"}));expect(await screen.findByText("Critical")).toBeVisible();
 });
});


describe("Unavailable publication retention",()=>{
 it("explains missing activation without implying that no decisions exist",async()=>{
  mockApi({[`GET ${path}`]:()=>({availability:"not_installed",status:"unavailable",current:null,items:[],has_more:false,next_before_version:null,recovery:["History requires scheduled database activation."],message:"Read-only."})});
  render(<FindingPublication {...props}/>);await userEvent.click(screen.getByRole("button",{name:"Show publication history"}));
  expect(await screen.findByText("History unavailable")).toBeVisible();expect(screen.getByRole("status")).toHaveTextContent("database activation");
  expect(screen.queryByText("No publication recorded")).not.toBeInTheDocument();
 });
 it("distinguishes a retained observation reference from its missing owner",async()=>{
  const retained={...entry,operation:"undo",observation_owner_retained:false,source:{...source,retained:false,filename:null}};
  mockApi({[`GET ${path}`]:()=>({...history,status:"undone",current:retained,items:[retained]})});
  render(<FindingPublication {...props}/>);await userEvent.click(screen.getByRole("button",{name:"Show publication history"}));
  expect(await screen.findByText("Publication undone")).toBeVisible();expect(screen.getByText(/Retained reference .original owner unavailable/)).toBeVisible();
  expect(screen.queryByText(/Payload snapshots:/)).not.toBeInTheDocument();
 });
});


it("uses the existing readable separator instead of a corrupted question mark",async()=>{
 mockApi({[`GET ${path}`]:()=>history});render(<FindingPublication {...props}/>);
 await userEvent.click(screen.getByRole("button",{name:"Show publication history"}));
 expect(await screen.findByText(["Publish recorded","Version 1"].join(" "+String.fromCharCode(183)+" "))).toBeVisible();
});
