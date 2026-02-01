"""Scan DB & page sections for missing referenced image files and print a report.

Usage:
  python scripts/check_missing_images.py

This script checks:
 - entries in page_sections JSON that have 'image' keys (content.info_cards.cards and content.info_cards.highlights)
 - rows in 'tour_images' and 'location_images' tables for file_path

It reports missing files under public/uploads.
"""
import os
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / 'kajak_kenu.db'
UPLOADS_DIR = BASE_DIR / 'public' / 'uploads'

missing = []

def check_path(p: str, context: str):
    if not p:
        return
    # Normalize local upload paths
    rel = p
    # If path points to a URL, ignore
    if rel.startswith('http://') or rel.startswith('https://'):
        return
    full = UPLOADS_DIR / rel
    if not full.exists():
        missing.append((rel, context))


def check_page_sections(conn):
    cur = conn.cursor()
    cur.execute("SELECT slug, content FROM page_sections")
    for slug, content in cur.fetchall():
        try:
            data = json.loads(content or '{}')
        except json.JSONDecodeError:
            continue
        if slug == 'info_cards':
            cards = data.get('cards', [])
            for i, c in enumerate(cards):
                check_path(c.get('image', ''), f'info_cards.cards[{i}]')
            highlights = data.get('highlights', [])
            for i, h in enumerate(highlights):
                check_path(h.get('image', ''), f'info_cards.highlights[{i}]')


def check_tables(conn):
    cur = conn.cursor()
    for table in ('tour_images', 'location_images'):
        try:
            cur.execute(f"SELECT id, file_path FROM {table}")
        except sqlite3.OperationalError:
            continue
        for row_id, fp in cur.fetchall():
            check_path(fp, f'{table}.id={row_id}')


def main():
    if not DB_PATH.exists():
        print('Database not found at', DB_PATH)
        return
    conn = sqlite3.connect(str(DB_PATH))
    check_page_sections(conn)
    check_tables(conn)
    conn.close()

    if not missing:
        print('No missing images found.')
        return

    print('Missing images report:')
    for path, ctx in missing:
        print(f' - {path} (referenced in: {ctx})')
    print('\nTip: run scripts/generate_thumbnails.py and scripts/migrate_to_webp.py, or use the admin UI to re-upload images.')

if __name__ == '__main__':
    main()
