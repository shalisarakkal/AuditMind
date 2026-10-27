import { render, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import ProductBrand from "./ProductBrand";
import { mockApi } from "@/test/helpers";

it("uses the fixed replaceable product asset with an accessible name", () => {
  mockApi({ "GET /platform/branding": () => ({ sidebar_logo_size: "medium", version: "none" }) });
  render(<ProductBrand />);
  const image = screen.getByRole("img", { name: "AuditMind" });
  expect(image).toHaveAttribute("src", "/branding/product-logo.svg");
  expect(image).not.toHaveAttribute("srcset");
  expect(image).toHaveClass("object-contain");
  expect(image.parentElement).toHaveClass("max-w-full", "min-w-0");
  expect(image).toHaveAttribute("width", "180");
  expect(image).toHaveAttribute("height", "48");
});

it.each([["small", "144", "40"], ["medium", "180", "48"], ["large", "192", "64"]])("uses platform %s sizing without distortion", async (size, width, height) => {
  mockApi({ "GET /platform/branding": () => ({ sidebar_logo_size: size, version: "v1" }) });
  render(<ProductBrand />);
  await waitFor(() => expect(screen.getByAltText("AuditMind")).toHaveAttribute("width", width));
  expect(screen.getByAltText("AuditMind")).toHaveAttribute("height", height);
});

it("keeps auth sizing independent without fetching platform settings", () => {
  const fetchMock = mockApi({});
  render(<ProductBrand variant="auth" />);
  expect(screen.getByAltText("AuditMind")).toHaveAttribute("width", "240");
  expect(fetchMock).not.toHaveBeenCalled();
});
