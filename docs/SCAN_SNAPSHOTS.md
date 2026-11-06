# Scan snapshot declarations and comparison review (PB-1.2)

PB-1.2 adds source-scan declarations and an informational metadata comparison.
It does not compute missing findings or change findings, workflow, archive
state, scores, qualifications or saved reports. No AI provider is called.
Finding reconciliation and stable identity verification remain PB-1.3 work.

## What is captured and what is declared

Migration `0041` adds `scans.ingestion_config_fingerprint` and
`scan_snapshot_declarations`. Existing scans are not backfilled or automatically
declared complete. Reimporting creates a new scan with captured configuration;
an exact-duplicate upload skipped by policy does not create one.

The importer captures the effective settings/profile, input kind/format and a
revision of the installed core parser source, Python runtime and parser-library
versions. Its stable SHA-256 identity is
stored with the import outcome. It is never accepted from a client or rebuilt
from today's settings for an old scan. Source line endings are normalized for
cross-platform consistency. Core parser changes conservatively invalidate
comparability, including comment-only changes in the covered source files.
The installed revision is captured at process import; deployments must restart
API/worker processes rather than mutate source files under running processes.
Parser changes also invalidate old staged-read fingerprints, so a resumed job
rereads its kept file under the effective configuration instead of mixing rules.
This hashing does not add a per-row or inventory-wide scan.

An organization admin or auditor explicitly declares:

- Source snapshot type: Complete, Partial, Incremental, Failed or Cancelled.
  This describes the external source scan; internal import job states retain
  their existing Pending/Running/Completed/Failed meanings.
- Source snapshot time: when the external scan completed or snapshot was taken.
  Enter it in browser local time; the API requires an offset and stores UTC.
  Complete requires it. Unknown time is allowed only for non-complete snapshots.
  It cannot be after import completion or outside the valid UTC timestamp range.
- Tool name, stable tool-instance ID and external tool-configuration/policy ID.
- Target scope, exclusions and unreachable targets: one opaque identifier per
  line, up to 500 entries per list and 255 characters per entry. CIDRs, immutable
  host/resource IDs or versioned scope/group names can describe large scopes.
- Whether the source assessed every declared target apart from exclusions,
  and a required rationale.

These are attributed operator assertions, not verified scanner connector or
inventory manifests. Named groups can change membership without changing their
names; this increment cannot verify that. Tool/scope entries are trimmed,
deduplicated and sorted, but are otherwise compared exactly and case-sensitively
to avoid guessing identity for arbitrary resource identifiers. Use stable,
versioned identifiers, not filenames or descriptions.

Only successfully completed imports with captured configuration and a verified
import report can receive declarations. A Complete declaration additionally
requires confirmed coverage, no unreachable targets and no import errors,
skipped items or warnings. This is deliberately conservative: even intentional
asset skips or skipped Nessus Info items prevent Complete. Use an appropriate
non-complete declaration; do not change ingestion policy just to pass review.
An incomplete-import rejection leaves the draft editable so its type can be
changed without discarding input; only a true version conflict requires reload.
An incomplete archive/restore/purge operation in the organization blocks a new
declaration and metadata compatibility, including stopped operations.

## Revision, permissions and lifecycle

Every save appends a declaration version containing the input, actor, rationale,
timestamp and server-owned scan context (scan UUID/type/profile/source, filename,
content hash, times and captured configuration). A correction appends another
version; revocation appends a Revoked version and requires a reason. Existing
versions are not overwritten. Activity records declaration/revocation UUIDs,
versions and rationale. A later fresh declaration can supersede a revocation.

Writes use expected-version checks and scan-row locking, with the existing
job-admission/organization lock ordering. The writer's membership is rechecked
under lock. Concurrent edits cannot silently overwrite each other. Stale drafts
remain visible until the user explicitly reloads or cancels them. Viewers and
platform read-only users may inspect and compare but cannot declare or revoke.
All API paths are scoped to organization membership and scan identity.

Soft archive retains declarations, but archived scans cannot be used by these
active-upload APIs. Purging the scan cascades to its declaration history; this
is not an independent permanent suppression record. Existing upload/finding
archive ownership and retention behavior is unchanged.

