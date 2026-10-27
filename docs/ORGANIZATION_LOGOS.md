# Organization logos

Local Phase 4 tenant branding. Saved reports/scoring are unchanged; this is not
an external image service or production upload-hardening approval.

## Use in Chrome

1. Sign in as an organization admin and select the intended organization.
2. Open **Settings → Organization logo**. Choose a static PNG, JPEG or WebP.
3. Click **Save logo**. Settings and the common header show the saved image.
   Reload to verify persistence. Choose another file and save to replace it.
4. **Remove logo** opens confirmation; Cancel preserves it, Confirm removal
   removes it. The organization name always remains visible.
5. Viewers/auditors can view but cannot change logos. Archived organizations
   are read-only. Other organizations cannot read the image.
6. Concurrent tabs/admins: stale save/remove receives 409 and requires
   **Reload organization logo**. Reload clears the staged file/confirmation;
   choose the file again before retrying. No silent overwrite.

Other tabs/users see changes on reload. The same-window header refreshes after
successful changes. Missing/unavailable header images fall back to the org name.

## Validation and API

**Header company name size** controls only the common header's organization name:
Small 16px, Medium 20px (new default), Large 24px. It saves automatically for the
organization and is admin-only; the organization selector and other text remain
unchanged. Hidden names stay hidden while a usable logo exists; missing/broken
logos still show the name using the selected size. Narrow headers can wrap.
Migration **0028** adds constrained `organizations.header_name_size`, default
`medium`, preserving logos and existing visibility/logo-size settings. Downgrade
drops only name sizing. Branding GET returns it; PATCH supports optional paired
`header_name_size` / `expected_header_name_size` (small/medium/large). Omitted
fields preserve the current value for older clients. Stale expected values
reject the whole update with 409 before any setting changes; writes are locked
and changed values are audited.

**Header logo size** is an admin-only, automatically saved organization setting:
Small 96×48px, Medium 160×64px (default), Large 224×80px. These are bounding boxes;
the image fits proportionally without cropping/stretching. Settings preview and
the common header share the selected size. The transparent square backdrop is
removed. Header content wraps on narrow screens; product/sidebar branding is not
affected. Transparent padding in the source image remains unchanged; a tighter,
higher-resolution source may still be needed for small/blurry artwork.

Migration **0027** adds constrained `organizations.header_logo_size`, default
`medium`, retaining existing images/preferences. Downgrade drops only the size
preference. Branding GET returns `header_logo_size`; PATCH accepts that field
with `expected_header_logo_size` (both small/medium/large), alongside the existing
name preference/expected value. Omitted size leaves it unchanged for older clients;
supplying only one of the size fields is invalid. Stale sizes return 409; changes
are locked, permission/lifecycle checked and audited like name visibility.

Admins can toggle **Show organization name beside logo** in the same Settings
section. Enabled by default, it saves automatically for the organization. Only
the header is affected; missing/unavailable/broken logos always show the name.
Logo alt text retains the organization name. Other sessions update on reload.
Migration **0026** adds `organizations.show_name_in_header`, default true; downgrade
drops only this preference. GET/PATCH `/orgs/{id}/branding` uses existing member-
read/admin-write lifecycle fences and no-store responses. PATCH requires strict
booleans `show_name_in_header` and `expected_show_name_in_header`; a stale value
returns 409 and requires reload. Writes lock the organization and record changed
values in Activity. No logo file replacement is required.

- Original file: at most **2 MiB**, **1–2048 pixels per side**. Decoded format
  must match PNG/JPEG/WebP content type. SVG, animations, malformed images and
  oversized/decompression-bomb inputs are rejected server-side.
- Decode, apply EXIF orientation, resize proportionally within 512×512, copy
  pixels into a fresh RGBA image and encode PNG. No original metadata, filename
  or original file is retained. Stored output at most 1 MiB, also DB-enforced.
- Existing streaming middleware caps the entire multipart logo request at
  **3 MiB**, including overhead, before parsing/auth dependencies. Declared size,
  chunked bodies and underreported lengths are checked. File limit stays 2 MiB.
- `GET /orgs/{id}/logo`: authenticated member or existing platform read access;
  returns `{version, image_data_url}`, both null when absent. PNG data URLs pass
  through the authenticated JSON client; no public URL or token-in-URL.
  `Cache-Control: no-store`.
- `POST /orgs/{id}/logo`: multipart `file`, `expected_version` (`none` if absent).
  `DELETE /orgs/{id}/logo?expected_version=...`: removal. Actual active org admins
  only, using the existing transactional role/lifecycle admission fence. Stale
  versions return 409, including remove/recreate and identical-image saves.
- Committed changes record `settings_changed` Activity events with action/version,
  never image bytes. Rejected writes do not record successful changes.

## Storage and migration

Migration **0025**, after 0024, adds `organization_logos`: one bounded binary PNG
and opaque version per org. The FK cascades on organization purge; no filesystem
or object-store cleanup is needed. Archive retains the logo for read-only viewing.
PostgreSQL backups include these small blobs. No pre-existing logos are migrated.
Downgrading 0025 deletes saved logos; other organization data is unchanged.

Apply using the existing environment-specific Alembic workflow after verifying the
database target. Local test/demo acceptance does not authorize production changes.

## Verification and limits

Backend tests cover formats/normalization/metadata, invalid/animated/oversize
images, tenant/role boundaries, stale writes/removal, rejected-write atomicity,
archive and cascade cleanup. Streaming tests cover declared/chunked/underreported
bodies. UI regressions cover save, read-only access, conflicts, confirmed removal
and preflight rejection. Chrome adds persistence/header/viewer/two-tab/removal
checks to the existing workflow suite. Final totals:
[Phase 4 validation](PHASE4_VALIDATION.md).

Historical initial logo acceptance: 1,260 full PostgreSQL tests, 382 frontend tests and 42
installed-Chrome checks passed, plus lint/build and migration round-trip/drift at
0025. These are earlier counts; current combined-tree and hosted evidence is in
PHASE4_VALIDATION.md. Subsequent header preferences extend the head through 0028.

Normalization is not malware-scanning certification. General upload throttling,
malware policy, production ACLs and hosting acceptance remain separate work.
