"""In-memory view of an org's assets and findings for one import.

An import used to look every row up in the database (several queries per
row, so a 500K-row file took over half an hour). Instead, after taking the
org's import lock, it loads once the assets the file can touch (those with
one of the file's hostnames, IPs or cloud IDs: every asset a row could match
shares one of its identifiers) and those assets' finding keys, then matches
rows against these indexes; rows it writes are added as it goes, so later
rows in the same file see earlier ones.

Loading only what the file names keeps a small import quick in an org with
millions of assets. But each of those lookups is a scattered read, and on a
spinning disk thousands of them are slower than one sequential pass over the
whole org (measured: ~10K assets and their findings, ~140 s cold; all 1.5M
assets and 2.15M findings, ~27 s). So above TARGETED_LOAD_MAX identifiers the
whole org is loaded instead: the result is the same either way.

The matching rules are exactly those of the queries they replace:

- By cloud ID first (exact); if that matches, or the row has no hostname or
  IP to fall back on, that's the answer. Otherwise only assets without a
  cloud ID of their own are candidates by name or IP.
- By hostname (case-insensitive). A row whose category is known matches only
  an asset of that category or one whose type is a guess (type_known false),
  a same-category asset first; a row with no known category matches any.
  Oldest first within that.
- By IP: when the row has a hostname that matched nothing, only assets with
  no hostname are candidates, so two differently named hosts sharing an IP
  are never merged. A row with no hostname matches any asset with its IP.

Archived assets and findings are left out: an import never matches them, and
a finding that only an archived one duplicates is recorded afresh.
"""

import uuid
from bisect import insort
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.finding import Finding


@dataclass(eq=False)
class IndexedAsset:
    """An asset's identity, as matching needs it. `seq` orders assets oldest
    first (created_at, then the order this import created them in)."""

    id: uuid.UUID
    type: str
    type_known: bool
    hostname: str | None
    ip: str | None
    cloud_id: str | None
    seq: int = field(default=0, compare=False)


def _seq(asset: IndexedAsset) -> int:
    return asset.seq


# Values per IN (...) query when loading: well under Postgres's parameter limit.
LOAD_CHUNK = 5000
# Up to this many identifiers (or assets, for findings) are looked up one by
# one; more load the whole org in one pass (see the module doc).
TARGETED_LOAD_MAX = 2000


def _chunks(values: list, size: int = LOAD_CHUNK) -> Iterable[list]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


class AssetIndex:
    def __init__(self, assets: Iterable[IndexedAsset] = ()):
        self._by_cloud: dict[str, list[IndexedAsset]] = {}
        self._by_host: dict[str, list[IndexedAsset]] = {}
        self._by_ip: dict[str, list[IndexedAsset]] = {}
        self._next_seq = 0
        # The already-existing assets it was loaded with (not ones added since).
        self.existing_ids: list[uuid.UUID] = []
        for asset in assets:
            self.add(asset)
            self.existing_ids.append(asset.id)

    @classmethod
    def load(
        cls,
        db: Session,
        org_id: uuid.UUID,
        hostnames: Iterable[str] = (),
        ips: Iterable[str] = (),
        cloud_ids: Iterable[str] = (),
    ) -> "AssetIndex":
        """The org's assets with any of these hostnames (case-insensitive),
        IPs or cloud IDs, oldest first; identity columns only (no tags or
        details). Each lookup uses its (org_id, ...) index."""
        columns = select(
            Asset.id, Asset.type, Asset.type_known, Asset.hostname, Asset.ip, Asset.cloud_id, Asset.created_at
        ).where(Asset.org_id == org_id, Asset.archived_at.is_(None))
        lookups = (
            (func.lower(Asset.hostname), {h.lower() for h in hostnames}),
            (Asset.ip, set(ips)),
            (Asset.cloud_id, set(cloud_ids)),
        )
        if sum(len(values) for _, values in lookups) > TARGETED_LOAD_MAX:
            rows = list(db.execute(columns))  # the whole org: one pass
        else:
            found = {}
            for column, values in lookups:
                for chunk in _chunks(sorted(values)):
                    for row in db.execute(columns.where(column.in_(chunk))):
                        found[row.id] = row
            rows = list(found.values())
        rows.sort(key=lambda r: (r.created_at, r.id))
        return cls(IndexedAsset(r.id, r.type, r.type_known, r.hostname, r.ip, r.cloud_id) for r in rows)

    def add(self, asset: IndexedAsset) -> None:
        """Index an asset as the newest so far."""
        asset.seq = self._next_seq
        self._next_seq += 1
        self._insert(asset)

    def update(self, asset: IndexedAsset, **changes) -> None:
        """Change an indexed asset's identity (hostname, ip, cloud_id, type,
        type_known), keeping the lookups in step."""
        self._remove(asset)
        for name, value in changes.items():
            setattr(asset, name, value)
        self._insert(asset)

    def find(
        self, hostname: str | None, ip: str | None, cloud_id: str | None = None, category: str | None = None
    ) -> list[IndexedAsset]:
        """The assets a row could be, best first; the row goes to the first.
        category None: the row's category isn't known (see the module doc)."""
        without_cloud_id = False
        if cloud_id:
            match = self._by_cloud.get(cloud_id)
            if match or (not hostname and not ip):
                return match[:1] if match else []
            without_cloud_id = True

        def candidates(assets: list[IndexedAsset]) -> list[IndexedAsset]:
            found = [
                a
                for a in assets
                if not (without_cloud_id and a.cloud_id)
                and (category is None or a.type == category or not a.type_known)
            ]
            if category:
                # Stable sort: same category first, oldest first within each.
                found.sort(key=lambda a: a.type != category)
            return found

        if hostname:
            matches = candidates(self._by_host.get(hostname.lower(), []))
            if matches or not ip:
                return matches
            return [a for a in candidates(self._by_ip.get(ip, [])) if a.hostname is None]
        return candidates(self._by_ip.get(ip, [])) if ip else []

    def other_categories(self, hostname: str, category: str) -> list[str]:
        """Categories of the assets named `hostname` other than `category`."""
        return sorted({a.type for a in self._by_host.get(hostname.lower(), []) if a.type != category})

    def _insert(self, asset: IndexedAsset) -> None:
        for bucket, key in self._keys(asset):
            insort(bucket.setdefault(key, []), asset, key=_seq)

    def _remove(self, asset: IndexedAsset) -> None:
        for bucket, key in self._keys(asset):
            bucket[key].remove(asset)
            if not bucket[key]:
                del bucket[key]

    def _keys(self, asset: IndexedAsset):
        if asset.cloud_id:
            yield self._by_cloud, asset.cloud_id
        if asset.hostname:
            yield self._by_host, asset.hostname.lower()
        if asset.ip:
            yield self._by_ip, asset.ip


