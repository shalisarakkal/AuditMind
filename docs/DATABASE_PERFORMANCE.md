# Database performance: what to do as the data grows

Review synchronization (2026-10-22): Historical/design record: original dates, results and proposals are preserved. This is not fresh test evidence or current release sign-off.
See [current code review and release gates](RELEASE_READINESS.md).

29 October measured follow-up: [single-organization Dashboard count indexes](SINGLE_ORG_PERFORMANCE.md)
adds migration 0033, preserves exact counts and records query plans, local timing,
storage/maintenance costs and verification scope. Historical hardware/tuning
recommendations below are not fresh measurements or automatic configuration changes.

How fast AuditMind's bulk operations run (imports, archive/restore/purge,
list pages, migrations) depends mostly on **how many rows the biggest tables
hold** and **where Postgres keeps them** (disk type, memory). This page says
what to change at each size, with the numbers measured on the development
machine, and how to make the changes on it.

"Rows" below means the rows of the big tables together: `findings`, `assets`
and `asset_scans` (the upload-asset links), archived rows included (they stay
in the tables until purged).

## Why it slows down

Most operations touch rows scattered across the tables and their indexes: an
import adds each finding to several indexes at random places (the ids are
random), matching looks up hostnames and IPs, archiving updates rows and
index entries. Each of those is fast if the page is in memory and costs a
disk **seek** if not:

