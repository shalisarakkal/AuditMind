"""The in-memory matching an import uses (import_matching.py): the same rules
as the database queries it replaced."""

import uuid

from app.services.import_matching import AssetIndex, FindingIndex, IndexedAsset, finding_key


def _asset(type_="server", hostname=None, ip=None, cloud_id=None, type_known=True) -> IndexedAsset:
    return IndexedAsset(uuid.uuid4(), type_, type_known, hostname, ip, cloud_id)


def test_a_cloud_id_match_wins_and_otherwise_only_assets_without_one_match_by_name():
    in_cloud = _asset(hostname="web-01", cloud_id="i-1")
    on_prem = _asset(hostname="web-01")
    index = AssetIndex([in_cloud, on_prem])

    assert index.find("anything", None, "i-1") == [in_cloud]
    assert index.find("web-01", None, "i-2") == [on_prem]
    assert index.find(None, None, "i-2") == []


def test_hostnames_match_case_insensitively_oldest_first():
    older, newer = _asset(hostname="Web-01"), _asset(hostname="web-01")
    index = AssetIndex([older, newer])

    assert index.find("WEB-01", None) == [older, newer]


def test_a_known_category_matches_its_own_or_guessed_types_same_category_first():
    guess = _asset("server", hostname="h", type_known=False)
    router = _asset("network_device", hostname="h")
    workstation = _asset("workstation", hostname="h")
    index = AssetIndex([guess, router, workstation])

    assert index.find("h", None, category="workstation") == [workstation, guess]
    assert index.find("h", None, category="database") == [guess]
    # An unknown category matches any, oldest first.
    assert index.find("h", None) == [guess, router, workstation]


def test_ip_fallback_only_reaches_assets_without_a_hostname():
    named = _asset(hostname="alpha", ip="10.0.0.1")
    nameless = _asset(ip="10.0.0.1")
    index = AssetIndex([named, nameless])

    assert index.find("beta", "10.0.0.1") == [nameless]
    # With no hostname, any asset with the IP matches.
    assert index.find(None, "10.0.0.1") == [named, nameless]


def test_added_and_updated_assets_are_found_by_their_new_identity():
    index = AssetIndex()
    asset = _asset(ip="10.0.0.1")
    index.add(asset)

    index.update(asset, hostname="db-01", type="database")

    assert index.find("DB-01", None, category="database") == [asset]
    assert index.find("other", "10.0.0.1") == []  # it has a hostname now
    assert index.other_categories("db-01", "server") == ["database"]
    assert index.other_categories("db-01", "database") == []


def test_an_updated_asset_keeps_its_age():
    older, newer = _asset(hostname="a"), _asset(hostname="b")
    index = AssetIndex([older, newer])

    index.update(newer, hostname="a")
    index.update(older, ip="10.0.0.9")

    assert index.find("a", None) == [older, newer]


def test_finding_keys_use_the_description_only_without_a_category():
    asset_id = uuid.uuid4()
    index = FindingIndex([finding_key(asset_id, "scan", "CVE-1", "old text"), finding_key(asset_id, "scan", None, None)])

    assert finding_key(asset_id, "scan", "CVE-1", "new text") in index
    assert finding_key(asset_id, "other", "CVE-1", None) not in index
    assert finding_key(asset_id, "scan", None, None) in index
    assert finding_key(asset_id, "scan", None, "text") not in index