def finding_key(
    asset_id: uuid.UUID, source: str | None, category: str | None, description: str | None
) -> tuple:
    """What makes a finding a duplicate: same asset, source and category; with
    no category, the description stands in for it (None matching None), so
    unrelated uncategorised findings aren't collapsed."""
    return (asset_id, source, category, description if category is None else None)


# Where a finding already recorded came from: the upload (scan id), None for
# one added by hand, or the row of the file being imported.
Origin = uuid.UUID | int | None


class FindingIndex:
    """Duplicate keys (see finding_key) of the findings on some assets, each
    with where its finding came from (so a duplicate can say what it
    duplicates)."""

    def __init__(self, keys: Iterable[tuple] | dict[tuple, Origin] = ()):
        self._origins: dict[tuple, Origin] = keys if isinstance(keys, dict) else dict.fromkeys(keys)

    @classmethod
    def load(cls, db: Session, org_id: uuid.UUID, asset_ids: Iterable[uuid.UUID]) -> "FindingIndex":
        """The findings on these assets: a finding can only duplicate one on
        its own asset, and a new asset has none yet."""
        # Descriptions only matter for uncategorised findings.
        description = case((Finding.category.is_(None), Finding.description))
        query = select(Finding.asset_id, Finding.source, Finding.category, description, Finding.scan_id).where(
            Finding.org_id == org_id, Finding.archived_at.is_(None), Finding.source.is_not(None)
        )
        # One object per upload, not one per row: millions of findings share
        # a few uploads.
        uploads: dict[uuid.UUID, uuid.UUID] = {}

        def entry(row) -> tuple[tuple, Origin]:
            scan_id = row[4]
            return finding_key(*row[:4]), scan_id and uploads.setdefault(scan_id, scan_id)

        asset_ids = list(asset_ids)
        if len(asset_ids) > TARGETED_LOAD_MAX:  # the whole org: one pass
            return cls(dict(entry(row) for row in db.execute(query.where(Finding.asset_id.is_not(None)))))
        origins: dict[tuple, Origin] = {}
        for chunk in _chunks(asset_ids):
            origins.update(entry(row) for row in db.execute(query.where(Finding.asset_id.in_(chunk))))
        return cls(origins)

    def __contains__(self, key: tuple) -> bool:
        return key in self._origins

    def origin(self, key: tuple) -> Origin:
        return self._origins.get(key)

    def add(self, key: tuple, origin: Origin = None) -> None:
        self._origins[key] = origin
