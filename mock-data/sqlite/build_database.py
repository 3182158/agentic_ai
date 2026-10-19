"""Build the deterministic Acme helpdesk SQLite database from SQL fixtures."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = DATA_DIR / "acme_helpdesk.sqlite3"


def build_database(database_path: Path = DEFAULT_DATABASE) -> None:
    """Recreate the database from schema.sql and seed.sql."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript((DATA_DIR / "schema.sql").read_text(encoding="utf-8"))
        connection.executescript((DATA_DIR / "seed.sql").read_text(encoding="utf-8"))
        connection.commit()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(f"Foreign key violations: {violations}")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"database output path (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()
    build_database(args.output)
    print(f"Built SQLite database: {args.output.resolve()}")


if __name__ == "__main__":
    main()
