import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { mockApi, json } from "@/test/helpers";
import FindingCanonicalReview from "./FindingCanonicalReview";
import FindingCanonicalHistory from "./FindingCanonicalHistory";

const path="/orgs/o1/findings/f2/observations/obs2/identity-binding";
const summary=(id:string,status:string)=>({id,category:"Native plugin",description:`Details ${id}`,severity:"high",
  verification_state:"unverified",verification_version:0,verification:null,
  workflow:{status,version:3,assignee_label:"Reviewed owner",latest_rationale:{text:`Rationale ${id}`},latest_verification:{text:`Verification ${id}`}}});
const view={review_token:"a".repeat(64),expected_version:0,saved:null,context:{findings:[summary("finding-a","open"),summary("finding-b","resolved")]}};
const props={orgId:"o1",path,sourceId:"obs1",onClose:vi.fn(),onSaved:vi.fn()};
async function confirm() {
  await screen.findByText("Rationale finding-a",{exact:false});
  await userEvent.click(screen.getByRole("radio",{name:/finding-a/}));
  await userEvent.type(screen.getByLabelText("Canonical selection reason"),"Reviewed both decisions");
  await userEvent.click(screen.getByLabelText(/I reviewed both independent histories/));
}

it("shows both histories with no preselected survivor and saves only explicit confirmation",async()=>{
  let body:unknown;
  mockApi({["POST "+path+"/canonical/preview"]:()=>view,["POST "+path+"/canonical"]:init=>{body=JSON.parse(String(init.body));return{};}});
  render(<FindingCanonicalReview {...props}/>);
  await screen.findByText("Rationale finding-a",{exact:false});
  expect(screen.getByRole("button",{name:"Cancel"})).toHaveFocus();
  expect(screen.getByRole("radio",{name:/finding-a/})).not.toBeChecked();
  expect(screen.getByRole("button",{name:"Save canonical selection"})).toBeDisabled();
  expect(screen.getAllByRole("link")).toHaveLength(2);
  await confirm();
  await userEvent.click(screen.getByRole("button",{name:"Save canonical selection"}));
  await waitFor(()=>expect(body).toEqual({source_observation_id:"obs1",expected_version:0,review_token:view.review_token,canonical_finding_id:"finding-a",rationale:"Reviewed both decisions",confirm_histories:true}));
});

it("requires fresh confirmation when changing the canonical choice",async()=>{
  mockApi({["POST "+path+"/canonical/preview"]:()=>view});
  render(<FindingCanonicalReview {...props}/>);await confirm();
  await userEvent.click(screen.getByRole("radio",{name:/finding-b/}));
  expect(screen.getByLabelText(/I reviewed both independent histories/)).not.toBeChecked();
  expect(screen.getByRole("button",{name:"Save canonical selection"})).toBeDisabled();
});

