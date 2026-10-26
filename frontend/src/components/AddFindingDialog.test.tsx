import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import AddFindingDialog from "./AddFindingDialog";
import { json, mockApi } from "@/test/helpers";

it("creates an organization manual finding with trimmed fields and no uploaded scan", async () => {
  let payload: unknown;
  mockApi({ "POST /orgs/o1/findings": (init: RequestInit) => { payload = JSON.parse(String(init.body)); return {id:"f1"}; } });
  const saved = vi.fn(), close = vi.fn();
  render(<AddFindingDialog orgId="o1" orgName="Synthetic org" onClose={close} onSaved={saved} />);
  await userEvent.type(screen.getByLabelText("Description"), " Manual finding ");
  await userEvent.click(within(screen.getByRole("form")).getByRole("button", {name:"Add finding"}));
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(payload).toMatchObject({ description:"Manual finding", severity:"medium", category:null, source:"manual" });
  expect(payload).not.toHaveProperty("scan_id"); expect(close).toHaveBeenCalledOnce();
});

it("does not retry an uncertain creation and retains the description", async () => {
  const post = vi.fn(() => json({detail:"Unavailable"}, 503));
  mockApi({ "POST /orgs/o1/findings": post });
  render(<AddFindingDialog orgId="o1" orgName="Synthetic org" onClose={vi.fn()} onSaved={vi.fn()} />);
  await userEvent.type(screen.getByLabelText("Description"), "Retain me");
  await userEvent.click(screen.getByRole("button", {name:"Add finding"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("may have been created");
  expect(screen.getByLabelText("Description")).toHaveValue("Retain me");
  expect(screen.getByRole("button", {name:"Add finding"})).toBeDisabled();
  expect(post).toHaveBeenCalledOnce();
});
