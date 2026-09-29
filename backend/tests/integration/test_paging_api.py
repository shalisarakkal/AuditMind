"""Paged lists: GET /orgs/{id}/assets and /findings return {items, total}
(findings also domain_counts), with limit/offset and a search."""

import uuid

import pytest

from app.models.enums import Domain, Severity
from app.models.finding import Finding
from tests.conftest import requires_db
from tests.helpers import first_org_id, register, upload

pytestmark = requires_db


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _get(client, admin, path, **params):
    headers, org_id = admin
    resp = client.get(f"/api/v1/orgs/{org_id}/{path}", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _upload(client, admin, kind, content):
    headers, org_id = admin
    assert upload(client, f"/api/v1/orgs/{org_id}/{kind}/import", headers, "a.csv", content).status_code == 201


def test_assets_come_a_page_at_a_time_oldest_first(client, admin):
    _upload(client, admin, "assets", b"type,hostname\n" + b"".join(b"server,host-%02d\n" % i for i in range(5)))

    first = _get(client, admin, "assets", limit=2)
    rest = _get(client, admin, "assets", limit=2, offset=4)

    assert first["total"] == rest["total"] == 5
    assert [a["hostname"] for a in first["items"]] == ["host-00", "host-01"]
    assert [a["hostname"] for a in rest["items"]] == ["host-04"]


def test_asset_search_matches_hostname_or_ip_and_takes_wildcards_literally(client, admin):
    _upload(client, admin, "assets", b"type,hostname,ip\nserver,Web-01,10.0.0.1\nserver,db_01,10.0.9.9\nserver,dbx01,\n")

    assert [a["hostname"] for a in _get(client, admin, "assets", q="WEB")["items"]] == ["Web-01"]
    assert [a["hostname"] for a in _get(client, admin, "assets", q="10.0.9")["items"]] == ["db_01"]
    # "_" is a character to find, not a LIKE wildcard.
    assert _get(client, admin, "assets", q="db_")["total"] == 1
    assert _get(client, admin, "assets", q="   ")["total"] == 3


def test_page_size_is_bounded(client, admin):
    headers, org_id = admin
    assert client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers, params={"limit": 501}).status_code == 422
    assert client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers, params={"offset": -1}).status_code == 422


FINDINGS = (
    b"hostname,domain,severity,category,description\n"
    b"web-01,network_config,low,C1,Telnet banner\n"
    b"web-01,identity_access,critical,C2,Default admin password\n"
    b"db-01,network_config,high,C3,Open RDP\n"
    b"db-01,network_config,critical,C4,Exposed database port\n"
)


def test_findings_are_most_severe_first_with_their_host_and_domain_counts(client, admin):
    _upload(client, admin, "findings", FINDINGS)

    body = _get(client, admin, "findings")

    assert body["total"] == 4
    assert body["domain_counts"] == {"network_config": 3, "identity_access": 1}
    # Newest first within a severity.
    assert [(f["severity"], f["category"]) for f in body["items"]] == [
        ("critical", "C4"),
        ("critical", "C2"),
        ("high", "C3"),
        ("low", "C1"),
    ]
    assert [f["asset_hostname"] for f in body["items"]] == ["db-01", "web-01", "db-01", "web-01"]


def test_the_domain_filter_narrows_the_list_but_not_the_counts(client, admin):
    _upload(client, admin, "findings", FINDINGS)

    body = _get(client, admin, "findings", domain="network_config", limit=2)

    assert body["total"] == 3
    assert [f["category"] for f in body["items"]] == ["C4", "C3"]
    assert body["domain_counts"] == {"network_config": 3, "identity_access": 1}


def test_finding_search_matches_description_or_category_and_counts_follow_it(client, admin):
    _upload(client, admin, "findings", FINDINGS)

    body = _get(client, admin, "findings", q="rdp")
    assert [f["category"] for f in body["items"]] == ["C3"]
    assert body["domain_counts"] == {"network_config": 1}

    assert _get(client, admin, "findings", q="c2")["total"] == 1


