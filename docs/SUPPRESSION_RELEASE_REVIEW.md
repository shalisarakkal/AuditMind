# Imported finding suppression and clear: release review

11 November 2026. PB-1.3 bounded disposition increment, migration 0050.
Implementation commit: `f26bc63`; retained-source correction: `6ed32a4`.
Final suppression/retained-source delivery: `f97a4fbf29a728a45087f03d8dabf6ea21950d4b`;
all four hosted Linux jobs passed in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797). This includes the
`6ed32a4` retained-source correction, which the earlier `cc1ca17` run did not cover.
Current application baseline: `e4c7488c1a0b40a99bc20efe60a6663fac7f62d3`;
all four jobs passed in [run 43144443993](https://github.com/shalisarakkal/AuditMind/actions/runs/43144443993), including full backend, frontend,
dependency/security and complete browser acceptance. These are engineering
results; the broader PB-1.3, pilot, production and SaaS gates remain separate.

## Delivered behavior and limits

- Organization admins/auditors can explicitly suppress an active finding only
  when all its retained observations (1-1000) have current independent native
  Nessus reviews resolving to one supported plugin/service identity. Generic
  CSV/JSON labelled Nessus and other profiles remain ineligible. Active matching
  reviewed identities and conflicting canonical designations block publication.
- A server preview pins target, workflow/proof versions, source/lifecycle,
  observation review versions, registry version and reappearance history. Required
  rationale, explicit confirmation and a request UUID accompany each decision.
  Replayed identical requests return the original receipt; changed reuse conflicts.
- Clearing is organization-admin-only. It can clear a retained, archived or
  purged target, including after identity revocation. It never recreates deleted
  payloads or restores archived parents. An active potential duplicate blocks
  restoration of a retained target until the source/canonical conflict is resolved.
- Suppression is independent of workflow status, source archive ownership and
  approved scoring evidence. Raw severity, notes, assignee and deadlines remain.
  Existing saved reports are immutable. No automatic resolution or score approval.
- Unreviewed uploads do not inherit bindings. A suppressed source is excluded
  from legacy active duplicate matching; a new unreviewed occurrence stays visible.
  An indexed batch lookup records possible reappearances for the same captured
  source asset and normalized native material. This similarity is not authority
  to hide a record or establish a scanner namespace. Different/new asset identities
  cannot inherit suppression by hostname or description. Explicit fresh review is
  required before applying a standing identity to a replacement record.
- The registry, decisions and possible-reappearance receipts survive finding,
  scan, observation and actor retention. Organization deletion cascades them.
  Clearing changes state, not history. Minimal source identity/labels and rationale
  remain; source payloads are not copied into tombstones.

## Atomicity, concurrency and performance

Publication uses job admission, a prompt try of the organization publication
lock, current organization/member/account admission, registry/finding locks and
version/context fences. Busy publication returns a conflict instead of waiting
through a large import. Binding changes and tool retirement share publication
admission. Ordinary workflow editing retains its separate row/version path.

Finding visibility, durable decision, activity, list revision, suppression/evidence
revision and coalesced Dashboard invalidation commit together. Failed publication
rolls back all effects. A Dashboard capture from before a suppression change
cannot publish afterward: stale payloads are withheld and a current refresh is
queued. Read-only history is paged and does not load source context/payloads.

Migration 0050 adds the retained registry/history, possible-reappearance receipts,
per-organization suppression revision and nullable finding visibility/history
links. Source links to the registry are deferred no-action foreign keys, protecting
retained history while permitting organization-wide cascade deletion without
intermediate visibility updates. Active Findings partial indexes are rebuilt
with `archived_at IS NULL AND suppression_id IS NULL`; existing covering counts,
seek navigation and selective searches retain eligible index predicates.
Unchanged index definitions are not rebuilt. No existing source payload backfill.

Counts/facets/top issues, evidence inputs, new report capture and both Dashboard
views use visible active findings. Suppressed counts and decision references are
recorded separately from verified risk exclusions; suppression alone never proves
coverage or a healthy score. An all-suppressed finding scope has no numeric
finding baseline, including when status-aware scoring is disabled. Suppression
basis stays in server provenance and is not additional AI evidence.

Source archive/restore preserves the independent suppression and history links.
The duplicate-deletion restore path cannot delete previously reviewed payloads.
Restoring a cleared reviewed payload over an active duplicate stops with an
explicit conflict rather than silently merging or deleting it. Explicit source
purge remains possible, preserving the minimal ledger. Migration rollback is an
operator action requiring backup/export of retained suppression history; removing
visibility support is not an implicit business-level clearance.

## UI and Chrome acceptance

Findings provides **Suppress** for native Nessus rows and **Suppressed findings**
for organization-wide inspection. Individual actions remain disabled while bulk
selection is active. Manual Archive is unchanged. Inspect history and possible
reappearances; admins can open **Clear suppression**. Rationale and acknowledgment
are required. Unknown outcomes retry the identical request; stale edits retain the
rationale but require explicit preview reload. Busy dialogs reject dismissal.
No Close/Cancel implies that a submitted operation was undone.

The new walkthrough verifies genuine isolated native imports/bindings, held-save
controls, independent-review conflicts, retained workflow/count behavior, admin
clear, viewer reads, 320px layout/Axe and an actual committed response replaced by
503 followed by idempotent retry. Fixtures use disposable schemas with no AI.

## Validation record

- Earlier broader PostgreSQL regression: 161 passed; final focused lifecycle,
  ledger and migration run: 46 passed after reproducing and fixing source-alias
  reapplication tracking. These overlap and are not full acceptance.
- Final full frontend: 576 passed (two test workers). Final component rerun: 9 passed; lint and isolated
  production build pass. Component reruns overlap the full frontend suite.
- Final rebuilt Chrome walkthrough: 103 checks passed, no browser errors or AI
  usage, including current status and a long scanner name at 320px.
- High-severity Bandit: zero High findings; dependency consistency passes. This
  does not claim that all Medium/Low findings or production gates are closed.
- Full required-PostgreSQL regression with warnings as errors: 1,765 passed and
  one existing abort-test setup-readiness timeout during concurrent migration
  and validation (81m19s). It failed at the five-second registration wait, not
  at the cancellation or rollback assertions. Setup wait is now 30 seconds;
  cancellation lock/completion budgets are unchanged. Post-review reruns and
  exact-source hosted CI must pass before delivery.

Private test databases are removed and private servers stopped by the runners.
The normal application is migrated to 0050 and rebuilt/restarted; health, login
and auth-options return HTTP 200. Queue preflight was idle. A 1,522,009,682-byte
schema/data backup was created and its archive listing verified before migration. No provider consent,
scoring setting or worker-capacity setting is changed. Unrelated local files and
the original Copilot worktree remain preserved.

PB-1.3 remains partial after this bounded feature: safe canonical consolidation
and source-payload publication, additional reviewed source mappings and automatic
reconciliation are separate work. Pilot, production and broad scale gates stay open.

## Source-alias review correction

A replacement import may use a new source asset while an independent review maps
it to the same canonical asset. A reproduced regression showed that explicitly
reapplying the standing suppression retained the old source fingerprint. The
publisher now updates the reviewed identity and source fingerprint in the same
transaction; previous decision contexts remain historical. A later matching
upload records a possible reappearance and stays visible for independent review.
The regression passes in the 46-case post-review run. That run covers the latest
backend fix; the longer full-suite run started before this small correction.
Final pushed-source hosted CI is verified in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797).

