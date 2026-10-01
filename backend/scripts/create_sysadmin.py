r"""Create a Sysadmin: the account that creates organizations and their first
admins, and looks after accounts in an emergency (PLAN.md, Phase 2e). Run on
the server, never through the website. It's an account of its own, in no
organization; it gets a temporary password, shown once here, to be changed
at the first sign-in.

    cd backend
    .venv\Scripts\python scripts\create_sysadmin.py --email root@example.com --name "Platform admin"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import TypeAdapter, ValidationError  # noqa: E402

import app.db.base  # noqa: E402,F401  (every model, so the mappers can be set up)
from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.schemas.types import LowerEmail  # noqa: E402
from app.services.people import PeopleError  # noqa: E402
from app.services.platform import create_sysadmin  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Sysadmin account.")
    parser.add_argument("--email", required=True, help="The Sysadmin's sign-in (an account of its own)")
    parser.add_argument("--name", help="How it's shown, e.g. Platform admin")
    args = parser.parse_args(argv)
    try:
        email = TypeAdapter(LowerEmail).validate_python(args.email)
    except ValidationError:
        print(f"Not an email address: {args.email}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        try:
            password = create_sysadmin(db, email, args.name)
        except PeopleError as refused:
            print(refused.message, file=sys.stderr)
            return 1
        db.commit()
    print(f"Sysadmin {email} created.")
    print(f"Temporary password (shown only this once): {password}")
    print(f"Sign in within {settings.TEMP_PASSWORD_DAYS} days and choose your own password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
