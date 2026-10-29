import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  current: false, retired_at: null as string | null, purged_at: null as string | null,
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
  it.each([false, true])("rejects an oversized document immediately without a version request (platform=%s)", async platform => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId={platform ? undefined : "org-1"} writable platform={platform} />, "admin", {
      ...routes(), "GET /platform/documents": () => ({ items: [], total: 0 }),
      "GET /platform/documents/facets": () => ({ framework: [] }),
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    const form = screen.getByRole("form", { name: "Upload document" });
    const file = new File(["Synthetic policy"], "oversized.md", { type: "text/markdown" });
    Object.defineProperty(file, "size", { value: 10 * 1024**2 + 1 });
    fireEvent.change(within(form).getByLabelText("UTF-8 text or Markdown, up to 10 MiB"), { target: { files: [file] } });
    expect(within(form).getByRole("alert")).toHaveTextContent("oversized.md exceeds the 10 MiB file limit");
    expect(within(form).getByRole("button", { name: "Queue processing" })).toBeDisabled();
    fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    fireEvent.change(within(form).getByLabelText("UTF-8 text or Markdown, up to 10 MiB"), { target: { files: [new File(["Policy"], "valid.md")] } });
    expect(within(form).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Queue processing" })).toBeEnabled();
    fireEvent.click(within(form).getByRole("button", { name: "Cancel upload" }));
    expect(screen.queryByRole("form", { name: "Upload document" })).not.toBeInTheDocument();
  });

  it("explains that a JSON inventory is not a document, without submitting it", async () => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable />, "admin", routes());
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    const form = screen.getByRole("form", { name: "Upload document" });
    fireEvent.change(within(form).getByLabelText("UTF-8 text or Markdown, up to 10 MiB"), { target: { files: [new File(["[]"], "cloud_assets.json")] } });
    expect(within(form).getByRole("alert")).toHaveTextContent("Assets or Findings");
    fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  it.each([false, true])("opens and hides a version preview beneath its own row (writable=%s)", async writable => {
    const { fetchMock } = await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={writable} />, writable ? "admin" : "viewer", {
      ...routes([{ ...DOCUMENT, versions: [{ ...VERSION, indexes: [] }] }]),
      "GET /orgs/org-1/documents/versions/version-ui": () => ({ content: "Saved policy text" }),
    });
    const row = (await screen.findByText("UI policy")).closest("tr")!;
    const trigger = within(row).getByRole("button", { name: "Preview v1" });
    expect(trigger).toHaveAttribute("aria-expanded", "false"); fireEvent.click(trigger);
    const panel = await screen.findByRole("region", { name: "Preview of UI policy · v1" });
    expect(await within(panel).findByText("Saved policy text")).toBeVisible();
    expect(panel.closest("tr")?.previousElementSibling).toBe(row);
    expect(panel.closest("td")).toHaveAttribute("colspan", writable ? "6" : "5");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(trigger).toHaveAttribute("aria-controls", panel.id);
    fireEvent.click(within(panel).getByRole("button", { name: "Close preview" }));
    expect(trigger).toHaveFocus(); expect(screen.queryByText("Saved policy text")).not.toBeInTheDocument();
    expect(callsTo(fetchMock, "GET /orgs/org-1/documents?limit=100&offset=0")).toHaveLength(1);
    fireEvent.click(trigger); await screen.findByText("Saved policy text"); fireEvent.click(trigger);
    expect(screen.queryByRole("region", { name: /Preview of/ })).not.toBeInTheDocument();
  });
  it("switches versions/documents without showing a late response from the old preview", async () => {
    let finish!: (value: {content: string}) => void;
    const first = new Promise<{content: string}>(resolve => { finish = resolve; });
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", {
      ...routes([{ ...DOCUMENT, versions: [{ ...VERSION, indexes: [] }] }, { ...DOCUMENT, id: "doc-2", title: "Other policy", versions: [{ ...VERSION, id: "version-2", indexes: [] }] }]),
      "GET /orgs/org-1/documents/versions/version-ui": () => first,
      "GET /orgs/org-1/documents/versions/version-2": () => ({ content: "Second policy text" }),
    });
    fireEvent.click(within((await screen.findByText("UI policy")).closest("tr")!).getByRole("button", { name: "Preview v1" }));
    expect(await screen.findByText("Loading preview…")).toBeVisible();
    fireEvent.click(within(screen.getByText("Other policy").closest("tr")!).getByRole("button", { name: "Preview v1" }));
    expect(await screen.findByText("Second policy text")).toBeVisible();
    await act(async () => { finish({ content: "Late first response" }); });
    expect(screen.queryByText("Late first response")).not.toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: /Preview of/ })).toHaveLength(1);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search documents" }), { target: { value: "Other" } });
    await waitFor(() => expect(screen.queryByRole("region", { name: /Preview of/ })).not.toBeInTheDocument());
  });
  it("keeps preview errors and retry inside the row and treats source text as plain text", async () => {
    let fail = true;
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", {
      ...routes([{ ...DOCUMENT, versions: [{ ...VERSION, indexes: [] }] }]),
      "GET /orgs/org-1/documents/versions/version-ui": () => fail ? json({ detail: "Preview denied" }, 403) : { content: "<script>not executable</script>" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Preview v1" }));
    const panel = await screen.findByRole("region", { name: "Preview of UI policy · v1" });
    expect(await within(panel).findByRole("alert")).toHaveTextContent("Preview denied");
    fail = false; fireEvent.click(within(panel).getByRole("button", { name: "Retry preview" }));
    expect(await within(panel).findByText("<script>not executable</script>")).toBeVisible();
    expect(panel.querySelector("script")).toBeNull();
  });
  it("does not offer preview text for removed versions", async () => {
    await renderSignedIn(<DocumentsLibrary orgId="org-1" writable={false} />, "viewer", routes([{ ...DOCUMENT, versions: [{ ...VERSION, purged_at: "2026-10-25T12:00:00Z", indexes: [] }] }]));
    expect(await screen.findByRole("button", { name: "Preview v1" })).toBeDisabled();
  });
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
    expect(preview).toHaveAttribute("tabindex", "0");
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
