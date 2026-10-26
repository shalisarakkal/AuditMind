import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import SecuritySummary from "./SecuritySummary";
import { json, renderSignedIn } from "@/test/helpers";

const summary = { window_start: "2026-10-19T14:00:00Z", window_end: "2026-10-26T14:00:00Z", counts: { member_added: 0, role_changed: 2, purge: 3 } };
it("links counts to the identical organization/window/outcome and labels unavailable auth attribution", async () => {
  await renderSignedIn(<SecuritySummary orgId="org-1" />, "viewer", { "GET /orgs/org-1/dashboard/security-summary": () => summary });
  const link = await screen.findByRole("link", { name: "Role changes 2" });
  const query = new URL(link.getAttribute("href")!, "http://localhost").searchParams;
  expect(Object.fromEntries(query)).toEqual({ org: "org-1", type: "role_changed", result: "completed", window_start: summary.window_start, window_end: summary.window_end });
  expect(screen.getByRole("link", { name: "Members added 0" })).toBeInTheDocument();
  expect(screen.getByText(/organization attribution is not guaranteed/)).toBeInTheDocument();
});
it("shows an error instead of misleading zeros and supports retry", async () => {
  let fail = true;
  await renderSignedIn(<SecuritySummary orgId="org-1" />, "admin", {
    "GET /orgs/org-1/dashboard/security-summary": () => fail ? json({ detail: "Unavailable" }, 503) : summary,
  });
  await screen.findByRole("alert");
  expect(screen.queryByRole("link", { name: "Members added 0" })).not.toBeInTheDocument();
  fail = false; fireEvent.click(screen.getByRole("button", { name: "Retry security summary" }));
  await waitFor(() => expect(screen.getByRole("link", { name: "Completed purges 3" })).toBeInTheDocument());
});
