"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/apiClient";
import { PRODUCT_BRANDING_CHANGED, ProductSize, useProductBranding } from "@/lib/productBranding";
import ProductBrand from "./ProductBrand";

export default function ProductBrandingSettings() {
  const branding = useProductBranding();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  async function change(size: ProductSize) {
    if (!branding.data || inFlight.current || conflict) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      await api.patch("/platform/branding", { sidebar_logo_size: size, expected_version: branding.data.version });
      window.dispatchEvent(new Event(PRODUCT_BRANDING_CHANGED));
    } catch (invalid) {
      setError((invalid as Error).message);
      if ((invalid as { status?: number }).status === 409) setConflict(true);
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Product branding settings" className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-4">
    <div>
      <label htmlFor="product-logo-size" className="block text-sm text-white">Sidebar product logo size</label>
      <select id="product-logo-size" value={branding.data?.sidebar_logo_size ?? "medium"}
        disabled={busy || branding.loading || !branding.data || conflict}
        onChange={event => void change(event.target.value as ProductSize)}
        className="mt-1 max-w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-white disabled:opacity-50">
        <option value="small">Small (144 × 40)</option>
        <option value="medium">Medium (180 × 48)</option>
        <option value="large">Large (192 × 64)</option>
      </select>
    </div>
    <p className="text-sm text-white/60">Saved automatically for all organizations. Only platform admins can change this. Other sessions update on refresh. Sign-in, company logos and company names are unchanged.</p>
    <div><p className="mb-2 text-sm text-white/70">Preview</p><ProductBrand /></div>
    {busy && <p role="status" className="text-sm text-white/60">Saving product branding…</p>}
    {(error || branding.error) && <p role="alert" className="text-sm text-red-300">{error || branding.error}</p>}
    {(conflict || branding.error) && <button type="button" disabled={busy} className="text-sm text-cyan underline" onClick={() => { setConflict(false); setError(null); branding.reload(); }}>Reload product branding</button>}
  </section>;
}
