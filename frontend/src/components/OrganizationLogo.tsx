"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/apiClient";
import { useApi } from "@/lib/useApi";
import { LOGO_MAX_BYTES } from "@/lib/uploadValidation";
import ConfirmPanel from "./ConfirmPanel";

type Logo = { version: string | null; image_data_url: string | null };
const CHANGED = "auditmind-organization-logo-changed";
type LogoSize = "small" | "medium" | "large";
type Branding = { show_name_in_header: boolean; header_logo_size?: LogoSize; header_name_size?: LogoSize };
const NAME_SIZES = { small: "text-base", medium: "text-xl", large: "text-2xl" };
const LOGO_SIZES = {
  small: { width: 96, height: 48, className: "h-12 w-24" },
  medium: { width: 160, height: 64, className: "h-16 w-40" },
  large: { width: 224, height: 80, className: "h-20 w-56" },
};

function useBranding(orgId: string) {
  const branding = useApi<Branding>(`/orgs/${orgId}/branding`);
  useEffect(() => {
    const changed = (event: Event) => {
      if ((event as CustomEvent<string>).detail === orgId) branding.reload();
    };
    window.addEventListener(CHANGED, changed);
    return () => window.removeEventListener(CHANGED, changed);
  }, [orgId, branding.reload]);
  return branding;
}