it("retains reason on conflict and requires fresh preview, choice and confirmation",async()=>{
  mockApi({["POST "+path+"/canonical/preview"]:()=>view,["POST "+path+"/canonical"]:()=>json({detail:"Canonical review context changed"},409)});
  render(<FindingCanonicalReview {...props}/>);await confirm();
  await userEvent.click(screen.getByRole("button",{name:"Save canonical selection"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("context changed");
  expect(screen.getByLabelText("Canonical selection reason")).toHaveValue("Reviewed both decisions");
  await userEvent.click(screen.getByRole("button",{name:"Reload canonical context"}));
  await screen.findByRole("radio",{name:/finding-a/});
  expect(screen.getByRole("radio",{name:/finding-a/})).not.toBeChecked();
  expect(screen.getByLabelText(/I reviewed both independent histories/)).not.toBeChecked();
});

it("blocks Escape and Cancel while a submitted selection is saving",async()=>{
  let finish:(value:unknown)=>void=()=>{};
  const pending=new Promise(resolve=>{finish=resolve;});
  mockApi({["POST "+path+"/canonical/preview"]:()=>view,["POST "+path+"/canonical"]:()=>pending});
  const close=vi.fn();render(<FindingCanonicalReview {...props} onClose={close}/>);await confirm();
  await userEvent.click(screen.getByRole("button",{name:"Save canonical selection"}));
  expect(screen.getByRole("button",{name:"Cancel"})).toBeDisabled();
  fireEvent(screen.getByRole("dialog"),new Event("cancel",{bubbles:true,cancelable:true}));
  expect(close).not.toHaveBeenCalled();finish({});
  await waitFor(()=>expect(close).toHaveBeenCalledOnce());
});

it("loads history on demand and revokes only the latest selected decision",async()=>{
  const row={id:"d1",version:1,state:"selected",current:null,latest:true,canonical_finding_id:"finding-a",rationale:"Original review",actor_label:"Admin",created_at:"2026-11-07T12:00:00Z",context:view.context};
  let body:unknown;
  const calls=mockApi({"GET /orgs/o1/findings/f2/canonical-decisions":()=>[row,{...row,id:"old",version:0,latest:false}],
    "POST /orgs/o1/canonical-decisions/d1/revoke":init=>{body=JSON.parse(String(init.body));return{};}});
  render(<FindingCanonicalHistory orgId="o1" findingId="f2" canReview disabled={false}/>);
  expect(calls).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Show canonical selection history"}));
  await screen.findByRole("button",{name:"Revoke canonical selection"});
  expect(screen.getAllByRole("button",{name:"Revoke canonical selection"})).toHaveLength(1);
  await userEvent.click(screen.getByRole("button",{name:"Revoke canonical selection"}));
  await userEvent.type(screen.getByLabelText("Revocation reason"),"Withdraw selection");
  await userEvent.click(screen.getByRole("button",{name:"Revoke selection"}));
  await waitFor(()=>expect(body).toEqual({expected_version:1,rationale:"Withdraw selection"}));
});

it("distinguishes a former assignee from an unassigned finding",async()=>{
  const unavailable={...view,context:{findings:view.context.findings.map(f=>({...f,workflow:{...f.workflow,assignee_id:"former-user",assignee_label:null}}))}};
  mockApi({["POST "+path+"/canonical/preview"]:()=>unavailable});
  render(<FindingCanonicalReview {...props}/>);
  expect((await screen.findAllByText("Assignee: Former/unavailable assignee")).length).toBe(2);
});

it("lets an admin review and revoke a conflicting receipt before reloading the new pair",async()=>{
  let blocked=true;
  const prior={id:"prior",version:1,state:"selected",current:null,latest:true,canonical_finding_id:"finding-a",rationale:"Prior independent designation",actor_label:"Admin",created_at:"2026-11-07T12:00:00Z",context:view.context};
  mockApi({["POST "+path+"/canonical/preview"]:()=>blocked ? json({detail:{code:"canonical_conflict",message:"Another canonical selection requires review",canonical_finding_id:"finding-a",decision_id:"prior"}},409):view,
    "GET /orgs/o1/findings/finding-a/canonical-decisions":()=>[prior],
    "POST /orgs/o1/canonical-decisions/prior/revoke":()=>{blocked=false;return{};}});
  render(<FindingCanonicalReview {...props}/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("requires review");
  await userEvent.click(screen.getByRole("button",{name:"Show canonical selection history"}));
  await screen.findByText("Prior independent designation");
  await userEvent.click(screen.getByRole("button",{name:"Revoke canonical selection"}));
  await userEvent.type(screen.getByLabelText("Revocation reason"),"Clear the prior designation");
  await userEvent.click(screen.getByRole("button",{name:"Revoke selection"}));
  await waitFor(()=>expect(screen.queryByRole("dialog",{name:"Revoke canonical selection"})).not.toBeInTheDocument());
  await userEvent.click(screen.getByRole("button",{name:"Reload canonical context"}));
  await screen.findByRole("radio",{name:/finding-a/});
  expect(screen.getByRole("radio",{name:/finding-a/})).not.toBeChecked();
});
