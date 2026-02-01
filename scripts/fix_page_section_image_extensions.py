"""Replace image references in page_sections JSON from .jpg/.jpeg to existing .webp (prefers thumb) and commit to DB.

Backs up DB before making changes. Prints a report of changes made.
"""
import sqlite3
from pathlib import Path
import shutil
import json

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / 'kajak_kenu.db'
UPLOADS_DIR = BASE_DIR / 'public' / 'uploads'
BACKUP_DB = DB_PATH.with_name(DB_PATH.name + '.before_fix_images')

def backup_db():
    shutil.copy2(DB_PATH, BACKUP_DB)
    print(f"DB backed up to {BACKUP_DB}")


def find_replacement(rel_path: str):
    """Given a relative path like 'content/info_cards/abc.jpg', find a replacement file.
    Prefer '<name>_thumb.webp' then '<name>.webp'."""
    if not rel_path:
        return None
    p = UPLOADS_DIR / rel_path
    if p.exists():
        return None  # exists already
    base = Path(rel_path)
    name = base.stem
    dirpart = base.parent
    thumb = UPLOADS_DIR / dirpart / f"{name}_thumb.webp"
    webp = UPLOADS_DIR / dirpart / f"{name}.webp"
    if thumb.exists():
        return str((dirpart / thumb.name).as_posix())
    if webp.exists():
        return str((dirpart / webp.name).as_posix())
    return None


def process_sections(conn):
    cur = conn.cursor()
    cur.execute("SELECT slug, content FROM page_sections")
    updated = []
    for slug, content in cur.fetchall():
        try:
            data = json.loads(content or '{}')
        except json.JSONDecodeError:
            continue
        changed = False
        # info_cards specific
        if slug == 'info_cards':
            cards = data.get('cards', [])
            for i, c in enumerate(cards):
                img = c.get('image')
                if img and img.lower().endswith(('.jpg', '.jpeg')):
                    repl = find_replacement(img)
                    if repl:
                        c['image'] = repl
                        changed = True
                        print(f"info_cards.cards[{i}] {img} -> {repl}")
            highlights = data.get('highlights', [])
            for i, h in enumerate(highlights):
                img = h.get('image')
                if img and img.lower().endswith(('.jpg', '.jpeg')):
                    repl = find_replacement(img)
                    if repl:
                        h['image'] = repl
                        changed = True
                        print(f"info_cards.highlights[{i}] {img} -> {repl}")
        # Add more section types if needed
        if changed:
            payload = json.dumps(data, ensure_ascii=False)
            cur.execute("UPDATE page_sections SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?", (payload, slug))
            updated.append(slug)
    return updated


def main():
    if not DB_PATH.exists():
        print('DB not found')
        return
    backup_db()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        updated = process_sections(conn)
        conn.commit()
        print('Updated sections:', updated)
    except Exception as e:
        conn.rollback()
        print('Error:', e)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
