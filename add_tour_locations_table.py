"""Utility script to backfill the new tour_locations helper table.

Run with: python add_tour_locations_table.py
"""

from __future__ import annotations

import os
import sqlite3
from typing import Iterable, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "kajak_kenu.db")

SEED_LOCATIONS: Iterable[Tuple[str, float, float]] = (
    ("Duna, Szentendre (Lázár cár rakpart)", 47.6756, 19.0688),
    ("Római-part, Budapest", 47.5677, 19.0635),
    ("Tisza-tó, Tiszafüred - Morotva", 47.6204, 20.6483),
    ("Kisköre - Hallépcső", 47.4919, 20.5002),
    ("Velencei-tó, Sukoró", 47.2337, 18.6207),
    ("Mosoni-Duna, Győr", 47.6896, 17.6506),
)


def ensure_tours_column(cursor: sqlite3.Cursor) -> None:
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(tours)").fetchall()]
    if "tour_location_id" not in columns:
        cursor.execute("ALTER TABLE tours ADD COLUMN tour_location_id INTEGER")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tours_tour_location_id ON tours(tour_location_id)"
        )


def ensure_locations_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tour_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            latitude REAL,
            longitude REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_tour_locations_name ON tour_locations(name)"
    )


def seed_locations(cursor: sqlite3.Cursor) -> None:
    cursor.executemany(
        "INSERT OR IGNORE INTO tour_locations (name, latitude, longitude) VALUES (?, ?, ?)",
        SEED_LOCATIONS,
    )


def backfill_tours(cursor: sqlite3.Cursor) -> int:
    updated = 0
    locations = cursor.execute(
        "SELECT id, name FROM tour_locations"
    ).fetchall()

    for loc_id, loc_name in locations:
        result = cursor.execute(
            """
            UPDATE tours
               SET tour_location_id = ?
             WHERE location = ?
               AND (tour_location_id IS NULL OR tour_location_id != ?)
            """,
            (loc_id, loc_name, loc_id),
        )
        updated += result.rowcount
    return updated


def main() -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    ensure_locations_table(cursor)
    ensure_tours_column(cursor)
    seed_locations(cursor)
    updated_rows = backfill_tours(cursor)

    conn.commit()
    conn.close()

    print("tour_locations table ensured and seeded.")
    print(f"Mapped {updated_rows} existing tours to helper locations.")


if __name__ == "__main__":
    main()
