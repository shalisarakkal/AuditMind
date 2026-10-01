"""Reading uploads a record at a time (Phase 2f part 1)."""

import codecs
import tracemalloc

import pytest

from app.services.import_readers import FileReader, ImportFileError
from app.services.nessus_parser import parse_nessus


def read(content: bytes, fmt: str = "csv", list_key: str = "assets", skip_through: int = 0):
    return list(FileReader(content, fmt, list_key).records(skip_through))


# --- CSV ----------------------------------------------------------------------


def test_csv_rows_are_numbered_by_their_line():
    rows = read(b'Type, HostName\nserver,a\n"laptop","multi\nline"\nserver,c,extra\n')
    assert rows == [
        (2, {"type": "server", "hostname": "a"}),
        (4, {"type": "laptop", "hostname": "multi\nline"}),  # a record's last line
        (5, {"type": "server", "hostname": "c"}),  # cells beyond the header dropped
    ]


def test_csv_with_a_bom_and_windows_line_ends():
    assert read(codecs.BOM_UTF8 + b"type,hostname\r\nserver,a\r\n") == [(2, {"type": "server", "hostname": "a"})]


@pytest.mark.parametrize(
    "content, message",
    [
        (b"", "The CSV file has no header row"),
        (b"type,hostname\nserver,caf\xe9\n", "The file is not valid UTF-8 text"),
    ],
)
def test_csv_problems(content, message):
    with pytest.raises(ImportFileError, match=message):
        read(content)


def test_skipping_rows_already_read():
    content = b"type,hostname\n" + b"".join(f"server,h{n}\n".encode() for n in range(5))
    assert [row for row, _ in read(content, skip_through=4)] == [5, 6]


# --- JSON ---------------------------------------------------------------------


def test_json_list_or_wrapped_list():
    assert read(b'[{"Type": "server", "n": 1.5}, {"type": "laptop"}]', "json") == [
        (1, {"type": "server", "n": 1.5}),
        (2, {"type": "laptop"}),
    ]
    assert read(codecs.BOM_UTF8 + b' {"assets": [{"type": "server"}], "meta": 1}', "json") == [(1, {"type": "server"})]
    assert read(b'{"assets": []}', "json") == []  # empty: the import says "no rows"


@pytest.mark.parametrize(
    "content, message",
    [
        (b"", "Invalid JSON"),
        (b'"text"', "Expected a JSON list of records"),
        (b'{"other": [1]}', "Expected a JSON list of records"),
        (b'{"assets": {"a": 1}}', "Expected a JSON list of records"),
        (b'[{"type": "server"}, {"type": ', "Invalid JSON"),
    ],
)
def test_json_problems(content, message):
    with pytest.raises(ImportFileError, match=message):
        read(content, "json")


# --- .nessus -----------------------------------------------------------------

NESSUS = b"""<?xml version="1.0"?>
<NessusClientData_v2><Report name="r">
<ReportHost name="10.0.0.5"><HostProperties><tag name="host-fqdn">web.acme.io</tag></HostProperties>
<ReportItem pluginID="1" pluginName="A" pluginFamily="F" severity="2" port="22" protocol="tcp"/>
<ReportItem pluginID="2" pluginName="B" pluginFamily="F" severity="0" port="0" protocol="tcp"/>
</ReportHost>
<ReportHost name="db"><ReportItem pluginID="3" pluginName="C" pluginFamily="F" severity="4" port="1" protocol="tcp"/>
<HostProperties><tag name="host-ip">10.0.0.9</tag></HostProperties></ReportHost>
</Report></NessusClientData_v2>"""


def test_nessus_items_in_order_with_their_hosts():
    items = [(row, item.hostname, item.ip, item.plugin_id) for row, item in read(NESSUS, "nessus")]
    # A host's identity holds even if its properties come after its items.
    assert items == [(1, "web.acme.io", "10.0.0.5", "1"), (2, "web.acme.io", "10.0.0.5", "2"), (3, "db", "10.0.0.9", "3")]
    assert [i.row for i in parse_nessus(NESSUS)] == [1, 2, 3]


def test_nessus_rejects_entities_and_other_xml():
    with pytest.raises(ImportFileError, match="DTDs and entity declarations"):
        read(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "boom">]><NessusClientData_v2>&e;</NessusClientData_v2>', "nessus")
    with pytest.raises(ImportFileError, match="expected a NessusClientData_v2 export"):
        read(b"<other/>", "nessus")


# --- Flat memory ----------------------------------------------------------------


def _peak_reading(content: bytes, fmt: str) -> tuple[int, int]:
    reader = FileReader(content, fmt, "assets")
    tracemalloc.start()
    count = sum(1 for _ in reader.records())
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return count, peak


@pytest.mark.parametrize("fmt", ["csv", "json", "nessus"])
def test_reading_keeps_memory_flat_whatever_the_size(fmt):
    def make(n: int) -> bytes:
        if fmt == "csv":
            return b"type,hostname,notes\n" + b"".join(f"server,host-{i},{'x' * 100}\n".encode() for i in range(n))
        if fmt == "json":
            return b"[" + b",".join(f'{{"type":"server","hostname":"host-{i}","notes":"{"x" * 100}"}}'.encode() for i in range(n)) + b"]"
        hosts = "".join(
            f'<ReportHost name="h{i}"><ReportItem pluginID="1" pluginName="{"x" * 100}" pluginFamily="F" '
            f'severity="1" port="1" protocol="tcp"/></ReportHost>'
            for i in range(n)
        )
        return f'<NessusClientData_v2><Report name="r">{hosts}</Report></NessusClientData_v2>'.encode()

    small_count, small_peak = _peak_reading(make(1_000), fmt)
    large_count, large_peak = _peak_reading(make(20_000), fmt)
    assert (small_count, large_count) == (1_000, 20_000)
    # 20x the rows, about the same memory: the reader holds a record (and
    # its read buffer) at a time, never the rows read so far. (The content
    # itself isn't measured: in a real import it's the file on disk.)
    assert large_peak < small_peak * 2, (small_peak, large_peak)

