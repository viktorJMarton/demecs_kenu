"""Service helpers for editable site sections."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import get_db

# Seed data for first-run experience and validation fallbacks.
DEFAULT_SECTIONS: Dict[str, Dict[str, Any]] = {
    "hero": {
        "label": "Hero szekció",
        "content": {
            "headline": "Hello There",
            "subheadline": "Provident cupiditate voluptatem et in. Quaerat fugiat ut assumenda excepturi exercitat quasi.",
            "cta_label": "Túranaptár megnyitása",
            "cta_target": "modal:my_modal_7",
            "video_url": "/static/hero-bg.mp4",
        },
    },
    "faq": {
        "label": "Gyakran Ismételt Kérdések",
        "content": {
            "items": [
                {
                    "question": "Hogyan tudok foglalni?",
                    "answer": "Válassz egy túrát az oldalon, töltsd ki az űrlapot, és erősítsd meg a foglalást.",
                },
                {
                    "question": "Milyen felszerelést biztosítotok?",
                    "answer": "Minden túrán biztosítjuk a kajakot, evezőt, mentőmellényt és a szükséges kiegészítőket.",
                },
                {
                    "question": "Lehet-e lemondani a túrát?",
                    "answer": "A túra előtt legalább 48 órával díjmentesen lemondhatod vagy átfoglalhatod az időpontot.",
                },
            ]
        },
    },
    "info_cards": {
        "label": "Infó kártyák",
        "content": {
            "heading": "Általános leírás a vállalkozásról",
            "cards": [
                {
                    "title": "Személyes méretek",
                    "description": "Lorem ipsum dolor sit amet et delectus accommodare his consul copiosae legendos.",
                },
                {
                    "title": "Nézhető hely képpel",
                    "description": "Lorem ipsum dolor sit amet et delectus accommodare his consul copiosae legendos.",
                },
                {
                    "title": "Második blokk, stb",
                    "description": "Lorem ipsum dolor sit amet et delectus accommodare his consul copiosae legendos.",
                },
            ],
            "highlights": [
                {"icon": "🖼️", "label": "Galéria"},
                {"icon": "🖼️", "label": "Élményeink"},
                {"icon": "🖼️", "label": "Hangulat"},
            ],
        },
    },
}


def _ensure_table() -> None:
    """Create storage and seed defaults once."""
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS page_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    for slug, meta in DEFAULT_SECTIONS.items():
        row = db.execute("SELECT 1 FROM page_sections WHERE slug = ?", (slug,)).fetchone()
        if not row:
            db.execute(
                "INSERT INTO page_sections (slug, label, content) VALUES (?, ?, ?)",
                (slug, meta["label"], json.dumps(meta["content"])),
            )
    db.commit()


def list_sections() -> List[Dict[str, Any]]:
    """Return all sections for admin editing UI."""
    _ensure_table()
    db = get_db()
    rows = db.execute(
        "SELECT slug, label, content, updated_at FROM page_sections ORDER BY slug"
    ).fetchall()

    sections: List[Dict[str, Any]] = []
    for row in rows:
        try:
            content = json.loads(row["content"]) if row["content"] else {}
        except json.JSONDecodeError:
            content = {}
        sections.append(
            {
                "slug": row["slug"],
                "label": row["label"],
                "content": content,
                "updated_at": row["updated_at"],
            }
        )
    return sections


def get_section(slug: str) -> Dict[str, Any]:
    """Load a single section with fallback to defaults."""
    _ensure_table()
    db = get_db()
    row = db.execute(
        "SELECT slug, label, content FROM page_sections WHERE slug = ?",
        (slug,),
    ).fetchone()

    if not row:
        default = DEFAULT_SECTIONS.get(slug, {"label": slug, "content": {}})
        return {"slug": slug, "label": default["label"], "content": default["content"]}

    try:
        content = json.loads(row["content"]) if row["content"] else {}
    except json.JSONDecodeError:
        content = {}
    return {"slug": row["slug"], "label": row["label"], "content": content}


def update_section(slug: str, label: str, content: Dict[str, Any]) -> None:
    """Insert or update the stored JSON blob for a section."""
    _ensure_table()
    db = get_db()
    payload = json.dumps(content, ensure_ascii=False)
    exists = db.execute("SELECT 1 FROM page_sections WHERE slug = ?", (slug,)).fetchone()

    if exists:
        db.execute(
            "UPDATE page_sections SET label = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
            (label, payload, slug),
        )
    else:
        db.execute(
            "INSERT INTO page_sections (slug, label, content) VALUES (?, ?, ?)",
            (slug, label, payload),
        )
    db.commit()
