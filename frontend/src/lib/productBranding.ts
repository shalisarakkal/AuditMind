"use client";

import { useEffect } from "react";
import { useApi } from "./useApi";

export type ProductSize = "small" | "medium" | "large";
export type ProductBranding = { sidebar_logo_size: ProductSize; version: string };
export const PRODUCT_BRANDING_CHANGED = "auditmind-product-branding-changed";
export const PRODUCT_SIZES = {
  small: { width: 144, height: 40, className: "h-10 w-36" },
  medium: { width: 180, height: 48, className: "h-12 w-[180px]" },
  large: { width: 192, height: 64, className: "h-16 w-48" },
};

export function useProductBranding() {
  const branding = useApi<ProductBranding>("/platform/branding");
  useEffect(() => {
    const changed = () => branding.reload();
    window.addEventListener(PRODUCT_BRANDING_CHANGED, changed);
    return () => window.removeEventListener(PRODUCT_BRANDING_CHANGED, changed);
  }, [branding.reload]);
  return branding;
}
