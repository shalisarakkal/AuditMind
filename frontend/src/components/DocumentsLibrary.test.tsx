import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DocumentsLibrary from "@/components/DocumentsLibrary";
import { callsTo, renderSignedIn } from "@/test/helpers";

const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: (url: string) => void (navigation.search = url.split("?")[1] ?? "") }),
  usePathname: () => "/documents",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  navigation.search = "";
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
    expect(screen.getByText(`SHA-256: ${"a".repeat(64)}`)).toBeInTheDocument();
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
