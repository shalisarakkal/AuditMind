import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import OrganizationLogoSettings, { OrganizationIdentity } from "./OrganizationLogo";
import { json, renderSignedIn } from "@/test/helpers";

const empty = { version: null, image_data_url: null };
const saved = { version: "v1", image_data_url: "data:image/png;base64,iVBORw0KGgo=" };

it.each([["small", "text-base"], ["medium", "text-xl"], ["large", "text-2xl"]])("renders %s company name typography", async (size, className) => {
  await renderSignedIn(<OrganizationIdentity orgId="org-1" name="Acme" />, "viewer", {
    "GET /orgs/org-1/logo": () => empty,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true, header_name_size: size }),
  });
  await waitFor(() => expect(screen.getByText("Acme", { exact: true })).toHaveClass(className));
});

it("persists company name size and updates the common header", async () => {
  let size = "medium";
  let body: unknown;
  await renderSignedIn(<><OrganizationIdentity orgId="org-1" name="Acme" /><OrganizationLogoSettings orgId="org-1" name="Acme" editable /></>, "admin", {
    "GET /orgs/org-1/logo": () => empty,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true, header_name_size: size }),
    "PATCH /orgs/org-1/branding": init => { body = JSON.parse(init.body as string); size = "large"; return { show_name_in_header: true, header_name_size: size }; },
  });
  const select = screen.getByLabelText("Header company name size");
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.change(select, { target: { value: "large" } });
  await waitFor(() => expect(select).toHaveValue("large"));
  expect(body).toMatchObject({ header_name_size: "large", expected_header_name_size: "medium" });
  expect(screen.getByText("Acme", { exact: true })).toHaveClass("text-2xl");
});

it("hides the header name only with a usable logo and restores it on image failure", async () => {
  await renderSignedIn(<OrganizationIdentity orgId="org-1" name="Acme" />, "viewer", {
    "GET /orgs/org-1/logo": () => saved,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: false }),
  });
  const image = await screen.findByAltText("Acme logo");
  await waitFor(() => expect(screen.queryByText("Acme", { exact: true })).not.toBeInTheDocument());
  fireEvent.error(image);
  expect(screen.getByText("Acme", { exact: true })).toBeVisible();
});

it("keeps the name visible without a logo despite a hidden-name preference", async () => {
  await renderSignedIn(<OrganizationIdentity orgId="org-1" name="Acme" />, "viewer", {
    "GET /orgs/org-1/logo": () => empty,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: false }),
  });
  expect(await screen.findByText("Acme", { exact: true })).toBeVisible();
});

it("saves the organization-wide name preference and refreshes identity", async () => {
  let show = true;
  let body: unknown;
  await renderSignedIn(<><OrganizationIdentity orgId="org-1" name="Acme" /><OrganizationLogoSettings orgId="org-1" name="Acme" editable /></>, "admin", {
    "GET /orgs/org-1/logo": () => saved,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: show }),
    "PATCH /orgs/org-1/branding": init => { body = JSON.parse(init.body as string); show = false; return { show_name_in_header: false }; },
  });
  const checkbox = await screen.findByLabelText("Show organization name beside logo");
  await waitFor(() => expect(checkbox).toBeEnabled());
  fireEvent.click(checkbox);
  await waitFor(() => expect(checkbox).not.toBeChecked());
  expect(body).toEqual({ show_name_in_header: false, expected_show_name_in_header: true, header_logo_size: "medium", expected_header_logo_size: "medium", header_name_size: "medium", expected_header_name_size: "medium" });
  expect(screen.queryByText("Acme", { exact: true })).not.toBeInTheDocument();
});

it("uploads an admin logo with the read version and refreshes the header", async () => {
  let current: typeof empty | typeof saved = empty;
  let fields: FormData | undefined;
  await renderSignedIn(<><OrganizationIdentity orgId="org-1" name="Acme" /><OrganizationLogoSettings orgId="org-1" name="Acme" editable /></>, "admin", {
    "GET /orgs/org-1/logo": () => current,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true }),
    "POST /orgs/org-1/logo": init => { fields = init.body as FormData; current = saved; return saved; },
  });
  await screen.findByText("No organization logo set.");
  fireEvent.change(screen.getByLabelText("Organization logo file"), { target: { files: [new File(["png"], "logo.png", { type: "image/png" })] } });
  fireEvent.click(screen.getByRole("button", { name: "Save logo" }));
  await screen.findByText("Organization logo saved.");
  expect(fields?.get("expected_version")).toBe("none");
  await waitFor(() => expect(screen.getAllByAltText("Acme logo")).toHaveLength(2));
});

