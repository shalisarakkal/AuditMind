import { screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import ApplicationHeader from "./ApplicationHeader";
import { renderSignedIn } from "@/test/helpers";

it("shows organization identity without duplicating product branding", async () => {
  await renderSignedIn(<ApplicationHeader />, "admin", {
    "GET /orgs/org-1/logo": () => ({ version: null, image_data_url: null }),
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true, header_logo_size: "medium", header_name_size: "medium" }),
  });
  const header = screen.getByRole("banner");
  expect(within(header).getByText("Acme Corp")).toBeInTheDocument();
  expect(within(header).queryByRole("img", { name: "AuditMind" })).not.toBeInTheDocument();
});

it("retains the company logo beside the organization name", async () => {
  await renderSignedIn(<ApplicationHeader />, "viewer", {
    "GET /orgs/org-1/logo": () => ({ version: "v1", image_data_url: "data:image/png;base64,iVBORw0KGgo=" }),
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true, header_logo_size: "medium", header_name_size: "medium" }),
  });
  expect(await screen.findByRole("img", { name: "Acme Corp logo" })).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "AuditMind" })).not.toBeInTheDocument();
});
