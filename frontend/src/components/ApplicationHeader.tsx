"use client";
import ProductBrand from "./ProductBrand";
import { useApp } from "@/context/AppContext";

export default function ApplicationHeader() {
  const { selectedOrg } = useApp();
  return <header className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
    <ProductBrand />
    <span className="min-w-0 break-words text-sm text-white/70">{selectedOrg?.name || "Platform"}</span>
  </header>;
}