function HeaderBrandingSettings({ orgId, editable }: { orgId: string; editable: boolean }) {
  const branding = useBranding(orgId);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  async function change(show: boolean, size: LogoSize, nameSize: LogoSize = branding.data?.header_name_size ?? "medium") {
    if (!branding.data || inFlight.current || conflict) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      await api.patch(`/orgs/${orgId}/branding`, { show_name_in_header: show, expected_show_name_in_header: branding.data.show_name_in_header,
        header_logo_size: size, expected_header_logo_size: branding.data.header_logo_size ?? "medium",
        header_name_size: nameSize, expected_header_name_size: branding.data.header_name_size ?? "medium" });
      window.dispatchEvent(new CustomEvent(CHANGED, { detail: orgId }));
    } catch (invalid) {
      setError((invalid as Error).message);
      if ((invalid as { status?: number }).status === 409) setConflict(true);
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <div className="space-y-2 border-t border-white/10 pt-3">
    <label className="flex items-center gap-2 text-sm text-white">
      <input type="checkbox" checked={branding.data?.show_name_in_header ?? true}
        disabled={!editable || busy || branding.loading || !branding.data || conflict}
        onChange={event => void change(event.target.checked, branding.data?.header_logo_size ?? "medium")} />
      Show organization name beside logo
    </label>
    <div>
      <label htmlFor={`header-logo-size-${orgId}`} className="block text-sm text-white">Header logo size</label>
      <select id={`header-logo-size-${orgId}`} value={branding.data?.header_logo_size ?? "medium"}
        disabled={!editable || busy || branding.loading || !branding.data || conflict}
        onChange={event => void change(branding.data?.show_name_in_header ?? true, event.target.value as LogoSize)}
        className="mt-1 block max-w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-white disabled:opacity-50">
        <option value="small">Small (96 × 48)</option>
        <option value="medium">Medium (160 × 64)</option>
        <option value="large">Large (224 × 80)</option>
      </select>
    </div>
    <p className="text-sm text-white/60">Logo size preserves proportions without cropping or stretching. Transparent padding inside the image can still make its artwork look small.</p>
    <div>
      <label htmlFor={`header-name-size-${orgId}`} className="block text-sm text-white">Header company name size</label>
      <select id={`header-name-size-${orgId}`} value={branding.data?.header_name_size ?? "medium"}
        disabled={!editable || busy || branding.loading || !branding.data || conflict}
        onChange={event => void change(branding.data?.show_name_in_header ?? true, branding.data?.header_logo_size ?? "medium", event.target.value as LogoSize)}
        className="mt-1 block max-w-full rounded-md border border-white/20 bg-navy px-3 py-2 text-white disabled:opacity-50">
        <option value="small">Small (16px)</option>
        <option value="medium">Medium (20px)</option>
        <option value="large">Large (24px)</option>
      </select>
    </div>
    <p className="text-sm text-white/60">Applies only to the header company name, when shown. The organization selector and other text sizes do not change.</p>
    <p className="text-sm text-white/60">Saved automatically for all organization members. The header always shows the name when no usable logo is available. The organization selector is unchanged.</p>
    {(error || branding.error) && <p role="alert" className="text-sm text-red-300">{error || branding.error}</p>}
    {(conflict || branding.error) && <button type="button" disabled={busy} className="text-sm text-cyan underline" onClick={() => { setConflict(false); setError(null); branding.reload(); }}>Reload branding preference</button>}
  </div>;
}

function useLogo(orgId: string) {
  const logo = useApi<Logo>(`/orgs/${orgId}/logo`);
  useEffect(() => {
    const changed = (event: Event) => {
      if ((event as CustomEvent<string>).detail === orgId) logo.reload();
    };
    window.addEventListener(CHANGED, changed);
    return () => window.removeEventListener(CHANGED, changed);
  }, [orgId, logo.reload]);
  return logo;
}

function LogoImage({ data, name, onError, size = "medium" }: { data: Logo | null; name: string; onError?: () => void; size?: LogoSize }) {
  const dimensions = LOGO_SIZES[size];
  return data?.image_data_url ? <Image key={data.version} src={data.image_data_url}
    width={dimensions.width} height={dimensions.height} unoptimized alt={`${name} logo`}
    onError={event => { event.currentTarget.hidden = true; onError?.(); }}
    className={`${dimensions.className} max-w-full shrink-0 rounded object-contain object-left`} /> : null;
}

/** The caller keys this component by org ID so another tenant's image never flashes. */
export function OrganizationIdentity({ orgId, name }: { orgId: string; name: string }) {
  const logo = useLogo(orgId);
  const branding = useBranding(orgId);
  const [failedVersion, setFailedVersion] = useState<string | null>(null);
  const usableLogo = !logo.error && !!logo.data?.image_data_url && failedVersion !== logo.data.version;
  const showName = branding.error || branding.data?.show_name_in_header !== false || !usableLogo;
  return <span className="flex min-w-0 max-w-full flex-wrap items-center gap-3 text-base font-medium text-white/90">
    <LogoImage data={logo.error ? null : logo.data} name={name} size={branding.data?.header_logo_size ?? "medium"} onError={() => setFailedVersion(logo.data?.version ?? null)} />
    {showName && <span className={`min-w-0 break-words ${NAME_SIZES[branding.data?.header_name_size ?? "medium"]}`}>{name}</span>}
  </span>;
}

export default function OrganizationLogoSettings({ orgId, name, editable }: { orgId: string; name: string; editable: boolean }) {
  const logo = useLogo(orgId);
  const branding = useBranding(orgId);
  const input = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(""), 5000);
    return () => window.clearTimeout(timer);
  }, [message]);
  async function save(remove: boolean) {
    if (inFlight.current || !logo.data || conflict) return;
    inFlight.current = true; setBusy(true); setError(null); setMessage("");
    try {
      const version = logo.data.version ?? "none";
      if (remove) await api.delete(`/orgs/${orgId}/logo?expected_version=${encodeURIComponent(version)}`);
      else if (file) await api.upload<Logo>(`/orgs/${orgId}/logo`, file, { expected_version: version });
      else return;
      setFile(null); if (input.current) input.current.value = "";
      setRemoving(false); setMessage(remove ? "Organization logo removed." : "Organization logo saved.");
      window.dispatchEvent(new CustomEvent(CHANGED, { detail: orgId }));
    } catch (invalid) {
      setError((invalid as Error).message);
      if ((invalid as { status?: number }).status === 409) setConflict(true);
    } finally { inFlight.current = false; setBusy(false); }
  }
  const disabled = busy || logo.loading || !logo.data || conflict;
  return <section aria-label="Organization branding" className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-4">
    <h2 className="text-lg font-medium text-white">Organization logo</h2>
    <p className="text-sm text-white/60">Shown in the organization header. Static PNG, JPEG or WebP; up to 2 MiB and 2048 pixels per side. Stored as a metadata-free PNG up to 512 pixels per side.</p>
    <HeaderBrandingSettings orgId={orgId} editable={editable} />
    {logo.loading && <p role="status" className="text-sm text-white/60">Loading organization logo…</p>}
    {!logo.loading && !logo.error && !logo.data?.image_data_url && <p className="text-sm text-white/60">No organization logo set.</p>}
    {!logo.error && <LogoImage data={logo.data} name={name} size={branding.data?.header_logo_size ?? "medium"} />}
    {(error || logo.error) && <p role="alert" className="text-sm text-red-300">{error || logo.error}</p>}
    {message && <p role="status" className="text-sm text-white">{message}</p>}
    {(conflict || logo.error) && <button type="button" disabled={busy} onClick={() => { setConflict(false); setError(null); setFile(null); setRemoving(false); if (input.current) input.current.value = ""; logo.reload(); }} className="text-sm text-cyan underline">Reload organization logo</button>}
    {editable ? <div className="space-y-3">
      <label className="block text-sm text-white">Organization logo file
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled || removing}
          className="mt-1 block max-w-full text-sm text-white/70" onChange={event => {
            const next = event.target.files?.[0] ?? null; setError(null); setMessage("");
            if (next && (next.size > LOGO_MAX_BYTES || !["image/png", "image/jpeg", "image/webp"].includes(next.type))) {
              setError("Choose a PNG, JPEG or WebP up to 2 MiB."); setFile(null); event.target.value = "";
            } else setFile(next);
          }} />
      </label>
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={disabled || !file || removing} onClick={() => void save(false)} className="rounded-md bg-cyan px-3 py-2 text-sm text-navy disabled:opacity-50">{busy ? "Saving…" : "Save logo"}</button>
        {logo.data?.image_data_url && <button type="button" disabled={disabled || removing} onClick={() => setRemoving(true)} className="text-sm text-cyan disabled:opacity-50">Remove logo</button>}
      </div>
      {removing && <ConfirmPanel label="Remove organization logo" message={`Remove the logo for ${name}? The organization name will remain visible.`} confirmLabel="Confirm removal" busy={busy || conflict} onConfirm={() => void save(true)} onCancel={() => setRemoving(false)} />}
    </div> : <p className="text-sm text-white/60">Only organization admins can change the logo.</p>}
  </section>;
}
