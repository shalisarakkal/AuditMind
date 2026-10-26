"""High-confidence tracked-file guard; reports locations, never matching values.

Not a replacement for credential rotation, history scanning or a managed secret
scanner. Test credentials in disposable CI databases are not provider secrets.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])sk-(?:ant-|or-v1-)?[A-Za-z0-9_-]{24,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    failures = []
    for name in filter(None, paths):
        path = ROOT / name
        if (path.name.startswith(".env") and not path.name.endswith(".example")) or path.name == "SIGN_IN.txt":
            failures.append(f"{name}: forbidden credential file")
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        for line_number, line in enumerate(content.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                failures.append(f"{name}:{line_number}: potential secret")
    for failure in failures:
        print(failure)
    if not failures:
        print("Tracked-file secret guard passed (matching values never printed).")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
