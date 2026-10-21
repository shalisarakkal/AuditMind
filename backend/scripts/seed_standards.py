"""CLI script to seed or refresh CIS/NIST/ISO compliance standards into PostgreSQL pgvector."""

import argparse
import sys
from pathlib import Path

# Add backend dir to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.session import SessionLocal
from app.services.standards_service import seed_standards_knowledge_base


def main():
    parser = argparse.ArgumentParser(description="Seed compliance standards knowledge base into pgvector.")
    parser.add_argument("--force", action="store_true", help="Force refresh existing standards")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        count = seed_standards_knowledge_base(db, force_refresh=args.force)
        print(f"Successfully processed {count} standard controls.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
