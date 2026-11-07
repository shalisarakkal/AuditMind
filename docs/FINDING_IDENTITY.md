# Stable finding identity foundation (PB-1.3, increment 1)

Implemented 7 November 2026. This is a read-only candidate identity contract,
not reconciliation, suppression, canonical merging or imported-finding archive.
Legacy import matching and scoring/report/workflow behavior remain unchanged.

## Versioned contract

`finding-identity-v1` hashes a structurally serialized tuple containing the
organization UUID, server-established tool-instance UUID, canonical asset UUID,
source mapping version and normalized native finding instance. It excludes
filename, upload/row/finding UUID, description, CVE, severity and mutable details.
Matching candidates indicate equal identity material, not authorization or proof
of resolution. Scope/configuration still belongs to scan comparability.

The first reviewed mapping is `nessus-plugin-service-v1`: native Nessus parser,
source `nessus`, no profile, positive numeric plugin ID, port 0 through 65535,
and tcp/udp/icmp/icmpv6 protocol. Numeric zero port is valid for host-level items.
Numeric values normalize leading zeros; protocols normalize case and surrounding
whitespace. Unknown protocols, missing fields, booleans/floats, oversized values
and unreviewed parser paths produce no key. Identifier tokens are not truncated.

| Source | Mapping in this increment |
| --- | --- |
| Native Nessus | Plugin ID + port + protocol; trusted tool/asset bindings still required. |
| Generic CSV/JSON (including source labelled Nessus/Qualys) | No reviewed mapping. Supplied IDs remain untrusted source data. |
| Asset-bearing profiles and aggregated events | No reviewed mapping; generated rule/category is insufficient. |
| Manual findings | No imported observation identity is inferred. |

`IdentityBinding` is an internal contract for a future trusted resolver, not an
HTTP/upload schema. Its organization must match the requested identity namespace;
all three IDs must be nonzero UUIDs. Hostname/IP/cloud ID, uploaded instance IDs,
a scan declaration and a legacy deduplication match cannot establish this binding.
Increment 1 did not construct bindings. Increment 2 below adds an explicit
administrator review resolver; uploaded claims still cannot construct bindings.

## Read-only diagnostics and performance

The existing tenant-scoped observation-history endpoint adds `identity_assessment`:
version, mapping, normalized source material, candidate_key and blocking_reasons.
The initial unbound assessment is derived on the existing bounded page
(20 default, 100 maximum) without extra queries. Reviewed bindings use a fixed
number of bounded queries (latest decisions, tools, source/canonical assets,
scans and finding lifecycle); no inventory scan or per-observation query.
Migration 0046 adds two indexed binding/namespace tables only. Imports do not
write them or resolve bindings while processing rows.
Historical observations are assessed using their captured source identity; this
does not rewrite them or confer verification retroactively. Invalid/missing
source data stays blocked. A new identity algorithm must use a new version.

In Chrome: Findings -> row Workflow -> Show source observations -> expand
Identity assessment on an observation. Native Nessus shows its mapping version;
generic/profile rows show No reviewed mapping. Candidate remains unavailable
until trusted tool/asset bindings exist; administrators can expand Review identity
binding on eligible native Nessus observations. Not eligible for reconciliation remains
visible. This read never updates finding status, archive state, scores or reports.

## Remaining PB-1.3 work

1. Extend the explicit per-observation bindings below with reviewed cross-import
   propagation and source-specific ambiguity/collision handling. No implicit reuse.
2. Establish canonical duplicate resolution, collision/conflict handling and source
   payload publication without losing observations or reviewed workflows.
3. Compare eligible complete snapshots and build an explicit not-observed review
   queue. Absence alone never resolves, suppresses or archives a finding.
4. Add reviewed suppression, reappearance, restore and purge semantics with shared
   lock ordering and tenant/role/version fences.

See [reconciliation design](FINDING_RECONCILIATION_DESIGN.md),
[scan snapshots](SCAN_SNAPSHOTS.md) and [observations](FINDING_OBSERVATIONS.md).

## Local verification - 7 November 2026

