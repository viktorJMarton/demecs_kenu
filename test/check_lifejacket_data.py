#!/usr/bin/env python3
"""Utility script to inspect booking lifejacket data."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

DB_PATH = Path(__file__).with_name("kajak_kenu.db")


def load_bookings() -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT id, order_ref, customer_name, participants_count, lifejacket_sizes
            FROM bookings
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()


def parse_lifejackets(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
        if isinstance(data, list):
            return [str(item) for item in data]
        return []
    except (TypeError, json.JSONDecodeError):
        return []


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    bookings = load_bookings()
    if not bookings:
        print("No bookings found.")
        return

    print("Bookings with lifejacket data:\n" + "-" * 60)
    for row in bookings:
        lifejackets = parse_lifejackets(row["lifejacket_sizes"])
        counts = Counter(lifejackets)
        mismatch = len(lifejackets) != row["participants_count"]
        badge = "⚠️" if mismatch else "✅"
        print(
            f"#{row['id']:>2} {row['order_ref']} | {row['participants_count']} fő | {badge}"
        )
        if counts:
            print("   Méretek:", ", ".join(f"{size}: {qty} db" for size, qty in sorted(counts.items())))
        else:
            print("   Méretek: nincsenek megadva")
        if mismatch:
            print(
                f"   FIGYELEM: résztvevők ({row['participants_count']}) != mentőmellény bejegyzések ({len(lifejackets)})"
            )
        print()


if __name__ == "__main__":
    main()
