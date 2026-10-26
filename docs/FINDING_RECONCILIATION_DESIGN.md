# Individual imported-finding archive and scan reconciliation

Status: functional rules approved on 23 October 2026; implementation remains pending
as a separate increment after browser-timezone correction. User approved minimal
suppression retained until explicit organization-admin clearance, independent of
archived-row purge; newer successful observations refresh severity/details without
overwriting workflow decisions or existing report snapshots. Comparable complete
scan confirmation is required for absence flags; ambiguous identity is ineligible.
Existing upload/asset archive behavior and import matching remain
unchanged. Absence from a later file never automatically resolves or archives a finding.

## Existing Settings/import behavior reviewed

The organization override `asset_existing_strategy` takes precedence over global
`ASSET_EXISTING_STRATEGY` (default update). Settings labels correspond to the
asset-row publisher, not to finding remediation/absence decisions:

| Settings choice | Asset-bearing tool/profile rows | Associated findings |
| --- | --- | --- |
| Update it | Match an active asset; update supplied fields and merge details. | Add new finding keys; skip existing duplicate keys. Existing finding payload and workflow are not refreshed. |
| Leave it unchanged | Reuse the active asset without replacing its imported attributes. | Still process findings. New findings are recorded; duplicate keys skipped. It does not skip the entire host's findings. |
| Add a duplicate | Create a new asset rather than match the inventory asset. | Findings point to the new asset ID, so matching the old asset's finding key does not deduplicate them. Earlier workflow decisions do not transfer to the new findings. |

For finding-only rows without an asset payload, `_finding` instead matches the
active inventory directly and fills missing hostname/IP/cloud ID identifiers;
the asset-row strategy branch is not used. Therefore Leave unchanged is not a
universal prohibition on all asset identifier enrichment, and Add a duplicate
does not force new assets on that finding-only path. Keep these parser-path
differences explicit rather than advertising a global finding policy.

Current finding deduplication is `(asset_id, source, category)` or, when category
is null, `(asset_id, source, null, description)`, always within the organization.
Severity/domain and (when categorized) description are not part of that key;
duplicates return without refreshing those fields or workflow. Existing
null-source findings are excluded from the cross-import finding index.
Archived assets/findings are excluded from matching, so a later import can create
fresh active rows instead of honoring a past archive.

A repeated finding retains its original `scan_id`: there is no per-scan finding
observation row created for the later duplicate. The asset is linked to the later
scan, but that is not equivalent to finding observation provenance. This means
the current model cannot reliably support last-seen/absence reconciliation, and
archiving an original upload can affect findings repeated in a newer upload.
These are design gaps for the proposed feature, not newly changed behavior.

Code reviewed: `org_settings.resolve_ingestion_settings`,
`ingestion_service._Publisher.publish/_asset/_finding/_create_finding`,
`import_matching.AssetIndex/FindingIndex/finding_key`, and archive service matching.
Settings help currently says only hostname/IP; cloud ID and type-aware matching
also apply. A future wording update should explicitly distinguish asset settings
from finding deduplication/observation policies.

Read-only demo configuration check: SA01 currently resolves to **Update it**,
inherited from the global default with no organization-specific override. No
setting was changed. Focused regression run: **49 tests passed in 34.69 seconds**
on PostgreSQL with warnings as errors (import matching unit tests, profile imports
and finding imports). This is not another full backend run. Test DB restored to
0022 with 30 public tables, zero browser schemas and clean drift; demo untouched.

## Proposed compatibility with Settings

- Preserve all three asset strategies; do not reinterpret Leave unchanged as
  "ignore findings" or Update it as "overwrite remediation decisions".
- Separate canonical finding identity, scan observations and explicit suppression
  from asset attribute updates. Record repeated observations without duplicating
  the canonical finding or overwriting workflow notes/status/ownership/deadlines.
- For Add a duplicate, require an explicit canonical asset mapping before using
  cross-scan absence or suppression. Until such mapping exists, mark reconciliation
  unavailable; do not collapse intentionally separate inventory rows by hostname.
- Preserve parser-path differences during migration and cover both asset-bearing
  profiles and findings-only exports. Legacy dedup keys alone are not safe stable
  suppression identities, especially where ports/tool-instance IDs are absent.
- Add regression gates for every strategy × initial/repeated/changed/archived
  finding × parser path, changed source/category/severity, reviewed workflows,
  original-upload archive after repetition, and missing/ambiguous asset mapping.

## Required stable identity and comparable scans

An observation must be scoped by organization, connector/tool instance, stable
asset identity and the tool's stable finding identifier (for example QID/plugin ID),
plus port/protocol or other tool-specific instance discriminator where applicable.
CVE alone and description text alone are not reliable identities. Current generic
exports may lack these fields; ambiguous rows must not be automatically reconciled.

Comparable scans must be successfully completed, explicitly designated complete
snapshots, with the same tool/source, asset scope and compatible configuration.
Partial/failed/cancelled scans, unreachable hosts, changed scope or filters and
incremental exports must not create "not observed" conclusions. The operator must
see the baseline/current scans and excluded assets before accepting reconciliation.

## Individual archive contract proposed

- Admin/auditor explicitly archives a selected imported finding with a required
  reason. Preserve original observation/source/scan links and workflow history.
- Persist an organization-scoped suppression/tombstone keyed to stable identity,
  independent of soft-deleted rows, so duplicate import cannot silently recreate it.
- A later matching observation updates last-observed metadata but stays archived;
  show that it was observed again and allow explicit authorized restore/review.
- Changed or ambiguous identity does not inherit suppression. Surface uncertainty;
  never suppress a possibly different finding merely because its description matches.
- Restore must reconcile active duplicates without deleting reviewed decisions or
  history; define one canonical finding and retain observation provenance.
- Upload/asset archive, restore, purge and retention must explicitly account for
  independent finding suppression. Purging an old upload must not silently remove
  an unrelated suppression; retention policy and explicit suppression removal need
  operator-visible semantics. Minimal suppression remains until explicit admin
  clearance per the approved policy; full archived payload retains existing retention.

## Not observed is not resolved

Record an observation state separate from remediation status, including last seen,
baseline/current scan, reconciliation time and comparability justification.
"Not observed in latest comparable scan" is a review flag, not proof of remediation.
Keep the finding active and scoring unchanged unless an explicit existing workflow
decision changes its state. Show a review queue and evidence links; resolution still
requires verification. Reappearance clears the absence flag and records history,
without silently undoing an explicit archive or risk decision.

## Approval and implementation gates

Implementation must define and test stable-key mappings for each supported source,
snapshot/comparability declarations, suppression retention/purge behavior, canonical
duplicate handling and the UI review/restore flow. Requires schema/API design,
migrations, role/tenant checks and archive/import shared lock ordering.

Tests must cover partial and failed scans; changed scope; duplicate/ambiguous keys;
cross-tenant same IDs; repeated imports; suppression reappearance; concurrent
archive/import/restore; upload/asset retention/purge; conflicting duplicates;
atomic history; existing score/report invariants; browser permissions and recovery.

Approval of these functional rules does not mean implementation is complete. No
automatic reconciliation, individual imported archive or new absence flag exists
yet. Live inference and production release remain outside this approval.