62 backend tests passed (identity validation, namespace isolation, legacy matching,
observation API and batching), plus 4 observation component tests and 93 real
Chrome workflow checks, including identity diagnostics at 320px and scoped Axe.
Lint and production build passed. No external AI usage; no migration required.
These are local results, not hosted CI or production-scale certification.

## Increment 2: reviewed tool and asset bindings (7 November 2026)

Migration 0046 adds organization-scoped tool namespaces and append-only reviewed
observation bindings. Organization admins register a Nessus instance with a reason,
choose that stable namespace and the canonical asset UUID, explicitly confirm the
mapping, and supply a review reason. The default asset UUID is the captured
source asset; changing it is an explicit mapping, never an asset/finding merge.
These are authorized administrator attestations, not scanner-authenticated claims.

Registration is a separate immediate write. Retired names cannot be reused;
retirement increments the namespace version and disables all its bindings. Names
are unique case-insensitively through the serialized API. New observations never
inherit bindings automatically, even when the legacy importer matches a finding.
Two separately reviewed native observations share a candidate only when tool,
organization, canonical asset, mapping and native service components match.

Each binding/revoke appends a numbered decision with reason, actor label and
captured source/canonical context, plus an Activity event in the same transaction.
Expected decision and tool versions reject stale saves. Organization write
admission fences membership/lifecycle changes and serializes competing reviews;
no import-wide lock or large data rewrite is used. Auditors/viewers/platform
read-only access cannot review or register namespaces for an organization.

Read-time checks withhold candidates for revoked decisions, retired/changed tools,
missing/archived source or canonical assets, changed asset identifiers/type,
missing/archived/incomplete source scans or changed captured source context, and
archived findings. If the same retained asset is restored with exactly its
reviewed identity, its existing mapping may become current again; revocation and
tool retirement require an explicit new decision/namespace. This is identity
material only: it never authorizes absence, suppression, risk exclusion or proof
of remediation. Future reconciliation must independently validate atomic source
snapshots and current lifecycle state.

Bindings live with observations. Deleting an observation deletes its binding
history; deleted tools/assets null their live references and cannot yield a key.
This is not the future independent suppression tombstone/retention mechanism.
Original-upload purge may remove findings and their observations under existing
ownership rules; this increment does not change those rules.

API: GET/POST `/orgs/{org}/identity-tools`, POST `/{tool}/retire`, and
GET/PUT `/orgs/{org}/findings/{finding}/observations/{observation}/identity-binding`,
POST `.../identity-binding/revoke`. All are tenant-scoped; writes require admin.
Chrome: open a native Nessus finding's Workflow -> Show source observations ->
Review identity binding. Register/select the scanner, verify the source/canonical
asset, enter a reason, check the confirmation and save. Reopen to revoke, or select
a tool and explicitly confirm retirement. A conflict retains the draft and
requires Reload identity context before another attempt. While saving, the parent
workflow cannot be dismissed; accepted writes are never cancelled by dismissal.

Increment 2 validation: 78 backend tests passed, including identity boundaries,
review/revoke, retirement, asset/scan/finding lifecycle, same-tool repeated
observations, competing first reviews, observation batching and real migration
upgrade/rollback/schema drift. A later cross-tenant canonical-asset recheck also
passed. Frontend: 542 passed; Chrome: 94 checks including real native registration,
binding, revocation, 320px layout and scoped Axe. Build/lint pass; no AI usage.
Activated locally at 0046 only after idle-queue checks; no production deployment.
These changes remain uncommitted, with hosted CI pending an authorized push.

Release review: mapping edits/pagination now clear confirmation, cancelled reviews
reopen fresh, newly registered tools remain selectable beyond the first page,
and retirement freezes/names its target in a blocking application dialog with
safe Cancel focus. Escape dismisses only that confirmation and preserves the
underlying editor. See [release review and complete tests](IDENTITY_RELEASE_REVIEW.md).

Review context pins the identity algorithm version, source mapping and normalized
source material. A changed contract does not silently reuse old approval: candidates
are withheld until explicit re-review. Pre-release prototype bindings without that
context also require fresh review; they are not automatically backfilled.
The API exposes reviewed_identity_version/reviewed_source_mapping alongside current
assessment metadata. See IDENTITY_RELEASE_REVIEW.md for reproduced defects,
complete-test checkpoints and final per-commit release gates.
