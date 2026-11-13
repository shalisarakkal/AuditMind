import { render,screen,waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe,it,expect,vi } from "vitest";
import FindingConsolidation from "./FindingConsolidation";
import { mockApi,json,callsTo } from "@/test/helpers";
const path="/orgs/o1/finding-consolidations";
const plan={review_token:"a".repeat(64),expected_version:0,members:[{finding_id:"a",role:"canonical"},{finding_id:"b",role:"alias"}],findings:[{id:"a",description:"Canonical source"},{id:"b",description:"Independent alias"}],source_counts:{scan:2,asset:2,observation:2}};
const props={orgId:"o1",findingId:"a",canReview:true,disabled:false,onBusyChange:vi.fn(),onChanged:vi.fn()};
function setup(enabled=true,extra={}) {return mockApi({
  [`GET ${path}/for-finding/a`]:()=>({settings:{enabled,version:1},items:[]}),
  "GET /orgs/o1/findings/a/canonical-decisions":()=>[{id:"d1",state:"selected",latest:true,canonical_finding_id:"a"}],
  [`POST ${path}/publication-preview`]:()=>plan,...extra});}
async function preview(){await userEvent.click(screen.getByRole("button",{name:"Show consolidation review"}));await userEvent.click(await screen.findByRole("button",{name:"Preview consolidation for a"}));await screen.findByText("Canonical source");}
async function acknowledge(){await userEvent.type(screen.getByLabelText("Review rationale"),"Explicitly reviewed both sources");await userEvent.click(screen.getByRole("checkbox"));}

describe("Reviewed consolidation UI",()=>{
  it("blocks mutations while preserving an unsaved workflow draft and labels both roles",async()=>{
    setup(true);const view=render(<FindingConsolidation {...props} hasWorkflowDraft/>);
    await userEvent.click(screen.getByRole("button",{name:"Show consolidation review"}));
    expect(await screen.findByRole("button",{name:"Preview consolidation for a"})).toBeDisabled();
    expect(screen.getByText(/Save or clear the unsaved workflow draft/)).toBeVisible();
    view.rerender(<FindingConsolidation {...props} hasWorkflowDraft={false}/>);
    await userEvent.click(screen.getByRole("button",{name:"Preview consolidation for a"}));
    expect(await screen.findByText("Canonical finding: remains the primary record")).toBeVisible();
    expect(screen.getByText(/Retained alias: excluded/)).toBeVisible();
  });

  it("keeps default-off controls unavailable and explains the separate setting",async()=>{
    setup(false);render(<FindingConsolidation {...props}/>);await userEvent.click(screen.getByRole("button",{name:"Show consolidation review"}));
    expect(await screen.findByText(/New consolidation is disabled/)).toBeVisible();
    expect(screen.queryByRole("button",{name:/Preview consolidation for/})).not.toBeInTheDocument();
  });
  it("requires rationale and acknowledgment, freezes submission and focuses Cancel",async()=>{
    let finish!:(value:unknown)=>void;setup(true,{[`POST ${path}/apply`]:()=>new Promise(resolve=>{finish=resolve;})});
    const changed=vi.fn();render(<FindingConsolidation {...props} onChanged={changed}/>);await preview();
    expect(screen.getByRole("button",{name:"Cancel"})).toHaveFocus();
    expect(screen.getByRole("button",{name:"Consolidate pair"})).toBeDisabled();await acknowledge();
    await userEvent.click(screen.getByRole("button",{name:"Consolidate pair"}));
    expect(screen.getByRole("button",{name:"Cancel"})).toBeDisabled();expect(screen.getByLabelText("Review rationale")).toBeDisabled();
    await userEvent.keyboard("{Escape}");expect(screen.getByRole("dialog")).toBeVisible();
    finish({consolidation_id:"g1",version:1});await waitFor(()=>expect(changed).toHaveBeenCalledOnce());
  });
  it("retains rationale across a conflict and requires a fresh preview",async()=>{
    setup(true,{[`POST ${path}/apply`]:()=>json({detail:"Source changed; reload"},409)});
    render(<FindingConsolidation {...props}/>);await preview();await acknowledge();await userEvent.click(screen.getByRole("button",{name:"Consolidate pair"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Source changed");
    expect(screen.getByRole("button",{name:"Consolidate pair"})).toBeDisabled();
    expect(screen.getByLabelText("Review rationale")).toHaveValue("Explicitly reviewed both sources");
    expect(screen.getByLabelText("Review rationale")).toBeDisabled();
    await userEvent.click(screen.getByRole("button",{name:"Reload and review current targets"}));await screen.findByText("Canonical source");
    expect(screen.getByLabelText("Review rationale")).toHaveValue("Explicitly reviewed both sources");expect(screen.getByRole("checkbox")).not.toBeChecked();
  });
  it.each(["network","server"])("retries an unknown %s result with exactly the same request and nonce",async(kind)=>{
    let attempts=0;const fetch=setup(true,{[`POST ${path}/apply`]:()=>{if(++attempts===1){if(kind==="network")throw new TypeError("Network unavailable");return json({detail:"Response unavailable"},503);}return {version:1};}});
    render(<FindingConsolidation {...props}/>);await preview();await acknowledge();await userEvent.click(screen.getByRole("button",{name:"Consolidate pair"}));
    await screen.findByText(/Outcome unknown/);expect(screen.getByLabelText("Review rationale")).toBeDisabled();
    await userEvent.click(screen.getByRole("button",{name:"Retry same request"}));await waitFor(()=>expect(attempts).toBe(2));
    const writes=callsTo(fetch,`POST ${path}/apply`);expect(writes).toHaveLength(2);expect(writes[0][1].body).toBe(writes[1][1].body);
  });
  it("provides read-only retained history without offering mutations to viewers",async()=>{
    setup(true,{[`GET ${path}/for-finding/a`]:()=>({settings:{enabled:true,version:1},items:[{id:"g1",version:1,state:"active",published:true,canonical_finding_id:"a",canonical_decision_id:"d1",member_ids:["a","b"]}]})});
    render(<FindingConsolidation {...props} canReview={false}/>);await userEvent.click(screen.getByRole("button",{name:"Show consolidation review"}));
    expect(await screen.findByText(/Published pair/)).toBeVisible();expect(screen.getByText(/Retained member source and workflow history/)).toBeVisible();
    expect(screen.queryByRole("button",{name:"Preview undo consolidation"})).not.toBeInTheDocument();
  });
});