## What comparison means

The review names the exact baseline/current scans and declaration versions. It
checks current lifecycle/completion, active declarations, confirmed Complete
coverage, chronological ordering, matching tool instance/configuration, actual
import type/profile/source and captured import configuration. It reports target
and exclusion differences and shows both scans' exclusions/unreachable targets.
The current **source snapshot time** must be after the baseline's source time;
upload completion times do not establish source chronology. Re-uploading an old
export does not make it a newer source scan. Missing captures,
missing/stale/revoked declarations, failed/partial/incremental/cancelled source
snapshots, unreachable targets, changed scope or configuration all block a
matching-metadata result.

**Declared metadata matches is not permission to infer absence.** Every response
has `absence_eligible=false`, an explicit identity/reconciliation blocker and
`not_observed_finding_ids=null`. Null means not evaluated, not an empty list of
missing findings. No source observation is promoted to reconciliation eligible.
Declaring a tool-instance ID does not configure a connector or verify/bind the
IDs on individual source observations; that requires the later identity work.
No severity, status, assignee, deadline or archive decision changes.

The comparison is a read-only, non-persisted review at the displayed time, not
a durable authorization token. Reload and review again after source lifecycle
or declaration changes. Both displayed versions are supplied to the server;
a stale or missing version is rejected. Snapshot GETs and comparison responses
are `Cache-Control: no-store`. Reviews read a few indexed metadata rows, not
the organization's assets/findings or broad exact counts.

## Chrome verification

For a synthetic non-production organization, these clean sample files avoid
parser-error blockers: [baseline](examples/scan-snapshot-baseline.csv) and
[current](examples/scan-snapshot-current.csv). They describe one synthetic host
and the same finding key. The source times are in each file's `observed_at`;
after import, Findings → Workflow → Source observations displays those times in
the browser timezone for use in the declaration. Use tool `Synthetic scanner`,
instance `snapshot-demo-1`, configuration `synthetic-v1` and target scope
`snapshot-demo-host`, with no exclusions or unreachable targets. Importing these
files adds synthetic data; they are not real security evidence.

1. Reimport two small compatible findings files with the same parser and effective
   settings. Use Reimport if duplicate policy would otherwise skip them.
2. On **Uploads**, clear any bulk selection and open the first row's **Snapshot**.
   Old uploads without captured configuration explain that reimport is needed.
3. Select **Declare snapshot**. Enter tool/instance/configuration identifiers and
   target scope and source snapshot time. Choose Complete only when justified, confirm coverage, supply a
   rationale and save. Check version, declarer and recording time.
4. Select **Use as baseline**. The pinned filename remains visible across paging
   and filtering. An organization change or full reload clears this UI-only pin.
5. Open the later upload's Snapshot and save a suitable declaration. Select
   **Review against baseline**, then **Review compatibility**. Check both named
   snapshots, scope/exclusions, the metadata result and **Not approved for absence
   conclusions**, even when metadata matches.
6. Revise one declaration's target or configuration and compare again. The
   mismatch must be explicit. A partial/incremental/failed/cancelled declaration
   cannot produce a matching-metadata result.
7. Open a declaration in two tabs. Save in one, then try saving the stale draft
   in the other. It must require explicit reload and preserve the draft until
   then. Revoke with a reason; a new comparison must show the revocation blocker.
8. Confirm the finding's workflow, severity, archive state and saved reports did
   not change. A viewer can review snapshots but sees no mutation controls.

## API contract

- `GET /api/v1/orgs/{org_id}/scans/{scan_id}/snapshot`: live scan context, latest
  declaration and blockers; no declaration is represented by null.
- `PUT .../{scan_id}/snapshot`: append a declaration with `expected_version`
  (zero initially), all declaration fields and rationale.
- `POST .../{scan_id}/snapshot/revoke`: append revocation with expected version
  and rationale.
- `POST .../scans/snapshot-comparison`: baseline/current scan UUIDs and their
  displayed declaration versions; returns review metadata and explicit blockers.

Validation, Chrome evidence and local activation status are tracked in
[Phase 4 validation](PHASE4_VALIDATION.md). This increment does not authorize
production rollout, broader scoring enablement or SaaS capacity claims.
