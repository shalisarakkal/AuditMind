"use client";

import ProductBrandingSettings from "@/components/ProductBrandingSettings";
import { SysadminOnly } from "@/components/SysadminOnly";

export default function ProductBrandingPage() {
  return <SysadminOnly><div className="space-y-6">
    <div><h1 className="text-2xl font-semibold text-white">Product branding</h1>
      <p className="mt-2 text-sm text-white/60">Platform-wide sidebar logo presentation. The approved product artwork is not modified.</p></div>
    <ProductBrandingSettings />
  </div></SysadminOnly>;
}
