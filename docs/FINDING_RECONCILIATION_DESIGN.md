# Individual imported-finding archive and scan reconciliation

11 November local integration: the authorized durable absence-review queue
from the second worktree is now included with review corrections. It records
historical keep-active/reopen notes without changing findings or scores;
local acceptance passed (1,723 backend tests, 567 frontend tests, 99 Chrome
checks, builds/security), and the app is active at 0049. Hosted CI is verified
on the exact pushed SHA at delivery. [Current review](ABSENCE_REVIEW_RELEASE_REVIEW.md).
This supersedes earlier statements that this feature is excluded; older dated
test/CI results remain historical.

[Canonical selection](CANONICAL_FINDING_REVIEW.md) adds the reviewed designation
and immutable receipt for two independently bound native findings. Both records
and their histories remain independent; consolidation/payload publication,
suppression/disposition and reappearance reconciliation remain separate
implementation gates. A durable absence-candidate snapshot queue with
keep-active/reopen review decisions is implemented locally; it does not change
finding state.

Implemented PB-1.3 review increments are documented in
[cross-import identity review](CROSS_IMPORT_IDENTITY_REVIEW.md) and
[canonical selection](CANONICAL_FINDING_REVIEW.md): admins may compare supported
native Nessus observations, explicitly carry forward a same-finding mapping, and
record/revoke a canonical designation for a reviewed conflict. The records and
histories remain independent. These operations do not merge findings, publish
new scanner payloads, mark findings absent, suppress or resolve findings.

7 November 2026: PB-1.3 adds a read-only [identity foundation](FINDING_IDENTITY.md).
Migration 0046 adds optional administrator-reviewed tool/asset bindings;
observations still remain ineligible for reconciliation.
Candidate diagnostics do not change import matching or authorize reconciliation.

PB-1.1 now implements the additive [source observation foundation](FINDING_OBSERVATIONS.md).
PB-1.2 adds [source-scan declarations and metadata comparison](SCAN_SNAPSHOTS.md),
which alone does not validate finding identity or enable suppression/reconciliation.
The existing-behavior analysis below describes the baseline before that increment.
Observations now record repeated occurrences; reviewed stable-identity bindings,
cross-import review and canonical designation are implemented. Refreshed
canonical payloads, suppression/disposition and automated reappearance
reconciliation remain pending. The local scan comparison has a bounded,
read-only candidate preview and a separate explicit save action for durable
candidate/context snapshots. Keep-active and reopen decisions are append-only
review history only; they do not change existing import matching, finding state
or archive ownership.

Status (8 November 2026): identity/review foundations are implemented through
migrations 0046-0048 and hosted CI is green for those commits. The bounded
absence-candidate preview and migration 0049 durable queue are implemented
locally. The focused PostgreSQL scan-snapshot suite passes 47 tests, and the
focused frontend queue suite passes 11 tests; changed-file lint and TypeScript
validation pass. The queue retains copied comparison/candidate context after
source observations/declarations are removed and does not mutate findings.
Chrome verification and hosted CI for migration 0049 remain pending. The
approved future semantics below remain design constraints, not delivered
behavior: suppression must be retained until explicit organization-admin
clearance independent of archived-row purge;
newer eligible observations may refresh severity/details only through a separately
reviewed publication design, without overwriting workflow decisions or saved
report snapshots. Absence requires comparable complete scans and explicit review;
ambiguous identity is ineligible. Absence never automatically resolves or archives
a finding.

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
