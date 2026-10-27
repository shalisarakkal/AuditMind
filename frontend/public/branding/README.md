# Replaceable product branding

Replace `product-logo.svg` with a trusted, approved SVG **using that exact name**.
It is the complete product logo/wordmark: the application does not add separate
AuditMind text beside it. Sign-in/register and sidebar use this asset; the
application header shows only the organization name/company logo.
Compact placement defaults to 180×48 CSS pixels; authentication uses 240×72.
Platform admins can choose Small 144×40, Medium 180×48 or Large 192×64 under
Platform → Product branding, without replacing the asset. Organization admins
cannot edit this platform-wide preference; other sessions update on refresh.
Both preserve aspect ratio without cropping, shrinking within available width.
Prefer a horizontal logo with a tightly fitted `viewBox`, transparent background,
and artwork legible on dark navy. Outline text to avoid platform font differences.

Replace `favicon.svg` independently with a square, simplified browser-tab icon.
The original generated defaults were provisional; user-supplied SVGs are now at
the fixed active paths. Replacing them does not require source-code changes.
Do not rename a PNG/JPEG file to `.svg`; provide a genuine SVG or request a code
change to use the correct image format. Use only trusted SVGs without scripts,
external resources, embedded HTML/foreignObject, or tracking links.

Both files are public product assets, shared by every organization. They are not
company/organization-logo uploads and must contain no private data. Only trusted
developers/operators should replace them; this is not a user-upload endpoint.

To compare variants, keep originals/alternatives outside `frontend/public`, copy
the selected approved SVG over the fixed filename, then Ctrl+F5. Replacing an
existing asset in the local running demo normally does not need a rebuild.
For application-code changes/new asset paths or packaged deployments, rebuild:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -Stop
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
```

Run from the repository root. Refresh with Ctrl+F5. Browsers may cache favicons
separately: close/reopen the tab, or test a fresh private window if needed.
In development (`npm run dev`), file replacement normally needs only a refresh.
The old `/brand.svg` remains a compatibility asset but is no longer the active icon.
