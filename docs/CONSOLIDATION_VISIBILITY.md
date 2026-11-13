# Consolidation visibility integration

Current follow-up: [Stage A release review](CONSOLIDATION_RELEASE_REVIEW.md) describes the local default-off proof/lifecycle/publication/UI implementation under final verification. The earlier checkpoint below retains its historical scope. No normal-data activation has occurred.

## Status: internal integration; publication disabled

12 November 2026. This follows the [metadata transaction component](CONSOLIDATION_TRANSACTIONS.md).
The private integration harness stages metadata and visibility in one caller-owned
transaction. No application route invokes it. Production `publish()` still rejects
all requests; no Apply/Undo UI or normal-data publication is enabled.
PB-1.3 remains partial. Group-aware proof, lifecycle/reappearance admission,
policy authorization, Activity events and guarded UI must be completed before
publication opens.

## Behavior

For a reviewed pair A/B whose canonical finding is A:

- Both physical findings, UUIDs, observations, source ownership and workflow
  histories remain. B is marked as the current alias; A remains visible.
- Shared active lists, filters, counts, Dashboard inventories, deterministic
  scores and new report inputs use A once. A filter that matches only B returns
  no visible finding. This increment does not merge the source payloads.
- Metadata, visibility, list-count/cursor revisions, evidence revision and
  Dashboard invalidation commit together. An error rolls all of them back.
- A Dashboard capture started before the change cannot publish stale totals
  afterward. Reads reject snapshots from an older consolidation revision.
- Alias removal is not a verified risk exclusion. Recorded totals distinguish
  retained aliases from visible findings and verified exclusions. A report scope
  containing only aliases is not assessed, rather than receiving a perfect score.
- Existing saved reports remain immutable. New report context records bounded
  consolidation provenance; internal UUID provenance is excluded from AI prompts.
- A physical-finding approval cannot exclude a current consolidated group from
  risk. Publication remains closed until group-aware proof is implemented.
- The private undo callback clears current visibility links while preserving
  history links. It requires a staged undo receipt and removed current members,
  inside the caller's outer transaction. It is not an authorized undo operation.
- Exact retries do not repeat effects, including after undo. A metadata-only
  receipt cannot be silently upgraded into a visibility change by replay.

A monotonic organization revision is included in inventory bindings. Undo cannot
restore an older evidence approval merely by restoring the original visible IDs.
History-marked findings are protected from duplicate cleanup, including after
undo. Complete source archive/restore/purge and reappearance behavior remains a
required subsequent gate; these protections do not constitute that full feature.

## Storage and performance

Migration `0053` adds tenant-scoped current, alias and history links on findings,
a small organization revision table and corresponding constraints/indexes.
The new partial link indexes lead with organization ID, keeping per-tenant alias
counts from scanning other organizations' aliases.
Materialized links keep ordinary list/count/seek queries free of per-row group
joins. All 28 affected existing partial indexes adopt the same alias-null active
predicate. Physical sources are retained instead of copied or deleted.

## Activation and rollback

The migration has not been applied to the normal application database. The
running application has not been restarted for this increment.

Activation requires a coordinated maintenance/rollout plan: stop admissions and
workers, back up, apply `0053`, deploy matching application code, then verify and
resume traffic. The migration rebuilds 28 indexes concurrently, one at a time,
with old/new swaps; concurrent builds still consume I/O, CPU and disk. Old
application predicates do not imply the new index predicate, so a mixed-version
rollout can degrade old queries. Measure migration time and free disk on a
representative database before scheduling activation. This migration is not a
lightweight hot restart.

Concurrent DDL commits in stages. Upgrade is designed to resume after an
interruption; rerun the migration after investigating the failure. Downgrade is
allowed only before any retained current/alias/history links or positive visibility
revision exist. The revision also protects history after physical source purge. After
publication, retain schema/history and roll forward; never remove historical
links merely to force a downgrade.

## Validation

Focused local PostgreSQL runs passed: 38 migration/transaction/Dashboard checks,
49 visibility/scoring/report checks and 148 broader archive/navigation/evidence
checks. Scopes overlap; these are not additive unique-test counts. The final private undo guard and concurrent-index recovery check passed in a
10-test run; two further migration guards passed, including rejection after
undo. These scopes overlap. The final 13-test schema/visibility run passed, including migration parity and
downgrade protection. The final full backend run passed all 1,865 tests in 1,724.10 seconds
(28 minutes 44 seconds), with PostgreSQL required and warnings treated as errors.
This includes the final migration guards, rollback checks and 100,000-finding
plan test. An earlier full run was stopped because it had loaded pre-review test
and index definitions; it is not counted as a completed validation run.
The final ten visibility checks also passed separately after strengthening
Dashboard rollback and pending-ORM undo coverage.

A 100,000-synthetic-finding check passed using the covering
`ix_findings_active_org_domain_severity` index and no group joins. Visible count
was 100,002 before and 100,001 after the simulated pair; physical count remained
100,002. Warm grouped count measured 21.5 ms / 21.3 ms respectively. Heap fetches
were 0 / 9; recently changed pages may need heap visibility checks even with an
index-only plan. This is a local query-plan check, not cold-cache or SaaS/load
capacity evidence. The synthetic bulk seed is not importer throughput evidence.
An initial test incorrectly required zero heap fetches after publication; that
assertion was corrected to bound the small changed-page checks and the test
passed. No production query/planner setting was changed to obtain this result.
Normal application data is not used as a test fixture; isolated PostgreSQL
clusters retain ordinary durability settings.

The preceding transaction checkpoint `1d5c86b` passed all four hosted Linux jobs
in [run 43292318027](https://github.com/shalisarakkal/AuditMind/actions/runs/43292318027).
That result does not cover these uncommitted changes. Hosted CI must be rerun
after an approved commit/push. There is no new publication action to verify yet. The isolated production build
and all 103 existing Chromium workflow checks passed, including tenant/role
restrictions, archive dialogs, Dashboard tabs, refresh and accessibility checks.
The high-severity Bandit gate and whitespace checks passed.
