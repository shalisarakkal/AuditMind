"""Where an import keeps the rows it has read and checked until they're
published (Phase 2f part 1).

The background worker's imports stage them in the database, a chunk at a
time, each chunk committed with how far reading got and the report so far
(ReadState): an import cut off carries on from its last chunk. Then all of
it is published in one step under the org's lock (ingestion_service), so
no one ever sees half an upload. Imports run in the request (small files)
keep them in memory: same reading and checking, no database round trips.

Chunks and state are pickled (the measured fastest way there and back:
500K rows staged in ~14 s, read back in ~9 s; JSON took ~42 s and ~28 s).
Only this app writes them, to its own unlogged tables, and reads them back
moments later; something that can't be read back (the app changed in
between) is dropped and the file read again.
"""

import logging
import pickle
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Notes listed per kind in a report (errors, warnings, skipped rows).
MAX_LISTED = 1000
# Changing what's pickled changes this, so older staging is read again.
STAGING_VERSION = 1


@dataclass
class Capped(Generic[T]):
    """The first MAX_LISTED items added (rows come in file order, so the
    lowest rows), and how many there were in all."""

    items: list[T] = field(default_factory=list)
    total: int = 0

    def add(self, item: T) -> None:
        self.total += 1
        if len(self.items) < MAX_LISTED:
            self.items.append(item)


@dataclass
class Identifiers:
    """The hostnames, IPs and cloud IDs an upload names, to load just the
    matching assets (AssetIndex.load); past `limit` of them, the whole org
    is loaded instead, so they stop being kept."""

    limit: int
    hostnames: set[str] = field(default_factory=set)
    ips: set[str] = field(default_factory=set)
    cloud_ids: set[str] = field(default_factory=set)
    whole_org: bool = False

    def add_row(self, item: "StagedRow") -> None:
        """A staged row's asset and findings."""
        for part in (item.asset, *item.findings):
            if part is not None:
                self.add(part)

    def add(self, row: Any) -> None:
        if self.whole_org:
            return
        if row.hostname:
            self.hostnames.add(row.hostname.lower())
        if row.ip:
            self.ips.add(row.ip)
        if row.cloud_id:
            self.cloud_ids.add(row.cloud_id)
        if len(self.hostnames) + len(self.ips) + len(self.cloud_ids) > self.limit:
            self.whole_org = True
            self.hostnames, self.ips, self.cloud_ids = set(), set(), set()


@dataclass
class StagedRow:
    """One file row's checked output: its asset (if it names one) and its
    findings. Published together, in file order."""

    row: int
    asset: Any | None
    findings: list[Any]


@dataclass
class ReadState:
    """How far reading has got, and everything the report needs from it."""

    fingerprint: str
    identifiers: Identifiers
    last_row: int = 0  # the last file row read (resume skips through it)
    rows_seen: int = 0
    rows_with_output: int = 0  # rows that gave an asset or findings
    items_staged: int = 0
    next_seq: int = 1
    read_done: bool = False
    columns: list[str] = field(default_factory=list)  # the first record's
    failed: int = 0
    errors: Capped = field(default_factory=Capped)
    warnings: Capped = field(default_factory=Capped)
    skipped: int = 0
    skipped_rows: Capped = field(default_factory=Capped)
    # What the row checker keeps across rows (see RowChecker.snapshot).
    checker: dict = field(default_factory=dict)


class MemoryStaging:
    """For an import run in the request: nothing to resume."""

    def __init__(self, state: ReadState):
        self.state = state
        self._items: list[StagedRow] = []

    def load(self) -> ReadState:
        return self.state

    def add(self, items: list[StagedRow], state: ReadState) -> None:
        self._items.extend(items)
        state.items_staged += len(items)

    def items(self) -> Iterator[StagedRow]:
        yield from self._items


class DbStaging:
    """For an import the background worker runs. Each add() commits."""

    def __init__(self, db: Session, scan_id: uuid.UUID, fresh: ReadState):
        self.db = db
        self.scan_id = scan_id
        self.fresh = fresh

    def load(self) -> ReadState:
        """Where an earlier run got to, if it read with the same settings;
        else start afresh (anything staged is dropped)."""
        row = self.db.execute(
            text("SELECT fingerprint, data FROM import_staging_state WHERE scan_id = :scan"), {"scan": self.scan_id}
        ).first()
        if row is not None and row.fingerprint == self.fresh.fingerprint:
            try:
                state = pickle.loads(row.data)
                logger.info("Import %s carries on after row %d", self.scan_id, state.last_row)
                return state
            except Exception:
                logger.warning("Import %s: its staging can't be read back; reading the file again", self.scan_id)
        if row is not None:
            discard(self.db, self.scan_id)
        return self.fresh

    def add(self, items: list[StagedRow], state: ReadState) -> None:
        """Stage `items` and save `state` with them, in one commit."""
        if items:
            self.db.execute(
                text("INSERT INTO import_staging_chunks (scan_id, seq, data) VALUES (:scan, :seq, :data)"),
                {"scan": self.scan_id, "seq": state.next_seq, "data": pickle.dumps(items, pickle.HIGHEST_PROTOCOL)},
            )
            state.next_seq += 1
            state.items_staged += len(items)
        self.db.execute(
            text(
                "INSERT INTO import_staging_state (scan_id, fingerprint, data, updated_at) "
                "VALUES (:scan, :fingerprint, :data, :now) ON CONFLICT (scan_id) "
                "DO UPDATE SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at"
            ),
            {
                "scan": self.scan_id,
                "fingerprint": state.fingerprint,
                "data": pickle.dumps(state, pickle.HIGHEST_PROTOCOL),
                "now": datetime.now(timezone.utc),
            },
        )
        self.db.commit()

    def items(self) -> Iterator[StagedRow]:
        """Everything staged, in file order, a chunk at a time (inside the
        caller's transaction)."""
        seq = 0
        while True:
            chunk = self.db.execute(
                text(
                    "SELECT seq, data FROM import_staging_chunks WHERE scan_id = :scan AND seq > :seq "
                    "ORDER BY seq LIMIT 1"
                ),
                {"scan": self.scan_id, "seq": seq},
            ).first()
            if chunk is None:
                return
            seq = chunk.seq
            yield from pickle.loads(chunk.data)


def discard(db: Session, scan_id: uuid.UUID) -> None:
    """Drop an import's staging (when it ends, however it ends). Commits."""
    for table in ("import_staging_chunks", "import_staging_state"):
        db.execute(text(f"DELETE FROM {table} WHERE scan_id = :scan"), {"scan": scan_id})
    db.commit()


def purge_orphans(db: Session) -> int:
    """Staging of imports no longer waiting or running (left by a crash
    between their end and the clean-up). Daily, by the background worker."""
    deleted = 0
    for table in ("import_staging_chunks", "import_staging_state"):
        deleted += db.execute(
            text(
                f"DELETE FROM {table} t WHERE NOT EXISTS (SELECT 1 FROM scans s WHERE s.id = t.scan_id "
                "AND s.status IN ('pending', 'running'))"
            )
        ).rowcount
    db.commit()
    return deleted
