# PB-1.4 - Organization-managed asset context

Implementation and local review are complete. Migration 0059 is not activated in the normal application; its current schema remains 0058. No normal-service restart or broader feature opt-in is part of this work so far.

## Field and permission contract

Managed owner, environment and business criticality are independent of the existing scanner-supplied asset environment, criticality, tags and details. Existing assets start Unassigned/Unknown without copying scanner classifications. Owner must be a currently active organization member when assigned; owner metadata does not grant access. Organization admins and auditors may edit; members and platform read-only viewers may read. Platform privilege alone does not authorize organization edits.

Environment is trimmed text up to 50 characters, with blank meaning Unknown. Business criticality is Critical, High, Medium, Low or Unknown. Owner changes, clears and environment/criticality changes require a rationale and the expected context version. Identical current-version saves do not create history or increment versions. Stale versions fail even when a draft happens to equal the current values. Clearing all context preserves its generation to prevent version reset/ABA.

The context retains an owner UUID and saved name/email label after account or membership removal; it never uses that reference as authorization. Reads resolve current member labels only within the same organization and mark inactive/former owners explicitly. Past history retains the label captured with that decision. A former/inactive current owner can be kept while other context is edited; new assignment to an unavailable owner is refused.

## Storage, lifecycle and concurrency

Migration 0059 adds `asset_contexts`, `asset_context_history` and an independent organization context-revision lane. It does not add/backfill fields or rebuild indexes on the large assets table. Database guards enforce tenant ownership, new-owner eligibility and immutable context ownership; retained context/history prevents an asset's raw tenant transfer. An asset-scoped try-lock fences that rare transfer against a first context write without locking normal scanner updates.

Context/history commit atomically with Activity and context-revision invalidation. Context edits take KEY SHARE on the source asset, so normal non-key scanner updates can proceed. Their revision row is separate from the long-running import's list revision. Edits are refused while the asset or its creating upload has an unfinished archive/restore/purge operation. Archive/restore retain context and history. Explicit asset purge removes its context/history by cascade; Activity follows its existing retention policy. Downgrade refuses retained context, history or nonzero context revisions until reviewed export/rollback.

Readiness checks fail closed for absent tables/functions or disabled/missing guards. A pre-activation asset list still works and reports context unavailable; managed filters and writes require complete activation.

## Lists, UI and scope

Assets exposes Organization context alongside the scanner fields, plus managed-owner, managed-environment and business-criticality filters. Blank filters mean Unassigned/Unknown. Common text search includes managed values and scoped owner names/emails. Context payloads are batch-loaded only for the selected list page. Metadata GET/PATCH paths read narrow asset columns rather than scanner JSON payloads.

The source search's selective indexed path is preserved. Where the separate context query is estimated at at most 5,000 matches, narrow source/context ID candidates can be combined. That estimate chooses strategy only; it never truncates matches or changes exact counts. Broad/short searches retain fallback semantics and still have their existing cold-count costs. Current source-sort/seek behavior remains; this increment adds filters, not business-context sorting.

Row actions are disabled during multi-row selection. The context dialog has a neutral Cancel/Close and a filled primary Save context. A save blocks dismissal; a stale/failed response retains the draft and requires explicit reload review. Discard confirmation belongs to the application. A genuinely unknown outcome says the request may have committed; Close and refresh reloads the list without another write. History shows changed fields with readable owner labels, rationale, actor and browser-local time.

These fields do not change finding workflow, identity bindings, evidence qualification, Dashboard scores or saved reports. Future contextual scoring/control mapping needs its own approved design. PB-1.3 manual acceptance, pilot/production, broader evidence-qualified scoring and SaaS scale holds remain separate.

## API

- `GET/PATCH /orgs/{org}/assets/{asset}/context` reads or changes one fixed asset.
- `GET /orgs/{org}/assets/{asset}/context/history?limit=20&before_version=...` pages retained history.
- `GET /orgs/{org}/assets/context-facets` supplies managed filter values.
- The existing Assets list accepts `managed_owner`, `managed_environment` and `business_criticality` filters and returns an additive `context` object.

## Review evidence

Initial backend behavior tests passed after wiring the new Activity event. A real held scanner update reproduced a context-save lock timeout; the independent revision lane fixes it. The existing selective-search regression reproduced loss of the indexed path; bounded candidate-ID composition restores it. A metadata SQL probe reproduced imported-payload loading; narrow-column reads fix it. Dedicated logs are retained under `temp/pb14-*`; these are isolated local checks and do not constitute hosted CI, normal activation or SaaS capacity evidence. The final focused backend run passed 27 checks, including migration up/down/drift, quoted schema names, concurrent reviewers/imports, owner removal and a 5,000-asset indexed filter probe. The frontend suite passed 613 tests across 65 files; the full Chrome regression passed 112 checks. ESLint, TypeScript and the isolated production build passed; Bandit reported no high-severity findings. A further stale-history reload case was reproduced and fixed; its regression passes, and the final focused Chrome rerun passed 8 checks. The full backend regression passed 2,134 tests in 43m 5s. The focused 27-check run includes late-added cases and overlaps the full suite; these counts are not additive. Hosted CI and normal migration activation are not yet claimed.

## Chrome verification

1. After migration 0059 activation, sign in as an organization admin or auditor and open Assets. Existing rows show Unassigned/Unknown under Organization context.
2. Clear row selections and choose Edit context for one asset. Scanner attributes are shown separately. Search for an active member by name/email, select the owner, enter a managed environment and business criticality, add a rationale and save.
3. Reopen the same row. Confirm saved values, version and history; use the managed filters to locate it. Source environment/criticality remain unchanged. Reimporting the source must retain the managed values.
4. Open the same asset in two separate browser sessions before saving. Save in one; the other must report a conflict and retain its draft until an explicit reload. A read-only member must have View context without editing controls.
5. Archive and restore the asset. Its context/history return with it. An archived asset cannot be edited; permanent asset purge removes its sidecar context/history.

The automated Chrome exercise covers these flows using isolated synthetic records, including unknown save outcomes and narrow/mobile display. It does not modify the normal inventory.
