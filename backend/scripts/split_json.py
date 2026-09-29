"""Split a large JSON import file into smaller parts that can be imported one
after another (each part matches against the ones imported before it, so the
result is the same as one big import).

The file is read one record at a time, so splitting uses little memory even
for files far larger than an import can hold. Accepts a top-level list of
records, or an object whose first list holds them ({"records": [...]}).
Each part is written as a plain list of records.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts\\split_json.py <file.json> [--part-mb 40] [--out <folder>]

Parts go to <file>_parts/ next to the file unless --out is given, named
<file>_part01.json, <file>_part02.json, ...
"""

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

READ_CHARS = 1 << 20  # read 1M characters at a time


def iter_records(path: Path) -> Iterator[object]:
    """The records of the file's first list, one at a time."""
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8-sig") as f:
        buffer = ""
        start = -1
        while start < 0:
            more = f.read(READ_CHARS)
            if not more:
                raise ValueError("no JSON list found in the file")
            buffer += more
            start = buffer.find("[")
        pos = start + 1
        while True:
            # Skip whitespace and commas between records, reading on as needed.
            while True:
                while pos < len(buffer) and buffer[pos] in " \t\r\n,":
                    pos += 1
                if pos < len(buffer):
                    break
                more = f.read(READ_CHARS)
                if not more:
                    raise ValueError("the file ends before its list is closed")
                buffer, pos = more, 0
            if buffer[pos] == "]":
                return
            try:
                record, end = decoder.raw_decode(buffer, pos)
            except json.JSONDecodeError:
                # The record continues past what's been read: read more.
                more = f.read(READ_CHARS)
                if not more:
                    raise
                buffer, pos = buffer[pos:] + more, 0
                continue
            yield record
            pos = end
            if pos > READ_CHARS:  # drop what's been consumed
                buffer, pos = buffer[pos:], 0


def split(path: Path, out_dir: Path, part_bytes: int) -> list[tuple[Path, int, int]]:
    """Write the parts; returns (part, records, bytes) for each."""
    out_dir.mkdir(parents=True, exist_ok=True)
    parts: list[tuple[Path, int, int]] = []
    current = None
    count = size = 0

    def close() -> None:
        if current is not None:
            current.write("\n]\n")
            current.close()
            parts.append((Path(current.name), count, size))

    for record in iter_records(path):
        line = json.dumps(record, ensure_ascii=False)
        if current is None or size + len(line) > part_bytes:
            close()
            current = (out_dir / f"{path.stem}_part{len(parts) + 1:02d}.json").open("w", encoding="utf-8")
            current.write("[\n")
            count = size = 0
        elif count:
            current.write(",\n")
        current.write(line)
        count += 1
        size += len(line) + 2
    close()
    return parts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--part-mb", type=float, default=40, help="approximate size of each part (default 40 MB)")
    parser.add_argument("--out", type=Path, help="folder for the parts (default: <file>_parts next to it)")
    args = parser.parse_args()

    source: Path = args.file
    if not source.is_file():
        sys.exit(f"{source} not found")
    out_dir = args.out or source.with_name(f"{source.stem}_parts")
    parts = split(source, out_dir, int(args.part_mb * 1024 * 1024))
    total = sum(count for _, count, _ in parts)
    print(f"{source.name}: {total:,} records -> {len(parts)} parts in {out_dir}")
    for part, count, size in parts:
        print(f"  {part.name}: {count:,} records, {size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
