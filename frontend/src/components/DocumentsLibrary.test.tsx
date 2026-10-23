import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DocumentsLibrary from "@/components/DocumentsLibrary";
import { callsTo, json, renderSignedIn } from "@/test/helpers";

const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => "/documents",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
});

const VERSION = { id: "version-ui", number: 1, edition: "Demo", source: "Synthetic policy",
  content_kind: "organization_policy", rights: "Synthetic example", content_hash: "b".repeat(64),
  current: false, retired_at: null as string | null, purged_at: null,
  indexes: [{ id: "index-ui", status: "pending", publish_version: true, error_message: null }] };
const DOCUMENT = { id: "doc-ui", org_id: "org-1" as string | null, title: "UI policy", framework: null,
  created_at: "2026-10-21T12:00:00Z", versions: [VERSION] };
const SETTINGS = { embedding_target: "local:test", report_target: "anthropic:test:prompt",
  effective_embedding: "local", embedding_granted: false, report_granted: false };
function routes(documents = [DOCUMENT]) {
  return { "GET /orgs/org-1/documents": () => ({ items: documents, total: documents.length }),
    "GET /orgs/org-1/documents/facets": () => ({ framework: [] }),
    "GET /orgs/org-1/documents/settings": () => SETTINGS };
}

describe("Documents UI permissions and states", () => {
  it.each(["viewer", "auditor"] as const)("keeps %s read-only, including bulk controls", async role => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" orgName="SA01" writable={false} />, role, routes());
    await screen.findByText("UI policy");
    expect(screen.getByText("1 document in SA01")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retire" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview v1" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Data processing consent"));
    expect(screen.queryByRole("button", { name: /Approve external/ })).not.toBeInTheDocument();
  });

  it("only offers mutation selections for owned documents", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", routes([
      DOCUMENT, { ...DOCUMENT, id: "shared-ui", org_id: null, title: "Shared reference", versions: [{ ...VERSION, id: "shared-version" }] },
    ]));
    await screen.findByText("Shared reference");
    expect(screen.queryByRole("checkbox", { name: /Select Shared reference/ })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Select UI policy/ })).toBeInTheDocument();
    const row = screen.getByText("Shared reference").closest("tr")!;
    expect(within(row).queryByRole("button", { name: "Retire" })).not.toBeInTheDocument();
  });

  it("labels initial publication Queued, not Reactivating, with compact details", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", routes());
    expect(await screen.findByText("Queued")).toHaveClass("bg-white/10");
    expect(screen.queryByText("Reactivating…")).not.toBeInTheDocument();
    const details = screen.getByText("Version details v1").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Version details v1"));
    expect(details).toHaveAttribute("open");
    expect(screen.getByText(`SHA-256: ${"b".repeat(64)}`)).toBeInTheDocument();
  });

  it("uploads through the header action with labelled fields and cancellation", async () => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      ...routes(), "POST /orgs/org-1/documents": () => ({ ok: true }),
    });
    expect(screen.queryByRole("form", { name: "Upload document" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    const form = screen.getByRole("form", { name: "Upload document" });
    expect(within(form).getByLabelText("Title")).toHaveFocus();
    for (const [label, value] of [["Title", "New policy"], ["Edition / version", "v2"], ["Source reference", "Synthetic"], ["Usage rights / authorization", "Owned example"]]) {
      fireEvent.change(within(form).getByLabelText(label), { target: { value } });
    }
    fireEvent.change(within(form).getByLabelText("UTF-8 text or Markdown, up to 10 MiB"), { target: { files: [new File(["Example"], "policy.txt", { type: "text/plain" })] } });
    fireEvent.submit(form);
    await waitFor(() => expect(callsTo(fetchMock, "POST /orgs/org-1/documents")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("form", { name: "Upload document" })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel upload" }));
    expect(screen.queryByRole("form", { name: "Upload document" })).not.toBeInTheDocument();
  });

  it("requires separate explicit consent confirmation and shows updated status", async () => {
    let approved = false;
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      ...routes(), "GET /orgs/org-1/documents/settings": () => ({ ...SETTINGS, report_granted: approved }),
      "PUT /orgs/org-1/documents/settings/consent": () => { approved = true; return { ok: true }; },
    });
    fireEvent.click(screen.getByText("Data processing consent"));
    fireEvent.click(await screen.findByRole("button", { name: "Approve external AI reports" }));
    expect(callsTo(fetchMock, "PUT /orgs/org-1/documents/settings/consent")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Approve processing" }));
    expect(await screen.findByRole("button", { name: "Revoke external AI reports" })).toBeInTheDocument();
    expect(JSON.parse(String(callsTo(fetchMock, "PUT /orgs/org-1/documents/settings/consent")[0][1].body))).toEqual({ purpose: "report", granted: true, target: SETTINGS.report_target });
    expect(screen.getByText("Approved")).toHaveClass("bg-emerald-400/15");
    expect(screen.getByText("Local processing")).toBeInTheDocument();
  });

  it("distinguishes empty, populated and failed evidence searches", async () => {
    let attempt = 0;
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", {
      ...routes(), "POST /orgs/org-1/documents/search": () => {
        attempt++;
        return attempt === 1 ? { items: [] } : attempt === 2 ? { items: [{ citation_id: "c1", title: "Policy evidence", version: "v1", source: "Synthetic", content: "Example excerpt" }] } : json({ detail: "Search unavailable" }, 503);
      },
    });
    const form = screen.getByRole("form", { name: "Search permitted evidence" });
    fireEvent.change(screen.getByLabelText("Evidence query"), { target: { value: "MFA" } });
    fireEvent.submit(form);
    expect(await screen.findByText("No matching permitted evidence found.")).toBeInTheDocument();
    fireEvent.submit(form);
    expect(await screen.findByText("1 evidence result")).toBeInTheDocument();
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("Search unavailable");
    expect(screen.queryByText("Example excerpt")).not.toBeInTheDocument();
  });

  it("hides platform configuration and mutation tools in read-only library mode", async () => {
    await renderSignedIn(<DocumentsLibrary platform writable={false} />, "viewer", {
      "GET /platform/documents": () => ({ items: [{ ...DOCUMENT, org_id: null }], total: 1 }),
      "GET /platform/documents/facets": () => ({ framework: [] }),
    });
    await screen.findByText("UI policy");
    expect(screen.queryByText("Platform embedding configuration")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
  });
});