it("keeps viewer settings read-only", async () => {
  await renderSignedIn(<OrganizationLogoSettings orgId="org-1" name="Acme" editable={false} />, "viewer", {
    "GET /orgs/org-1/logo": () => saved,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true }),
  });
  await screen.findByAltText("Acme logo");
  expect(screen.queryByLabelText("Organization logo file")).not.toBeInTheDocument();
  expect(screen.getByText(/Only organization admins/)).toBeInTheDocument();
  expect(screen.getByLabelText("Show organization name beside logo")).toBeDisabled();
  expect(screen.getByLabelText("Header logo size")).toBeDisabled();
  expect(screen.getByLabelText("Header company name size")).toBeDisabled();
});

it.each([["small", "96", "48"], ["medium", "160", "64"], ["large", "224", "80"]])("uses proportional %s logo sizing", async (size, width, height) => {
  await renderSignedIn(<OrganizationIdentity orgId="org-1" name="Acme" />, "viewer", {
    "GET /orgs/org-1/logo": () => saved,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true, header_logo_size: size }),
  });
  await waitFor(() => expect(screen.getByAltText("Acme logo")).toHaveAttribute("width", width));
  expect(screen.getByAltText("Acme logo")).toHaveAttribute("height", height);
  expect(screen.getByAltText("Acme logo")).toHaveClass("object-contain", "max-w-full");
});

it("saves logo size with stale-edit protection and refreshes the preview", async () => {
  let size = "medium";
  let body: unknown;
  await renderSignedIn(<OrganizationLogoSettings orgId="org-1" name="Acme" editable />, "admin", {
    "GET /orgs/org-1/logo": () => saved,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true, header_logo_size: size }),
    "PATCH /orgs/org-1/branding": init => { body = JSON.parse(init.body as string); size = "large"; return { show_name_in_header: true, header_logo_size: size }; },
  });
  const select = screen.getByLabelText("Header logo size");
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.change(select, { target: { value: "large" } });
  await waitFor(() => expect(select).toHaveValue("large"));
  expect(body).toEqual({ show_name_in_header: true, expected_show_name_in_header: true, header_logo_size: "large", expected_header_logo_size: "medium", header_name_size: "medium", expected_header_name_size: "medium" });
  expect(screen.getByAltText("Acme logo")).toHaveAttribute("width", "224");
});

it("blocks stale preference retries until explicitly reloaded", async () => {
  await renderSignedIn(<OrganizationLogoSettings orgId="org-1" name="Acme" editable />, "admin", {
    "GET /orgs/org-1/logo": () => empty,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true }),
    "PATCH /orgs/org-1/branding": () => json({ detail: "Branding changed; reload before retrying" }, 409),
  });
  const checkbox = screen.getByLabelText("Show organization name beside logo");
  await waitFor(() => expect(checkbox).toBeEnabled());
  fireEvent.click(checkbox);
  await screen.findByText("Branding changed; reload before retrying");
  expect(checkbox).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload branding preference" }));
  await waitFor(() => expect(checkbox).toBeEnabled());
});

it("requires reload after a stale write and preserves the current image", async () => {
  await renderSignedIn(<OrganizationLogoSettings orgId="org-1" name="Acme" editable />, "admin", {
    "GET /orgs/org-1/logo": () => saved,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true }),
    "POST /orgs/org-1/logo": () => json({ detail: "Logo changed; reload before retrying" }, 409),
  });
  await screen.findByAltText("Acme logo");
  fireEvent.change(screen.getByLabelText("Organization logo file"), { target: { files: [new File(["png"], "logo.png", { type: "image/png" })] } });
  fireEvent.click(screen.getByRole("button", { name: "Save logo" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Save logo" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload organization logo" }));
  await waitFor(() => expect(screen.getByLabelText("Organization logo file")).toBeEnabled());
});

it("confirms removal and submits only the current version", async () => {
  let current: typeof saved | typeof empty = saved;
  const { fetchMock } = await renderSignedIn(<OrganizationLogoSettings orgId="org-1" name="Acme" editable />, "admin", {
    "GET /orgs/org-1/logo": () => current,
    "DELETE /orgs/org-1/logo?expected_version=v1": () => { current = empty; return new Response(null, { status: 204 }); },
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true }),
  });
  await screen.findByAltText("Acme logo");
  fireEvent.click(screen.getByRole("button", { name: "Remove logo" }));
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Confirm removal" }));
  await screen.findByText("Organization logo removed.");
  await screen.findByText("No organization logo set.");
});

it("rejects unsupported files before sending them", async () => {
  const { fetchMock } = await renderSignedIn(<OrganizationLogoSettings orgId="org-1" name="Acme" editable />, "admin", {
    "GET /orgs/org-1/logo": () => empty,
    "GET /orgs/org-1/branding": () => ({ show_name_in_header: true }),
  });
  await screen.findByText("No organization logo set.");
  fireEvent.change(screen.getByLabelText("Organization logo file"), { target: { files: [new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" })] } });
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Save logo" })).toBeDisabled();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
});
