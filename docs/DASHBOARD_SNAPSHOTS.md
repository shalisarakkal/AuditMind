# Stored Dashboard snapshots

The Dashboard can serve a saved, per-organization database snapshot rather than
recounting inventory on each visit. Migration **0034** adds one cache/job row per
organization. This is a refreshable view, not an immutable audit report or a new
scoring algorithm. Existing index migration 0033 also accelerates rebuilding.

## Controls and normal use

Platform administrators open **Platform → Dashboard settings**. **Use stored
Dashboard snapshots** defaults off for compatibility until enabled. The refresh
Platform interval defaults to **1 hour**, configurable from **1 to 1,440 minutes**.
Organization administrators can set a different interval under **Settings →
Dashboard refresh**, or check **Inherit Platform refresh interval** and click
**Save refresh interval** to resume inheritance. The checkbox is a draft choice
until saved; there is no separate Reset action.
Without an override, later Platform changes apply automatically. Organization
changes are authorized, versioned and audited; viewers/auditors cannot edit them.
Settings are authorized, audited and versioned; conflicting edits require an
explicit reload. Disabling stored mode immediately returns reads to the live
path. Existing refresh jobs finish safely, and stored data remains for reuse.
This control is separate from the default-off evidence-qualified scoring mode.

In stored mode, members see **Last updated** in their browser time zone and a
**Refresh dashboard** button. Refresh queues a rebuild rather than blocking the
request on counting. Repeated requests while a job is pending/running share the
same organization row. Old results remain available until atomic replacement;
failures retain the last good payload and show a retryable error. Before the
first successful build, the UI shows a pending/failed state without invented
zero counts, perfect scores or completed assessments.

The scheduler warms missing snapshots for active organizations and refreshes
existing snapshots when due, including their rolling security-summary window.
Scheduled refreshes wait at least the effective interval, plus a stable spread
of up to 10% of that interval, capped at five minutes. Thus the hourly default
normally becomes due after 60–65 minutes, before worker/queue delay. The stable
organization-based offset reduces synchronized bursts across organizations;
it does not change manual refresh or interrupt active jobs. Platform/organization
interval changes recalculate future due times without queuing catch-up work.

It checks about every 30 seconds between coordinator jobs. Long jobs, an offline
worker or queue pressure can delay refresh beyond the configured interval.
Up to 100 missing and 100 due organizations are considered per check. Admission
is fair through the existing bounded pool; one queued job per organization still
runs at a time. Archived/purging organizations are excluded, and pending/running
Dashboard refreshes count when checking whether an organization can be archived.

An open Dashboard checks cheap mode/revision/snapshot metadata every ten seconds
and on focus. New generated timestamps cause it to fetch the replacement. While
its own refresh is pending/running, it polls the saved endpoint every two seconds
after the prior request, without keeping the login alive. Errors stop polling
and allow explicit retry. No heavy inventory query runs on these cached reads.

## What is saved and what remains current

The payload stores exact findings grouped by domain/severity, active asset count,
five top findings, five recent uploads and the security summary's explicit
seven-day window. Counts/cards and revision are captured in one repeatable-read
transaction and published together. The security summary's Activity links retain
that captured window, and the UI labels its saved window end.

Counts and source cards describe the generated snapshot, so recent imports,
archivals, purges, workflow changes or upload-status changes may not appear until
regeneration. **Last updated** is part of that contract. The cache is not a
source of truth for an action: finding links, mutations, authorization and item
existence still use current organization-scoped APIs. Organization deletion
cascades to the stored row. No source record or saved report is changed by a
refresh. Failed builds never publish partial counts.

Scoring is inexpensive arithmetic over saved counts, using existing deductions
and weights. Membership and current scoring mode/version are checked on reads.
Evidence eligibility is **not stored as an authoritative decision**: current
policy, review expiry/revocation, evaluation identity and inventory/source
revision are checked without rescanning inventory. A cached inventory revision
must match current inventory before evidence-qualified numbers can be displayed.
After a material change, users may need both a Dashboard refresh and a separate
evidence re-evaluation/review. Refreshing this cache never approves evidence or
calls AI. Missing/expired/conflicting evidence stays unscored.

## Persistence and failure handling

`dashboard_snapshots` contains the last payload plus the coalesced job's pending,
running, completed or failed state. First-row creation is serialized across
sessions. Scheduler admission, per-thread heartbeat tracking, job locks and stale
recovery include Dashboard work. Interrupted work can retry up to the existing
worker recovery limit; successful publication replaces the entire payload.
Failures keep the old payload, expose a generic error and back off periodic retry
using the configured interval. Manual retry can queue immediately.

The snapshot's read transaction is separate from its short publish transaction;
concurrent inventory writes do not have to wait for the read. If a write commits
during collection, the saved view remains internally consistent but is marked
stale on subsequent reads. It cannot qualify a current evidence score.

Settings use the existing platform-settings table. Snapshot rollback disables
stored mode and increments its settings version before dropping the cache table.
The startup migration guard prevents an updated worker starting without it.
Apply migrations before restarting the worker. Disabling the setting is the
normal rollback; dropping the table is deployment rollback, not a UI action.

Migration **0035** adds nullable organization interval overrides and their edit
version. Existing organizations inherit by default. Previously saved Platform
intervals remain explicit configured values; the migration does not overwrite
them. The authorized local demo update separately changes its configured
five-minute interval to one hour and audits that change. Downgrading 0035 drops
organization overrides; stored snapshot mode and the Platform value remain.

## Verification

Backend tests cover first-view queuing, coalescing from two independent sessions,
no heavy query on saved reads, exact replacement counts, periodic warming and
refresh, archived-organization boundaries, failed publication retaining payload,
stale recovery, concurrent inventory writes, membership, platform permissions,
settings conflicts, and live expiry/revocation/inventory/policy checks.

```text
python -m pytest -W error --require-postgres tests/integration/test_dashboard_snapshots.py tests/integration/test_dashboard_api.py tests/integration/test_background_evidence.py tests/integration/test_migrations.py -q
```

Frontend tests verify first-build presentation, refresh retention/polling,
failure recovery and platform controls. The isolated Chrome workflow also
enables snapshots through the UI, tests two-tab conflicts, changes inventory,
requests a refresh, checks the second user, verifies organization overrides/reset
and stale edits, waits for a real one-minute scheduled
refresh, verifies the open page updates, and checks mobile/Axe before disabling
the setting. No real organization is used by that fixture.

```text
node scripts/browser-finding-workflow.cjs
```

For manual Chrome verification, enable stored mode with a one-minute interval in
the isolated demo. Open Dashboard, note Last updated, and reload to see the same
snapshot. Add a manual finding, return and click Refresh dashboard; verify the
new count and timestamp. Keep two users open and confirm both observe scheduled
replacement. Restore the Platform interval to one hour afterward. Expired/revoked
evidence must remain unscored even before snapshot regeneration.

The latest exact test counts, runtime activation and any blocked launch are
recorded in [Phase 4 validation](PHASE4_VALIDATION.md); this design document alone
is not proof that the current runtime or hosted CI has passed.
