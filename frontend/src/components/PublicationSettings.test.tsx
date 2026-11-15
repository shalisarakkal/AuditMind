import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import PublicationSettings from "./PublicationSettings";
import { mockApi, json } from "@/test/helpers";
const path="/orgs/o/observation-publication/settings";
const saved={available:true,enabled:false,version:0,reason:null};
describe("Publication policy",()=>{
 it("fails closed without database activation",async()=>{
  mockApi({["GET "+path]:()=>({...saved,available:false,reason:"Activation required"})});render(<PublicationSettings orgId="o" editable/>);expect(await screen.findByText("Activation required")).toBeVisible();expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
 });
 it("does not offer policy edits to a read-only member",async()=>{
  mockApi({["GET "+path]:()=>saved});render(<PublicationSettings orgId="o" editable={false}/>);expect(await screen.findByText(/Read-only: an organization/)).toBeVisible();expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
 });
 it("reloads after uncertain save and permits review even if saved version is unchanged",async()=>{
  mockApi({["GET "+path]:()=>saved,["PATCH "+path]:()=>json({detail:"Unavailable"},503)});render(<PublicationSettings orgId="o" editable/>);await userEvent.click(await screen.findByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Save publication setting"}));expect(await screen.findByRole("alert")).toHaveTextContent("Outcome unknown");expect(screen.getByRole("checkbox")).toBeDisabled();await userEvent.click(screen.getByRole("button",{name:"Reload publication setting"}));expect(await screen.findByRole("checkbox")).toBeEnabled();expect(screen.getByRole("checkbox")).not.toBeChecked();expect(screen.queryByRole("alert")).not.toBeInTheDocument();
 });
});
