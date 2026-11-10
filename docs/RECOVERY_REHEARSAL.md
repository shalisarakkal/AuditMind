# Synthetic backup/restore and worker-recovery rehearsal

PB-0.3, 5 November 2026. This is local operational evidence, not production,
customer-pilot, hosting, live-AI or recovery-SLA approval.

## Scope and ownership

The project owner/user confirmed release, engineering, operations and security
ownership on 5 November. PB-0.1 checklist/ownership reconciliation is complete;
the remaining release decisions are tracked in
[release readiness](RELEASE_READINESS.md#current-release-gate-checklist---8-november-2026).
PB-0.2 pilot preparation, broader scoring and SaaS rollout remain deferred.
Current search behavior is unchanged.

The harness initializes a new loopback-only PostgreSQL cluster on a free local
port. It creates separate `recovery_source_test` and `recovery_restored_test`
databases there, with temporary synthetic credentials. It does not connect to
the configured ordinary/demo/test databases, alter their roles, or stop their
servers. Its own cluster is stopped and removed; synthetic backups and evidence
remain under ignored `temp/testing/recovery/recovery_<uuid>/`.

## Fixture and backup contract

- Actual Alembic migration from an empty database through **0039**.
- Two synthetic organizations and one administrator membership.
- One baseline asset, an archived finding, versioned rationale/verification
  history and its archive batch/job.
- One knowledge-document version and original synthetic Markdown companion file,
  an organization-logo blob and a deterministic non-AI report/HTML export.
- One queued 5,000-row CSV with a stable scan UUID, SHA-256 and real authenticated
  import-staging state/chunks.

Writers are quiesced after interrupting the owned worker. `pg_dump --format=custom`
captures the source database; a ZIP captures companion files under relative
paths. A manifest records archive/file SHA-256 values and row counts/hashes for
every application table. The normal queued-file path remains `<scan UUID>.upload`
under the separately configured restored upload root.

The custom archive is restored with `pg_restore --exit-on-error --no-owner
--no-acl` into the separate empty target database. PostgreSQL documents that
`pg_dump` covers one database; global roles/tablespaces need separate treatment.
This fixture therefore does not establish production role/ACL or cluster-wide
recovery. References: [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html).

## Executed checks

1. Kill an actual owned worker process after its first SQL publication flush:
   2,000 synthetic asset inserts are present inside its uncommitted transaction,
   while another connection sees zero published queued assets. Killing the
   process rolls back that transaction; committed staging and the raw file remain.
2. Capture the quiesced database/files bundle and integrity manifest.
3. Reject a deliberately corrupted archive through the same checksum validator
   used before restore. Detect an omitted restored upload, then repair it.
4. Restore and compare every table's complete row count/SHA-256 and application
   schema definitions. Check all indexes are valid and migration-to-head is a no-op.
5. Verify restored workflow/history, document content, report rendering and
   cross-organization denial through application service paths.
6. Wait for the **real configured 30-second rehearsal stale interval**; no clock
   or heartbeat is edited. Start the actual queue admission/reaper/import job
   paths using a one-shot worker harness.
7. Verify one retry, a saved authenticated checkpoint with all 5,000 rows already
   read, exactly 5,000 distinct published assets, completed import, discarded
   staging and normal removal of its consumed raw file.
8. Restart the one-shot worker again; verify no duplicate work or durable changes.
9. Restore the archived finding through the archive service and retain its history.
10. Verify the source fixture is unchanged and AI usage is zero; stop/remove the
    private cluster. External HTTP transports and inference credentials are disabled.

The fixture's one-shot harness calls the real worker scheduler, stale reaper and
import runner. It does not establish pool-leadership, distributed scheduling or
multi-worker capacity. Existing CLI-pool acceptance is a separate test.

### Schema comparison detail

PostgreSQL restore reparses seven CHECK expressions and one partial-index
predicate from an array-wide unbounded-varchar-to-text cast into per-element text
casts. The harness canonicalizes only that observed equivalent cast form.
Raw source/restore DDL remains in the evidence directory. Unit tests verify that
changed allowed values, operators, index keys, numeric types and length-limited
varchar casts are not hidden by normalization.

## Results and measured limits

The final rehearsal passed all ten operational checks, with five focused unit
checks passing for checksum rejection and narrow schema canonicalization.
Run: `recovery_44cc46a38cc9418a835e6c9a6b65a239`.
The prior complete run `recovery_51abbb7d74384298b7625ea5aa3879e8` also passed;
the final run additionally exercised the extracted checksum validator on a real
corrupted fixture archive. Final observations:

| Stage | Seconds |
| --- | ---: |
| Private cluster setup and migrations | 18.710 |
| Quiesced database + files backup | 0.477 |
| Restore + complete fingerprint/file verification | 0.987 |
| Worker restart to completed import, after stale eligibility | 5.255 |
| Actual interruption to completed restored import | 34.756 |

The database archive was 191,642 bytes and files ZIP 15,380 bytes. These timings
are for a small synthetic fixture. They are not full-inventory recovery targets,
production RTO/RPO commitments, or measurements of infrastructure provisioning.
Zero committed fixture rows/files were missing at the backup point. The 2,000
uncommitted inserts were intentionally rolled back; their source input recovered
successfully through the queue. Writes made after a backup are outside its scope.

The normal application's stale default remains 120 seconds. Only this isolated
rehearsal uses 30 seconds. No inference calls, settings changes, source migrations,
search indexes or ordinary service restarts were performed.

## Reproduction

PostgreSQL 18 server/client binaries and the installed `vector`/`pg_trgm`
extensions must be available. No CREATEDB grant on the existing installation is
needed: the script owns its separate disposable cluster.

From `backend` in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_recovery_rehearsal.py -q -W error
.\.venv\Scripts\python.exe scripts/rehearse_recovery.py --pg-bin 'S:/Program Files/PostgreSQL/18/bin'
```

Use the actual trusted PostgreSQL binary directory on another machine. The
script refuses optimized Python execution because its rehearsal assertions must
remain enabled. Worker subprocesses verify their database/port against their
owned cluster record. Recursive cleanup verifies the resolved cluster directory
is the newly created child under the workspace's rehearsal root.

Keep `bundle/database.dump`, `bundle/files.zip` and `bundle/manifest.json` together.
Do not apply this fixture harness to a live database or treat it as a scheduled
backup service. The backup point here is quiesced; no claim is made that online
database and file backups are transactionally synchronized.

## Failures retained and remaining acceptance

Earlier failed rehearsal runs remain as evidence. Windows inherited output
pipes initially blocked `pg_ctl` completion; the harness now uses owned log files.
Strict raw-schema comparison then exposed the cast representation change above;
row and file comparisons already matched, and the narrow canonicalization is
regression tested. Failed private clusters were stopped/removed.

Before a real deployment, select the target and approve recovery/data-loss goals;
validate a representative inventory, least-privilege restore identities, storage
ACLs, off-host/encrypted backup retention, secrets/configuration recovery, roles,
backup age/monitoring and the complete runtime/startup procedure. The staging
HMAC signing secret must be available through the approved secret-recovery
process; this synthetic harness retains the same ephemeral key across its source
and restored workers. It does not back up production secrets. Base/WAL backups,
point-in-time recovery, database-server crash/restart behavior of unlogged tables,
cross-host loss and disaster recovery are not established by this logical restore.

PB-0.3 can close for the explicitly authorized local synthetic rehearsal; G-03's
intended-deployment recovery acceptance remains open. The full native rehearsal
is a local, opt-in check. Hosted CI checks the helper unit tests and application
suites; it does not execute or certify this full native recovery drill.