def test_findings_never_point_at_or_show_another_orgs_asset(client, admin, db_session):
    other = register(client, "someone@other.io", org_name="Other Org")
    other_org = first_org_id(client, other)
    assert upload(
        client, f"/api/v1/orgs/{other_org}/assets/import", other, "a.csv", b"type,hostname,ip\nserver,their-host,10.9.9.9\n"
    ).status_code == 201
    their_asset = client.get(f"/api/v1/orgs/{other_org}/assets", headers=other).json()["items"][0]["id"]
    their_scan = client.get(f"/api/v1/orgs/{other_org}/scans", headers=other).json()[0]["id"]
    headers, org_id = admin

    for field, ref in (("asset_id", their_asset), ("scan_id", their_scan)):
        resp = client.post(
            f"/api/v1/orgs/{org_id}/findings",
            headers=headers,
            json={field: ref, "domain": "network_config", "severity": "low"},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == f"{field} {ref} is not in this organization"

    # A finding recorded that way before the check existed shows no host.
    db_session.add(
        Finding(org_id=uuid.UUID(org_id), asset_id=uuid.UUID(their_asset), domain=Domain.network_config, severity=Severity.low)
    )
    db_session.commit()
    [item] = _get(client, admin, "findings")["items"]
    assert (item["asset_hostname"], item["asset_ip"]) == (None, None)


def test_finding_search_also_matches_the_assets_hostname_or_ip(client, admin):
    _upload(client, admin, "findings", FINDINGS)
    _upload(client, admin, "assets", b"type,hostname,ip\nserver,db-01,10.20.30.40\n")

    by_host = _get(client, admin, "findings", q="DB-0")  # partial, any case
    assert sorted(f["category"] for f in by_host["items"]) == ["C3", "C4"]
    assert by_host["domain_counts"] == {"network_config": 2}

    assert sorted(f["category"] for f in _get(client, admin, "findings", q="10.20.30")["items"]) == ["C3", "C4"]


ASSETS = (
    b"type,hostname,ip,environment,criticality,tags\n"
    b"server,web-02,10.0.0.2,prod,high,web;dmz\n"
    b"Laptop,alice-pc,10.0.1.5,dev,,office\n"
    b"router,core-sw,10.0.0.1,prod,critical,\n"
    b"server,web-01,,staging,low,web\n"
)


def _hostnames(body):
    return [a["hostname"] for a in body["items"]]


def test_assets_sort_by_any_column_either_way_with_blanks_last(client, admin):
    _upload(client, admin, "assets", ASSETS)

    assert _hostnames(_get(client, admin, "assets", sort="hostname")) == ["alice-pc", "core-sw", "web-01", "web-02"]
    assert _hostnames(_get(client, admin, "assets", sort="hostname", order="desc")) == ["web-02", "web-01", "core-sw", "alice-pc"]
    # No IP: last whichever way.
    assert _hostnames(_get(client, admin, "assets", sort="ip")) == ["core-sw", "web-02", "alice-pc", "web-01"]
    assert _hostnames(_get(client, admin, "assets", sort="ip", order="desc")) == ["alice-pc", "web-02", "core-sw", "web-01"]
    # The default: the order they were added.
    assert _hostnames(_get(client, admin, "assets")) == ["web-02", "alice-pc", "core-sw", "web-01"]

    headers, org_id = admin
    assert client.get(f"/api/v1/orgs/{org_id}/assets", headers=headers, params={"sort": "tags"}).status_code == 422


def test_asset_column_filters_combine(client, admin):
    _upload(client, admin, "assets", ASSETS)

    assert _hostnames(_get(client, admin, "assets", environment=["prod", "staging"], sort="hostname")) == ["core-sw", "web-01", "web-02"]
    assert _hostnames(_get(client, admin, "assets", type="server", hostname="WEB-0", sort="hostname")) == ["web-01", "web-02"]
    assert _hostnames(_get(client, admin, "assets", ip="10.0.0")) == ["web-02", "core-sw"]
    assert _hostnames(_get(client, admin, "assets", tags="dm")) == ["web-02"]
    # "" picks the assets with no value.
    assert _hostnames(_get(client, admin, "assets", criticality="")) == ["alice-pc"]
    assert _hostnames(_get(client, admin, "assets", criticality=["", "low"])) == ["alice-pc", "web-01"]
    assert _get(client, admin, "assets", type="database")["total"] == 0


def test_asset_facets_list_each_pick_lists_values(client, admin):
    _upload(client, admin, "assets", ASSETS)

    facets = _get(client, admin, "assets/facets")

    assert facets == {
        "type": ["network_device", "server", "workstation"],
        "subtype": ["", "Laptop", "router"],
        "environment": ["dev", "prod", "staging"],
        "criticality": ["", "critical", "high", "low"],
    }


def test_findings_sort_and_filter_by_column(client, admin):
    _upload(client, admin, "findings", FINDINGS)
    categories = lambda body: [f["category"] for f in body["items"]]  # noqa: E731

    assert categories(_get(client, admin, "findings", sort="asset")) == ["C4", "C3", "C2", "C1"]  # db-01, then web-01
    assert categories(_get(client, admin, "findings", sort="severity", order="desc")) == ["C1", "C3", "C4", "C2"]
    assert categories(_get(client, admin, "findings", sort="finding")) == ["C2", "C4", "C3", "C1"]  # by description

    body = _get(client, admin, "findings", severity=["critical", "high"], asset="db")
    assert categories(body) == ["C4", "C3"]
    assert body["domain_counts"] == {"network_config": 2}

    body = _get(client, admin, "findings", domain=["network_config", "identity_access"], finding="port")
    assert categories(body) == ["C4"]

    assert _get(client, admin, "findings", source="manual")["total"] == 4  # the CSV's default source
    assert _get(client, admin, "findings", source="")["total"] == 0
    assert _get(client, admin, "findings/facets") == {"source": ["manual"]}


def test_asset_search_covers_every_shown_column(client, admin):
    _upload(client, admin, "assets", ASSETS)
    found = lambda q: sorted(_hostnames(_get(client, admin, "assets", q=q)))  # noqa: E731

    assert found("staging") == ["web-01"]  # environment
    assert found("CRIT") == ["core-sw"]  # criticality
    assert found("office") == ["alice-pc"]  # tag
    assert found("laptop") == ["alice-pc"]  # subtype
    assert found("network dev") == ["core-sw"]  # type, by the label shown ("Network device")
    assert found("10.0.1") == ["alice-pc"]  # IP


def test_finding_search_covers_every_shown_column(client, admin):
    _upload(client, admin, "findings", FINDINGS)
    found = lambda q: sorted(f["category"] for f in _get(client, admin, "findings", q=q)["items"])  # noqa: E731

    assert found("critical") == ["C2", "C4"]  # severity
    assert found("identity &") == ["C2"]  # domain, by the label shown ("Identity & Access")
    assert found("config") == ["C1", "C3", "C4"]  # "Network & Config"
    assert found("manual") == ["C1", "C2", "C3", "C4"]  # source
    assert found("zzz") == []


def test_cloud_resources_known_only_by_cloud_id_can_be_found_and_named(client, admin):
    _upload(
        client,
        admin,
        "assets",
        b"type,cloud_id\n"
        b"Lambda,arn:aws:lambda:us-east-1:111:function:billing\n"
        b"bucket,arn:aws:s3:::acme-backups\n",
    )
    _upload(
        client,
        admin,
        "findings",
        b"cloud_id,domain,severity,category,description\n"
        b"arn:aws:s3:::acme-backups,backup_recovery,high,S3-PUBLIC,Bucket is public\n",
    )
    cloud_ids = lambda body: [a["cloud_id"] for a in body["items"]]  # noqa: E731

    assert cloud_ids(_get(client, admin, "assets", sort="cloud_id")) == [
        "arn:aws:lambda:us-east-1:111:function:billing",
        "arn:aws:s3:::acme-backups",
    ]
    assert cloud_ids(_get(client, admin, "assets", cloud_id=":S3:")) == ["arn:aws:s3:::acme-backups"]
    assert cloud_ids(_get(client, admin, "assets", q="function:billing")) == ["arn:aws:lambda:us-east-1:111:function:billing"]

    [finding] = _get(client, admin, "findings", q="acme-backups")["items"]
    assert (finding["asset_hostname"], finding["asset_ip"], finding["asset_cloud_id"]) == (None, None, "arn:aws:s3:::acme-backups")
    assert _get(client, admin, "findings", asset="s3:::acme")["total"] == 1


def test_paging_through_findings_misses_nothing_across_severities(client, admin):
    # 11 findings over 4 severities, some filtered out by domain.
    rows = [
        f"host-{i},{'identity_access' if i % 4 == 0 else 'network_config'},{sev},C{i:02d},Finding {i}"
        for i, sev in enumerate(["low", "critical", "high", "low", "medium", "critical", "low", "high", "critical", "medium", "low"])
    ]
    _upload(client, admin, "findings", ("hostname,domain,severity,category,description\n" + "\n".join(rows) + "\n").encode())
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    for sort, order, domain in (("severity", "asc", None), ("severity", "desc", None), ("severity", "asc", "network_config"),
                                ("created", "desc", None), ("created", "asc", None)):
        params = {"sort": sort, "order": order, **({"domain": domain} if domain else {})}
        everything = _get(client, admin, "findings", limit=100, **params)["items"]
        paged = [f for offset in range(0, 12, 3) for f in _get(client, admin, "findings", limit=3, offset=offset, **params)["items"]]
        assert [f["id"] for f in paged] == [f["id"] for f in everything], (sort, order, domain)
        assert len(everything) == (8 if domain else 11)
        if sort == "severity":
            ranks = [rank[f["severity"]] for f in everything]
            assert ranks == sorted(ranks, reverse=order == "desc")
            # Newest first within a severity.
            for a, b in zip(everything, everything[1:]):
                if a["severity"] == b["severity"]:
                    assert a["created_at"] >= b["created_at"]
        else:
            times = [f["created_at"] for f in everything]
            assert times == sorted(times, reverse=order == "desc")