| Storage | Random reads per second | Rows/s when every row needs one seek |
|---|---|---|
| 5,400 rpm hard disk (the dev machine's S:) | ~100 | ~100 |
| SATA SSD | ~50,000+ | limited by the CPU instead |
| NVMe SSD | ~200,000+ | limited by the CPU instead |

So the two levers are: **keep the working set in memory** (Postgres's
`shared_buffers`, plus Windows' file cache) and **make the misses cheap**
(an SSD). Everything else is a smaller gain.

## By size

### Up to ~200,000 rows

- Default Postgres settings are fine, on any disk.
- Nothing to do.

### ~200,000 to ~2 million rows

- **Raise `shared_buffers`** so the indexes stay in memory: about 25% of the
  RAM Postgres can have, 1–4 GB. Raise `maintenance_work_mem` (index builds,
  vacuum) to 512 MB and `work_mem` to 16 MB.
- **An SSD is strongly recommended.** On a hard disk, the first import or
  archive after a restart (cold cache) is several times slower than the next.
- After a bulk operation (a big import, archive or purge, a migration), run
  `ANALYZE` on the big tables, or let autovacuum catch up, so the planner has
  current row counts.

### ~2 million to ~20 million rows (the dev database today: ~5 million)

- **SSD required.** On a hard disk, operations that touch hundreds of
  thousands of rows take many minutes to hours (see the measurements below).
- `shared_buffers` 2–4 GB, `effective_cache_size` about half the machine's
  RAM, and larger WAL settings so bulk writes don't force constant
  checkpoints: `max_wal_size = 4GB`, `checkpoint_timeout = 15min`,
  `wal_compression = on`.
- On an SSD, `random_page_cost = 1.1` (the default 4 assumes a hard disk and
  makes the planner avoid indexes it should use).
- Vacuum the big tables more often after bulk updates: for `findings` and
  `assets`, `autovacuum_vacuum_scale_factor = 0.05` (per table).
- Application changes that matter at this size (see the list at the end):
  archive in physical order and in smaller chunks, estimated counts and
  cached pick-list values on the list pages, trigram indexes for search.

### Over ~20 million rows, or many large organizations

- Partition `findings` and `assets` (by organization, or active vs.
  archived) so each operation reads only its part.
- Move archived rows to separate archive tables instead of marking them in
  place, so the active tables stay small.
- Run background jobs in a separate worker process with a queue (e.g. Celery
  or RQ), not inside the web server.
- A dedicated database server or managed Postgres, and a read replica for the
  dashboard and reports.

## Where the database runs

- **Development:** Postgres for Windows is fine once its data is on an SSD
  (step B below): the disk matters far more than the operating system here.
  Postgres in Docker (Linux, through WSL2) on the SSD is an alternative that
  matches CI, which runs the `pgvector/pgvector` image; the app is the same
  either way.
- **Production:** a managed Linux Postgres: Azure Database for PostgreSQL
  (Flexible Server), AWS RDS/Aurora or Google Cloud SQL, with pgvector
  enabled (all three support it) and SSD storage, sized by the sections
  above. Backups, patching, failover and monitoring come with it, which
  matters for customers' vulnerability data; Postgres is developed and tuned
  on Linux, and its memory handling on Windows is weaker. Chosen with the
  hosting platform (PLAN.md, Phase 4).

## Measured on the development machine

Machine: 16 GB RAM; Postgres 18.6 on a 5,400 rpm hard disk (S:),
`shared_buffers` 128 MB (the installer default). Database ~2.2 GB, data
folder 5 GB: ~1.5 million assets, ~2.2 million findings, ~1.3 million
upload-asset links.

| Operation | Measured | Notes |
|---|---|---|
| Import 500,000 rows (Phase 2d part 1) | 34 min → ~2 min | After in-memory matching replaced per-row queries; warm cache |
| Match a 10,000-row file against the org | ~140 s cold (per-row lookups) vs ~27 s (one pass over the whole org) | Why imports load the whole org above 2,000 identifiers |
| Findings list, first page | 27–76 s → 0.5 s | After the index walk (part 1) |
| Migration 0009 (archiving) | 99 s | A first version that checked each of 1.3M link rows as it inserted them ran over 15 min |
| Archive a 500,000-row upload | 17–18 min each (two at once) | ~200 findings/s at first; every archived row updates the table and several indexes |
| Import after the cache was flushed | ~100 findings/s (2,000 every ~20 s) | Almost all time waiting for index pages from disk |
| Assets page (count and pick lists) under load | 70–115 s per request | Each reads all 1.5 million assets; 0.2–0.5 s when the machine is idle and the cache warm |

The last three are the hard-disk limit showing: roughly one seek per row.

**After moving the data to the C: SSD (2026-09-29)**, same machine, same
128 MB `shared_buffers`, ~2.6 million assets and ~3.1 million findings:

| Operation | On the SSD | On the hard disk |
|---|---|---|
| Import 500,000 rows with 1,229,150 findings | 11.7 min (~1,750 findings/s) | a 429,266-finding file: 66 min (~100/s) |
| Import 108,000 cloud assets | ~1.4 min | — |
| Archive that 1.23M-finding upload (500,000 assets) | 3-4 min | 17-18 min for ~500K findings |
| Restore it | ~3 min | — |
| Purge it | ~2 min | — |
| Assets page queries, cold (count, first page, pick list) | 0.07-0.36 s | 0.2-0.5 s idle, 70-115 s under load |
| Findings page queries, cold | 0.02-0.18 s | 0.1-0.6 s |

Two things mattered besides the disk:

- **Statistics after bulk changes.** A restore right after a million rows
  changed state ran one chunk's duplicate check for minutes: Postgres still
  thought 28,000 findings were active (there were a million) and chose a plan
  for a small table. After `ANALYZE` (5 s), 0.6 s. Archive jobs now run
  `ANALYZE findings, assets` before a restore's findings and after any job
  that changes more than a chunk.
- **Web requests during a job.** Imports and archive jobs run inside the web
  server's process, so while one runs every request takes 2-3 s: planned as
  Phase 2d part 3 (a separate worker).

## Doing it on the development machine (Windows)

Both changes restart Postgres. **A restart stops a running import for good**
(its upload stays "running" and must be imported again); a running archive,
restore or purge is marked stopped and continues with Retry. So make the
changes when nothing is importing.

Use an **administrator** PowerShell window.

### A. Bigger memory settings (about 5 minutes)

1. Open `S:\Program Files\PostgreSQL\18\data\postgresql.conf` in a text
   editor run as administrator. Set (remove the leading `#` where there is
   one):

   ```
   shared_buffers = 2GB
   effective_cache_size = 6GB
   maintenance_work_mem = 512MB
   work_mem = 16MB
   max_wal_size = 4GB
   checkpoint_timeout = 15min
   wal_compression = on
   ```

   2 GB is sized for a 16 GB machine that also runs a browser and the dev
   servers. Measure before and after (below); if memory gets tight, use 1 GB.

2. Restart Postgres:

   ```powershell
   Restart-Service postgresql-x64-18
   ```

3. Check it took effect (from `backend\`):

   ```powershell
   .\.venv\Scripts\python -c "from sqlalchemy import create_engine, text; from app.core.config import settings; print(create_engine(settings.DATABASE_URL).connect().execute(text('show shared_buffers')).scalar())"
   ```

   It should print `2GB`. If Postgres doesn't start, the Windows Event Log
   (Application) says why; put the old values back to recover.

### B. Move the database to the SSD (about 20 minutes)

The data folder (5 GB) is copied, not moved: the original stays on S: as a
backup until everything is checked.

1. Stop Postgres and copy the folder with its permissions:

   ```powershell
   Stop-Service postgresql-x64-18
   robocopy "S:\Program Files\PostgreSQL\18\data" "C:\PostgreSQL\18\data" /E /COPYALL /DCOPY:DAT /R:1 /W:1
   ```

   robocopy exit codes 0–7 mean success.

2. Point the service at the new folder (only the `-D` path changes):

   ```powershell
   sc.exe config postgresql-x64-18 binPath= "\"S:\Program Files\PostgreSQL\18\bin\pg_ctl.exe\" runservice -N \"postgresql-x64-18\" -D \"C:\PostgreSQL\18\data\" -w"
   ```

3. Tell the planner the disk is an SSD, and log slow queries: in
   `C:\PostgreSQL\18\data\postgresql.conf` set

   ```
   random_page_cost = 1.1
   log_min_duration_statement = 1000
   log_lock_waits = on
   ```

   The last two record every statement slower than a second, and every wait
   for a lock longer than a second, in the `log` folder (one file per day):
   the first place to look when something is slow.

   (The dev machine's script, `temp\move_postgres_to_ssd.ps1`, does steps
   1–4 with checks, and switches back to S: if Postgres won't start.)

4. Start it and check:

   ```powershell
   Start-Service postgresql-x64-18
   ```

   Log in to the app and open the dashboard. As a superuser (e.g. pgAdmin),
   `SHOW data_directory;` should say `C:/PostgreSQL/18/data`.

5. Once it has worked for a few days, delete the old
   `S:\Program Files\PostgreSQL\18\data` to free the space. Until then, going
   back is step 2 with the old path.

### Measure before and after

Time the same things each time, with nothing else running:

- Import one of the 500,000-row test files.
- Archive it, then restore it (Imports and Archived pages), timing each
  from the click until the result appears.
- Open the Assets page and the Findings page after a restart (cold) and
  again (warm).

## Application-side improvements

Planned or worth doing as the data grows. Each is measured on a copy of the
dev data before it's adopted.

| Improvement | Helps | Status |
|---|---|---|
| Imports and archive jobs in a separate worker process | Pages stay fast while a job runs (measured: 2-3 s per request during an import on the SSD) | Phase 2d part 3 (planned) |
| Refresh statistics (`ANALYZE`) during and after large archive jobs | Restores' duplicate check, and every page right after a big job | Done (Phase 2d part 2) |
| Archive/restore/purge rows in physical (disk) order | Only a hard disk: on the SSD, measured no gain (11-13K rows/s either way) | Dropped |
| Smaller archive chunks | On the SSD a 20,000-row chunk holds the org lock ~1.5-2 s, so others wait seconds already | Not needed now; revisit on slower storage |
| Estimated counts ("about 1.5 million") and cached pick-list values on the list pages | Assets and Findings page loads | Proposed |
| Trigram indexes (`pg_trgm`) for "contains" search | Search boxes and column filters | Later (PLAN.md) |
| `fillfactor = 90` on `findings`/`assets`, and fewer indexes that mention `archived_at` | Archiving can update rows in place without touching indexes | To measure |
| Separate archive tables, partitioning | Very large databases | Over ~20 million rows |
| Imports read a record at a time and staged in chunks (unlogged tables), resumable; published in one pass | Large uploads: 500K-row endpoint export (500K assets, 1.24M findings): peak memory 1,681 MB -> 708 MB, time 173 s -> 209 s (+21%, the price of resuming) | Done (Phase 2f part 1) |
| Staging format: pickled chunks of 2,000 rows (measured: stage 14 s, read back 9 s for 500K rows; JSONB per row: 42 s and 29 s) | Staging cost | Done (Phase 2f part 1) |
| A row cap or warning for huge uploads | Publishing keeps the org's matching assets in memory and holds the org lock: millions of rows need GBs and minutes | To decide |
