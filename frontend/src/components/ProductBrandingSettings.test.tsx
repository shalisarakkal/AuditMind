import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import ProductBrandingPage from "@/app/(app)/platform/branding/page";
import { json, renderSignedIn } from "@/test/helpers";

it("keeps the platform page unavailable to organization admins", async () => {
  await renderSignedIn(<ProductBrandingPage />, "admin", { "GET /auth/me": () => ({ is_sysadmin: false }) });
  await screen.findByText("This page is for the Sysadmin.");
  expect(screen.queryByLabelText("Sidebar product logo size")).not.toBeInTheDocument();
});

it("saves platform size and refreshes the preview", async () => {
  let size = "medium";
  let body: unknown;
  await renderSignedIn(<ProductBrandingPage />, "admin", {
    "GET /auth/me": () => ({ is_sysadmin: true }),
    "GET /platform/branding": () => ({ sidebar_logo_size: size, version: "none" }),
    "PATCH /platform/branding": init => { body = JSON.parse(init.body as string); size = "large"; return { sidebar_logo_size: size, version: "v1" }; },
  });
  const select = await screen.findByLabelText("Sidebar product logo size");
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.change(select, { target: { value: "large" } });
  await waitFor(() => expect(select).toHaveValue("large"));
  expect(body).toEqual({ sidebar_logo_size: "large", expected_version: "none" });
  expect(screen.getByAltText("AuditMind")).toHaveAttribute("width", "192");
});

it("requires explicit reload after a platform conflict", async () => {
  await renderSignedIn(<ProductBrandingPage />, "admin", {
    "GET /auth/me": () => ({ is_sysadmin: true }),
    "GET /platform/branding": () => ({ sidebar_logo_size: "medium", version: "none" }),
    "PATCH /platform/branding": () => json({ detail: "Product branding changed; reload before retrying" }, 409),
  });
  const select = await screen.findByLabelText("Sidebar product logo size");
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.change(select, { target: { value: "large" } });
  await screen.findByRole("alert");
  expect(select).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload product branding" }));
  await waitFor(() => expect(select).toBeEnabled());
});
