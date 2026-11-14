#!/usr/bin/env python3
"""Back up and migrate a Kajak-Kenu SQLite database to affiliate schema v1."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from flaskr.affiliate_migration import migrate_affiliate_schema


def _backup_database(source: sqlite3.Connection, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup_connection = sqlite3.connect(destination)
    try:
        source.backup(backup_connection)
    finally:
        backup_connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=os.environ.get("DATABASE_URL", "kajak_kenu.db"),
        help="SQLite database path (default: DATABASE_URL or kajak_kenu.db)",
    )
    parser.add_argument(
        "--backup-path",
        help="Explicit backup path; defaults beside the database with a timestamp",
    )
    args = parser.parse_args()

    database_path = Path(args.database).expanduser().resolve()
    if not database_path.is_file():
        parser.error(f"database does not exist: {database_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        Path(args.backup_path).expanduser().resolve()
        if args.backup_path
        else database_path.with_name(f"{database_path.name}.bak_affiliate_{timestamp}")
    )
    if backup_path.exists():
        parser.error(f"backup path already exists: {backup_path}")

    connection = sqlite3.connect(database_path)
    try:
        _backup_database(connection, backup_path)
        migrate_affiliate_schema(connection)
    except Exception:
        print(f"Migration failed; untouched backup: {backup_path}")
        raise
    finally:
        connection.close()

    print(f"Affiliate migration completed: {database_path}")
    print(f"Pre-migration backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
