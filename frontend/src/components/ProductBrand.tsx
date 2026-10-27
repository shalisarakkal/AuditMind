"use client";

import Image from "next/image";
import { PRODUCT_SIZES, useProductBranding } from "@/lib/productBranding";

/** Replace public/branding/product-logo.svg to try an approved product logo. */
export default function ProductBrand({ variant = "compact" }: { variant?: "compact" | "auth" }) {
  return variant === "auth" ? <BrandImage width={240} height={72} className="h-[4.5rem] w-60" /> : <SidebarBrand />;
}

function SidebarBrand() {
  const branding = useProductBranding();
  const size = PRODUCT_SIZES[branding.data?.sidebar_logo_size ?? "medium"];
  return <BrandImage {...size} />;
}

function BrandImage({ width, height, className }: { width: number; height: number; className: string }) {
  return <span className={`inline-flex min-w-0 max-w-full ${className}`}>
    <Image src="/branding/product-logo.svg" width={width} height={height} unoptimized
      alt="AuditMind" className="h-full w-full object-contain object-left" />
  </span>;
}
