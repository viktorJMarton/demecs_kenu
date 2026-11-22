#!/usr/bin/env python3
"""Copy a Kajak-Kenu SQLite database and optionally migrate the source."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))



def _backup_database(source: sqlite3.Connection, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        backup_connection = sqlite3.connect(destination)
        try:
            source.backup(backup_connection)
            if backup_connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise sqlite3.DatabaseError("backup failed SQLite integrity check")
        finally:
            backup_connection.close()
    except BaseException:
        destination.unlink()
        raise


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
    parser.add_argument(
        "--copy-only",
        action="store_true",
        help="Create a private verified SQLite copy without migrating the source",
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

    mode = "ro" if args.copy_only else "rw"
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode={mode}", uri=True)
    try:
        _backup_database(connection, backup_path)
        if not args.copy_only:
            from flaskr.affiliate_migration import migrate_affiliate_schema
            try:
                migrate_affiliate_schema(connection)
            except Exception:
                print(f"Migration failed; verified backup: {backup_path}", file=sys.stderr)
                raise
    finally:
        connection.close()

    if not args.copy_only:
        print(f"Affiliate migration completed: {database_path}")
    print(f"Verified SQLite copy: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