describe("DocumentsLibrary list", () => {
  it("shows the shared empty state when the organization has no documents", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", {
      "GET /orgs/org-1/documents": () => ({ items: [], total: 0 }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: [] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
    });

    expect(screen.queryByRole("navigation", { name: "Pages" })).not.toBeInTheDocument();
    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  });

  it("uses the shared list controls and displays the stored content hash", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: true,
            retired_at: null,
            purged_at: null,
            indexes: [{ id: "index-1", status: "ready", error_message: null }],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
    });

    expect(await screen.findByRole("searchbox", { name: "Search documents" })).toHaveAttribute("placeholder", "Search all columns");
    expect(screen.getByRole("group", { name: "Added between" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Document/ })).toBeInTheDocument();
    expect(await screen.findByText(`SHA-256: ${"a".repeat(64)}`)).toBeInTheDocument();
  });

  it("keeps a long unbroken preview inside the page width", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: true,
            retired_at: null,
            purged_at: null,
            indexes: [],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
      "GET /orgs/org-1/documents/versions/version-1": () => ({ content: "x".repeat(5000) }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Preview v1" }));
    const preview = await screen.findByText("x".repeat(5000));
    expect(preview.tagName).toBe("PRE");
    expect(preview).toHaveClass("min-w-0", "max-w-full", "overflow-auto", "break-words");
    expect(preview.parentElement).toHaveClass("min-w-0", "max-w-full", "overflow-hidden");
  });

  it("uses the shared danger confirmation panel to remove a retired version", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: false,
            retired_at: "2026-10-02T12:00:00Z",
            purged_at: null,
            indexes: [],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    const confirmation = await screen.findByRole("group", { name: "Remove retired document version" });
    expect(confirmation).toHaveTextContent("Permanently remove Access policy · version 1?");
    expect(screen.getByRole("button", { name: "Remove permanently" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("queues reactivation for a retained retired version", async () => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: false,
            retired_at: "2026-10-02T12:00:00Z",
            purged_at: null,
            indexes: [],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
      "POST /orgs/org-1/documents/versions/version-1/reactivate": () => ({ ok: true }),
    });

    fireEvent.click(await screen.findByRole("button", { name: "Reactivate v1" }));

    await waitFor(() => expect(callsTo(fetchMock, "POST /orgs/org-1/documents/versions/version-1/reactivate")).toHaveLength(1));
  });

  it("prevents removing a version while reactivation is queued", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: false,
            retired_at: "2026-10-02T12:00:00Z",
            purged_at: null,
            indexes: [{ id: "index-1", status: "pending", publish_version: true, error_message: null }],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
    });

    expect(await screen.findByRole("button", { name: "Reactivating…" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Select Access policy · v1 (remove)" })).not.toBeInTheDocument();
  });

  it("bulk retires selected versions after listing their document names", async () => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: true,
            retired_at: null,
            purged_at: null,
            indexes: [],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
      "POST /orgs/org-1/documents/bulk-retire": () => ({ changed: 1 }),
    });

    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Access policy · v1 (retire)" }));
    fireEvent.click(screen.getByRole("button", { name: "Retire selected" }));
    const confirmation = await screen.findByRole("group", { name: "Retire selected document versions" });
    expect(confirmation).toHaveTextContent("Access policy · v1");
    fireEvent.click(screen.getByRole("button", { name: "Retire versions" }));

    await waitFor(() => expect(callsTo(fetchMock, "POST /orgs/org-1/documents/bulk-retire")).toHaveLength(1));
    expect(JSON.parse(String(callsTo(fetchMock, "POST /orgs/org-1/documents/bulk-retire")[0][1].body))).toEqual({ ids: ["version-1"] });
  });

  it("bulk removes selected retired versions through the destructive confirmation", async () => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", {
      "GET /orgs/org-1/documents": () => ({
        items: [{
          id: "doc-1",
          org_id: "org-1",
          title: "Access policy",
          framework: "NIST",
          created_at: "2026-10-01T12:00:00Z",
          versions: [{
            id: "version-1",
            number: 1,
            edition: "2026",
            source: "Internal policy",
            content_kind: "organization_policy",
            rights: "Organization owns this policy",
            content_hash: "a".repeat(64),
            current: false,
            retired_at: "2026-10-02T12:00:00Z",
            purged_at: null,
            indexes: [],
          }],
        }],
        total: 1,
      }),
      "GET /orgs/org-1/documents/facets": () => ({ framework: ["NIST"] }),
      "GET /orgs/org-1/documents/settings": () => ({
        embedding_target: "local",
        report_target: "local",
        effective_embedding: "local",
        embedding_granted: false,
        report_granted: false,
      }),
      "POST /orgs/org-1/documents/bulk-remove?confirmed=true": () => ({ changed: 1 }),
    });

    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Access policy · v1 (remove)" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove selected permanently" }));
    const confirmation = await screen.findByRole("group", { name: "Remove selected document versions" });
    expect(confirmation).toHaveTextContent("Permanently remove 1 selected version?");
    expect(confirmation).toHaveTextContent("Access policy · v1");
    fireEvent.click(screen.getByRole("button", { name: "Remove permanently" }));

    await waitFor(() => expect(callsTo(fetchMock, "POST /orgs/org-1/documents/bulk-remove?confirmed=true")).toHaveLength(1));
    const calls = callsTo(fetchMock, "POST /orgs/org-1/documents/bulk-remove?confirmed=true");
    expect(JSON.parse(String(calls[0][1].body))).toEqual({ ids: ["version-1"] });
  });
});
