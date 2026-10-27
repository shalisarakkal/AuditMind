# Trying approved product logos

Replace these fixed files, keeping their names:

| Purpose | Repository file |
|---|---|
| Complete product logo / wordmark | `frontend/public/branding/product-logo.svg` |
| Browser-tab icon | `frontend/public/branding/favicon.svg` |

The shared component loads the first file on sign-in/register and in the sidebar.
The signed-in header shows organization identity only, not a duplicate product logo.
It does not append separate product-name text. The
compact image defaults to 180×48 CSS pixels; authentication uses 240×72. Both
preserve aspect ratio without cropping. Use a horizontal logo,
tightly fitted SVG `viewBox`, transparent background and colors visible on navy.
Text converted to paths gives more consistent results across machines.

## Platform-admin size setting

Sign in as the platform admin and open **Platform → Product branding**. **Sidebar
product logo size** saves automatically for every organization: Small 144×40px,
Medium 180×48px (default), Large 192×64px. The sidebar's available width bounds
the image; it is not cropped or stretched. No asset replacement/rebuild is needed
to change this setting. Other sessions see it on refresh. Sign-in/register,
favicon and organization logo/name sizes are independent and unchanged.

The authenticated GET `/platform/branding` returns only display size/version;
organization admins/viewers can read but cannot PATCH it. PATCH requires the
platform-admin role, a valid size and `expected_version`; stale writes return 409
and the UI requires **Reload product branding**. A transaction-level PostgreSQL
advisory lock also fences concurrent first saves before a settings row exists.
The actor's active/platform role is rechecked after acquiring the lock. Actual
changes are audited to Platform activity; no-op saves do not rotate versions or
add misleading events. Stored under `platform_settings.product_branding`; no new
migration is needed. Failures leave sidebar rendering at the default size.

The browser icon should be a simple square SVG, legible at small sizes. These are
independent files: trying a product wordmark does not automatically replace the icon.
The original generated defaults were provisional. User-supplied SVG artwork is now
installed at the fixed active paths; the application does not rewrite that artwork.

## Compare variants in the local demo

1. Keep approved originals/alternate designs outside `frontend/public`.
2. Copy the selected **genuine SVG** over `product-logo.svg`. Replace `favicon.svg`
   separately if desired. Do not rename PNG/JPEG bytes to an SVG extension.
3. In the running local demo, replacing an existing fixed asset normally needs
   only Ctrl+F5, not a rebuild. Rebuild/restart when application code changes,
   adding new asset paths, or when deployment packaging requires it. From the
   repository root (existing data/passwords retained):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -Stop
   powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
   ```

4. Check sign-in, sidebar and a narrow window. The header retains company branding.
   Favicons can cache separately; reopen the tab or use a fresh private window.
5. Repeat with another approved SVG using the same filenames. No source-code
   edits are needed. In `npm run dev`, replacement normally needs only a refresh.

Only trusted, reviewed SVGs without scripts, external resources, embedded HTML
or tracking links belong here. Files are public and shared across all tenants;
this is not an untrusted-upload endpoint and must contain no private data.

Company/organization logos remain separate under **Settings → Organization logo**.
They do not replace the product assets. Existing saved reports/PDFs are unchanged.
The legacy `/brand.svg` remains available for compatibility, but metadata now uses
`/branding/favicon.svg`.

Local verification: 383 frontend tests, lint/TypeScript/production build and 43
installed-Chrome checks passed. Includes actual SVG loading on sign-in/sidebar/
header, favicon metadata and mobile/accessibility regressions. Backend unchanged.
The authentication layout uses one larger logo above the card, with no duplicate
brand inside the form. Sign-in, registration and signup-closed share this layout.
