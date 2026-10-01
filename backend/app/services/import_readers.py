"""Reading an uploaded file a record at a time, so memory stays flat
whatever its size (Phase 2f part 1): CSV streamed, JSON with ijson, .nessus
with iterparse.

Each reader yields (row, record) in file order, row being what the report
calls it: a CSV's line number (the record's last physical line, as
csv.reader counts), a JSON record's or .nessus ReportItem's 1-based
position. After a cut-off an import carries on by skipping the records
already read (skip_through): parsing them again is cheap next to checking
and writing them.

A problem with the file as a whole (not UTF-8, invalid JSON or XML, no
header) raises ImportFileError, possibly part-way through: nothing has been
published by then (see ingestion_service).
"""

import codecs
import csv
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

import ijson

from app.services import nessus_parser

# Bytes read at a time from the file.
_READ_SIZE = 1024 * 1024


class ImportFileError(Exception):
    """The file as a whole can't be read."""


def _key(key: Any) -> Any:
    return key.strip().lower() if isinstance(key, str) else key


class FileReader:
    """Records of one file. `size` and `position` (bytes) estimate how far
    reading has got, for progress."""

    def __init__(self, source: bytes | Path, fmt: str, list_key: str):
        self.fmt = fmt
        self.list_key = list_key
        self._source = source
        self.size = len(source) if isinstance(source, bytes) else source.stat().st_size
        self._file: BinaryIO | None = None

    @property
    def position(self) -> int:
        try:
            return self._file.tell() if self._file is not None else 0
        except (OSError, ValueError):
            return 0

    def records(self, skip_through: int = 0) -> Iterator[tuple[int, Any]]:
        """(row, record) for every record after row `skip_through`."""
        with self._open() as file:
            self._file = file
            reading = {"csv": _csv_records, "json": _json_records, "nessus": _nessus_records}[self.fmt]
            for row, record in reading(file, self.list_key):
                if row > skip_through:
                    yield row, record

    def _open(self) -> BinaryIO:
        if isinstance(self._source, bytes):
            return io.BytesIO(self._source)
        return self._source.open("rb")


def _csv_records(file: BinaryIO, _list_key: str) -> Iterator[tuple[int, dict]]:
    # Decoded as one text stream, split on "\n" as before (newline="\n"
    # matches io.StringIO), so line numbers are the same as they were.
    text = io.TextIOWrapper(file, encoding="utf-8-sig", errors="strict", newline="\n")
    reader = csv.DictReader(text)
    try:
        if not reader.fieldnames:
            raise ImportFileError("The CSV file has no header row")
        for record in reader:
            # Cells beyond the header land under the None key; ignore them.
            yield reader.line_num, {_key(k): v for k, v in record.items() if k is not None}
    except UnicodeDecodeError:
        raise ImportFileError("The file is not valid UTF-8 text")
    except csv.Error as exc:
        raise ImportFileError(f"Invalid CSV at line {reader.line_num}: {exc}")
    finally:
        text.detach()  # the file is closed by its owner


def _first_char(file: BinaryIO) -> str:
    """The first character that isn't white space (or a BOM), the file left
    where it was."""
    start = file.tell()
    head = file.read(4096)
    file.seek(start)
    text = codecs.decode(head.lstrip(codecs.BOM_UTF8), "utf-8", errors="ignore").lstrip()
    return text[:1]


class _SkipBom(io.RawIOBase):
    """The file without a leading UTF-8 BOM (ijson would refuse it)."""

    def __init__(self, file: BinaryIO):
        self.file = file
        if file.read(3) != codecs.BOM_UTF8:
            file.seek(0)

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        data = self.file.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def _json_records(file: BinaryIO, list_key: str) -> Iterator[tuple[int, Any]]:
    """A top-level list, or {list_key: [...]}, read an item at a time."""
    first = _first_char(file)
    if first not in ("[", "{"):
        if not first:
            raise ImportFileError("Invalid JSON: the file is empty")
        raise ImportFileError(f'Expected a JSON list of records, or {{"{list_key}": [...]}}')
    prefix = "item" if first == "[" else f"{list_key}.item"
    count = 0
    try:
        for count, record in enumerate(ijson.items(_SkipBom(file), prefix, use_float=True), start=1):
            yield count, ({_key(k): v for k, v in record.items()} if isinstance(record, dict) else record)
    except UnicodeDecodeError:
        raise ImportFileError("The file is not valid UTF-8 text")
    except ijson.JSONError as exc:
        raise ImportFileError(f"Invalid JSON: {exc}")
    if count == 0 and first == "{" and not _has_list(file, list_key):
        raise ImportFileError(f'Expected a JSON list of records, or {{"{list_key}": [...]}}')


def _has_list(file: BinaryIO, list_key: str) -> bool:
    """Whether a JSON object has {list_key: [...]} at its top level."""
    file.seek(0)
    try:
        for prefix, event, _ in ijson.parse(_SkipBom(file)):
            if prefix == list_key and event == "start_array":
                return True
    except ijson.JSONError:
        return False
    return False


def _nessus_records(file: BinaryIO, _list_key: str) -> Iterator[tuple[int, Any]]:
    try:
        for item in nessus_parser.iter_nessus(file):
            yield item.row, item
    except ValueError as exc:
        raise ImportFileError(str(exc))