## Migration operations

Migration 0050 rebuilds changed active-finding partial indexes so broad counts,
sorts and risk aggregation keep their covering paths with suppression excluded.
The unchanged archive-batch index is retained. This is a one-time maintenance
cost on a large table, not a zero-downtime migration. Stop application writers,
check all queues, take a schema/data backup, apply the migration and verify
Alembic drift before starting services. Local activation uses the existing
isolated demo schema and preserves passwords, uploads and organization settings.
A backup archive listing verifies readability; it is not a restore rehearsal.

## Hosted delivery verification

All four Linux jobs passed for `cc1ca17695fdf97b9748aac6c093ed27a4b621bb`
in [run 43125422309](https://github.com/shalisarakkal/AuditMind/actions/runs/43125422309): full backend with required PostgreSQL and warnings as errors,
frontend, dependency/security audit, and complete browser acceptance including
finding workflow, evidence/scoring pilot and worker-pool recovery. This covers
the latest source-alias correction and abort-test readiness adjustment. That run verifies the original publication. It does not cover the additional
retained-source correction below. Its own exact-tip hosted result is verified
for `f97a4fb` in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797). PB-1.3 remains partial.

## Retained-source correction after the initial green run

A further reproduced case reapplied a standing suppression to a reviewed
replacement, then restored the older suppressed upload. Clear preview incorrectly
returned HTTP 200 although clearing would expose two retained payloads sharing
one reviewed identity. It now returns 409 until the additional retained source
is archived or the canonical conflict is resolved. This also protects a purged
current target from silently exposing a different retained payload.

After an authorized clear, source restore checks both legacy duplicates and the
shared suppression-history identity, including reviewed source-asset aliases.
Separate indexed EXISTS probes preserve the legacy asset/source path and sparse
history-link path. A blocked restore keeps the reviewed payload and history.
Three final targeted PostgreSQL cases pass, including unchanged/aliased source
assets and the original cleared-payload restore conflict. Expanded regression
results and the follow-up implementation commit are recorded at check-in below.
The initial green `cc1ca17` run does not certify this later correction.

Follow-up check-in: `6ed32a4` passes 120 expanded suppression, ledger, migration,
abort and archive regressions (624.43s). Three final indexed-query cases pass
(13.70s); they overlap the expanded set. The normal app was restarted without a
frontend rebuild after an idle-queue check. Migration drift is clean and health,
login and auth-options return HTTP 200. All four exact-tip hosted jobs passed
for `f97a4fb` in [run 43129300797](https://github.com/shalisarakkal/AuditMind/actions/runs/43129300797); the earlier `cc1ca17` run remains a
historical baseline rather than proof of later changes.

## Unchanged-draft correction - delivered in e4c7488

Save draft is disabled when persisted draft content and inventory binding match
the saved draft. Review-note fields and unfinished observation inputs are separate.
An identical valid API save preserves version, updated attribution/time, audit
history and evidence revision. Observation ordering and equivalent time-zone
spellings do not count as edits. First saves, actual content/binding edits and
explicit return from a reviewed state to draft still create a version. Approved
records remain protected; permission, source freshness and expected-version
checks are retained before the no-op return.

Targeted PostgreSQL draft/review acceptance: 54 passed. Component acceptance:
15 passed; lint and production build passed. These overlap earlier suites and
are not full-suite totals. All four exact-SHA hosted Linux jobs passed in [run 43144443993](https://github.com/shalisarakkal/AuditMind/actions/runs/43144443993).
No new database migration was required; local activation remains at 0050.
