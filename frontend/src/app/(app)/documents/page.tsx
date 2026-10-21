"use client";

import DocumentsLibrary from "@/components/DocumentsLibrary";
import { useApp } from "@/context/AppContext";

export default function DocumentsPage() {
  const { selectedOrg } = useApp();
  if (!selectedOrg) return null;
  return <DocumentsLibrary key={selectedOrg.id} orgId={selectedOrg.id} writable={selectedOrg.role === "admin" && !selectedOrg.archived} />;
}
